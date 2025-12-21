-- =========================
-- Extensions
-- =========================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- Tenant Table
-- =========================
CREATE TABLE tenant (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- Marketing Event (Partitioned)
-- =========================
CREATE TABLE marketing_event (
    tenant_id         UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    event_id          TEXT NOT NULL,

    event_name        TEXT NOT NULL,
    event_description TEXT,
    event_type        TEXT NOT NULL,
    event_channel     TEXT NOT NULL,

    start_at          TIMESTAMPTZ NOT NULL,
    end_at            TIMESTAMPTZ NOT NULL,
    timezone          TEXT NOT NULL DEFAULT 'UTC',

    location          TEXT,
    event_url         TEXT,

    campaign_code     TEXT,
    target_audience   TEXT,
    budget_amount     NUMERIC(12,2),
    currency          CHAR(3) DEFAULT 'USD',

    owner_team        TEXT,
    owner_email       TEXT,

    status            TEXT NOT NULL DEFAULT 'planned',

    embedding         VECTOR(1536),
    embedding_status  TEXT NOT NULL DEFAULT 'pending',
    embedding_updated_at TIMESTAMPTZ,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_marketing_event PRIMARY KEY (tenant_id, event_id),
    CONSTRAINT chk_event_time CHECK (end_at > start_at)
) PARTITION BY HASH (tenant_id);

-- =========================
-- Create Partitions (16)
-- =========================
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE marketing_event_p%s PARTITION OF marketing_event
             FOR VALUES WITH (MODULUS 16, REMAINDER %s);',
            i, i
        );
    END LOOP;
END $$;

-- =========================
-- Hash ID Generator Trigger
-- =========================
CREATE OR REPLACE FUNCTION generate_marketing_event_id()
RETURNS TRIGGER AS $$
DECLARE
    hash_input TEXT;
BEGIN
    hash_input := lower(trim(concat_ws(
        '||',
        NEW.event_name,
        NEW.event_type,
        NEW.event_channel,
        COALESCE(NEW.location, ''),
        COALESCE(NEW.event_url, ''),
        COALESCE(NEW.owner_team, ''),
        COALESCE(NEW.campaign_code, ''),
        NEW.created_at::text
    )));

    NEW.event_id := encode(digest(hash_input, 'sha256'), 'hex');
    NEW.updated_at := now();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_event_hash
BEFORE INSERT ON marketing_event
FOR EACH ROW
EXECUTE FUNCTION generate_marketing_event_id();

-- =========================
-- Embedding Job Queue
-- =========================
CREATE TABLE embedding_job (
    job_id     BIGSERIAL PRIMARY KEY,
    tenant_id  UUID NOT NULL,
    event_id   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at  TIMESTAMPTZ
);

-- =========================
-- Enqueue Job Trigger
-- =========================
CREATE OR REPLACE FUNCTION enqueue_embedding_job()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO embedding_job (tenant_id, event_id)
    VALUES (NEW.tenant_id, NEW.event_id);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enqueue_embedding
AFTER INSERT OR UPDATE OF event_name, event_description
ON marketing_event
FOR EACH ROW
EXECUTE FUNCTION enqueue_embedding_job();

-- =========================
-- Indexes
-- =========================
CREATE INDEX idx_event_status
ON marketing_event (tenant_id, status);

CREATE INDEX idx_event_start
ON marketing_event (tenant_id, start_at);

CREATE INDEX idx_event_embedding
ON marketing_event
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- =========================
-- RLS
-- =========================
ALTER TABLE marketing_event ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_rls
ON marketing_event
USING (
    tenant_id = current_setting('app.current_tenant_id')::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.current_tenant_id')::uuid
);
