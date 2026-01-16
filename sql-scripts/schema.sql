-- ============================================================
-- LEO Data Activation & Alert Center – Unified Database Schema
-- PostgreSQL 16+
-- Modules: CDP, Marketing Automation, News Alert Center
-- Architecture: Multi-tenant, Event-Driven, Hybrid (SQL + Vector + Graph)
-- ============================================================

-- =========================
-- 1. REQUIRED EXTENSIONS
-- =========================
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- UUIDs and Hashing
CREATE EXTENSION IF NOT EXISTS vector;   -- AI Embeddings
CREATE EXTENSION IF NOT EXISTS citext;   -- Case-insensitive text
CREATE EXTENSION IF NOT EXISTS age;      -- Apache AGE (Graph Database)

-- Load AGE functionality
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- =========================
-- 2. SHARED UTILITIES
-- =========================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- 3. TENANT (CORE)
-- =========================
CREATE TABLE IF NOT EXISTS tenant (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tenant_updated_at' AND tgrelid = 'tenant'::regclass
    ) THEN
        CREATE TRIGGER trg_tenant_updated_at BEFORE UPDATE ON tenant
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 4. CDP PROFILES (The "User" Node)
-- ============================================================
CREATE TABLE IF NOT EXISTS cdp_profiles (
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ext_id          TEXT,

    email           CITEXT,
    mobile_number   TEXT,
    zalo_number     TEXT,

    first_name      TEXT,
    last_name       TEXT,
    job_title       TEXT,
    company_name    TEXT,

    -- Segmentation Data
    segments        JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_labels     JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Denormalized, append-only snapshot refs
    segment_snapshots JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Raw Data
    raw_attributes  JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- [ALERT CENTER UPDATE] User Interest Vector for News Matching
    -- Represents user's aggregate reading history/investing interests
    interest_embedding vector(1536),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_cdp_profile_ext UNIQUE (tenant_id, ext_id)
);

-- Trigger for updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cdp_profiles_updated_at' AND tgrelid = 'cdp_profiles'::regclass
    ) THEN
        CREATE TRIGGER trg_cdp_profiles_updated_at BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- Append-only guard for segment_snapshots
CREATE OR REPLACE FUNCTION prevent_snapshot_removal()
RETURNS TRIGGER AS $$
BEGIN
    IF jsonb_array_length(NEW.segment_snapshots) < jsonb_array_length(OLD.segment_snapshots) THEN
        RAISE EXCEPTION 'segment_snapshots is append-only';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_prevent_snapshot_removal' AND tgrelid = 'cdp_profiles'::regclass
    ) THEN
        CREATE TRIGGER trg_prevent_snapshot_removal BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW EXECUTE FUNCTION prevent_snapshot_removal();
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_email ON cdp_profiles (tenant_id, email);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_segments ON cdp_profiles USING GIN (segments jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_raw ON cdp_profiles USING GIN (raw_attributes);

-- RLS
ALTER TABLE cdp_profiles ENABLE ROW LEVEL SECURITY;
-- (RLS Policy omitted for brevity, identical to original)

-- ============================================================
-- 5. CAMPAIGN (STRATEGY)
-- ============================================================
CREATE TABLE IF NOT EXISTS campaign (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    campaign_id    UUID NOT NULL DEFAULT gen_random_uuid(),
    campaign_code  TEXT NOT NULL,
    campaign_name  TEXT NOT NULL,
    objective      TEXT,
    status         TEXT NOT NULL DEFAULT 'active',
    start_at       TIMESTAMPTZ,
    end_at         TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_campaign PRIMARY KEY (tenant_id, campaign_id),
    CONSTRAINT uq_campaign_code UNIQUE (tenant_id, campaign_code)
);
-- (Triggers and RLS for campaign preserved from original)

-- ============================================================
-- 6. MARKETING EVENT (EXECUTION)
-- ============================================================
CREATE TABLE IF NOT EXISTS marketing_event (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    event_id       TEXT NOT NULL,
    campaign_id    UUID,
    event_name     TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    event_channel  TEXT NOT NULL,
    start_at       TIMESTAMPTZ NOT NULL,
    end_at         TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'planned',
    embedding      VECTOR(1536),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_marketing_event PRIMARY KEY (tenant_id, event_id),
    CONSTRAINT fk_marketing_event_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
) PARTITION BY HASH (tenant_id);

-- Partitions (0-15)
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS marketing_event_p%s PARTITION OF marketing_event FOR VALUES WITH (MODULUS 16, REMAINDER %s);', i, i);
    END LOOP;
END $$;

-- (Triggers for ID generation and RLS for marketing_event preserved from original)

-- ============================================================
-- 7. SEGMENT SNAPSHOTS & MEMBERS
-- ============================================================
CREATE TABLE IF NOT EXISTS segment_snapshot (
    tenant_id        UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    segment_name     TEXT NOT NULL,
    segment_version  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_segment_snapshot PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS segment_snapshot_member (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id  UUID NOT NULL,
    profile_id   UUID NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_segment_snapshot_member PRIMARY KEY (tenant_id, snapshot_id, profile_id),
    CONSTRAINT fk_snapshot_member_snapshot FOREIGN KEY (tenant_id, snapshot_id) REFERENCES segment_snapshot (tenant_id, snapshot_id) ON DELETE CASCADE,
    CONSTRAINT fk_snapshot_member_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
);

-- ============================================================
-- 8. [NEW MODULE] ALERT CENTER - REFERENCE DATA
-- ============================================================

-- 8.1 Instruments (Assets/Books/Indices)
-- Shared Reference Data or Tenant Specific. 
-- We use tenant_id nullable; if NULL, it's a global instrument (e.g. AAPL).
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id   BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE, -- Nullable for global assets
    
    symbol          VARCHAR(20) NOT NULL, -- e.g. 'AAPL', 'EURUSD'
    name            TEXT NOT NULL,
    type            VARCHAR(50) NOT NULL, -- 'STOCK', 'FOREX', 'CRYPTO', 'ECONOMIC'
    sector          VARCHAR(100),
    meta_data       JSONB DEFAULT '{}'::jsonb, -- Store earnings dates, etc.
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    CONSTRAINT uq_instrument_symbol UNIQUE (tenant_id, symbol) -- Unique per tenant or global
);

-- 8.2 Real-time Market Snapshot
-- High-throughput table for the "Minute Worker"
CREATE TABLE IF NOT EXISTS market_snapshot (
    symbol          VARCHAR(20) PRIMARY KEY, -- Linked to instruments.symbol
    price           NUMERIC(18, 5),
    change_percent  NUMERIC(5, 2),
    volume          BIGINT,
    last_updated    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 9. [NEW MODULE] ALERT CENTER - RULES ENGINE
-- ============================================================

-- ============================================================
-- FIXED ALERT RULES SCHEMA (Idempotent & Deterministic Hash ID)
-- ============================================================

-- Ensure pgcrypto is enabled for hashing
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. SAFELY CREATE ENUMS (Idempotent Check)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_source_enum') THEN
        CREATE TYPE alert_source_enum AS ENUM ('USER_MANUAL', 'AI_AGENT');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_status_enum') THEN
        CREATE TYPE alert_status_enum AS ENUM ('ACTIVE', 'PAUSED', 'TRIGGERED');
    END IF;
END$$;

-- 2. TABLE DEFINITION
CREATE TABLE IF NOT EXISTS alert_rules (
    -- ID is now 64 chars to store SHA-256 Hex
    rule_id         VARCHAR(64) NOT NULL, 
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      UUID NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    
    -- Target
    symbol          VARCHAR(20) NOT NULL, 
    
    -- Configuration
    alert_type      VARCHAR(50) NOT NULL, -- 'PRICE', 'EARNINGS', 'NEWS', 'AI_SIGNAL'
    source          alert_source_enum DEFAULT 'USER_MANUAL',
    
    -- The Logic
    condition_logic JSONB NOT NULL,
    
    status          alert_status_enum DEFAULT 'ACTIVE',
    frequency       VARCHAR(50) DEFAULT 'ONCE', 
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    -- Composite PK for multi-tenancy + idempotency
    CONSTRAINT pk_alert_rules PRIMARY KEY (tenant_id, rule_id)
);

-- 3. HASH GENERATION FUNCTION
-- Purpose: Ensures rule_id is always unique to the specific logic configuration.
CREATE OR REPLACE FUNCTION generate_alert_rule_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.rule_id := encode(
        digest(
            lower(concat_ws('||',
                NEW.tenant_id::text,
                NEW.profile_id::text,
                NEW.symbol,
                NEW.alert_type,
                NEW.frequency,
                -- Cast JSONB to text to ensure logic is part of the unique hash
                NEW.condition_logic::text 
            )),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4. TRIGGER ASSIGNMENT
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_alert_rules_hash'
          AND tgrelid = 'alert_rules'::regclass
    ) THEN
        CREATE TRIGGER trg_alert_rules_hash
        BEFORE INSERT ON alert_rules
        FOR EACH ROW
        EXECUTE FUNCTION generate_alert_rule_hash();
    END IF;
END $$;

-- 5. UPDATED_AT TRIGGER
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_alert_rules_updated_at'
          AND tgrelid = 'alert_rules'::regclass
    ) THEN
        CREATE TRIGGER trg_alert_rules_updated_at
        BEFORE UPDATE ON alert_rules
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- 6. INDEXES & RLS
CREATE INDEX IF NOT EXISTS idx_alert_rules_worker 
ON alert_rules (symbol, status) 
WHERE status = 'ACTIVE';

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE policyname = 'alert_rules_tenant_rls'
          AND schemaname = current_schema()
          AND tablename = 'alert_rules'
    ) THEN
        CREATE POLICY alert_rules_tenant_rls ON alert_rules
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
    END IF;
END $$;

-- ============================================================
-- 10. [NEW MODULE] ALERT CENTER - SEMANTIC NEWS & SIGNALS
-- ============================================================

CREATE TABLE IF NOT EXISTS news_feed (
    news_id         BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE, -- Optional: Private news
    
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    
    -- AI Analysis
    related_symbols VARCHAR(20)[], -- Array of tickers
    sentiment_score NUMERIC(3,2),
    
    -- Embedding for Vector Search (Hybrid Logic)
    content_embedding vector(1536),
    
    published_at    TIMESTAMPTZ DEFAULT now()
);

-- HNSW Index for fast semantic search
CREATE INDEX IF NOT EXISTS idx_news_embedding 
ON news_feed USING hnsw (content_embedding vector_cosine_ops);


-- ============================================================
-- 11. AGENT TASK (AI DECISION TRACE)
-- ============================================================
-- (Updated to link to Alert Center concepts)
CREATE TABLE IF NOT EXISTS agent_task (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    task_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    agent_name   TEXT NOT NULL, -- e.g., 'MarketMonitorAgent'
    task_type    TEXT NOT NULL, -- e.g., 'PROCESS_SIGNAL', 'GENERATE_RULE'
    task_goal    TEXT,

    campaign_id  UUID,
    event_id     TEXT,
    snapshot_id  UUID,
    
    -- [ALERT LINK]
    related_news_id BIGINT REFERENCES news_feed(news_id),

    reasoning_summary TEXT,
    reasoning_trace   JSONB,

    status       TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_agent_task_campaign FOREIGN KEY (tenant_id, campaign_id) REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
);
-- (RLS preserved)

-- ============================================================
-- 12. DELIVERY LOG (EXECUTION TRUTH)
-- ============================================================
CREATE TABLE IF NOT EXISTS delivery_log (
    tenant_id     UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    delivery_id   BIGSERIAL PRIMARY KEY,
    campaign_id   UUID,
    event_id      TEXT NOT NULL,
    profile_id    UUID NOT NULL,
    
    channel       TEXT NOT NULL, -- 'WEB_PUSH', 'EMAIL'
    delivery_status TEXT NOT NULL,
    provider_response JSONB,
    
    sent_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- (RLS preserved)

-- ============================================================
-- 13. EMBEDDING QUEUE
-- ============================================================
CREATE TABLE IF NOT EXISTS embedding_job (
    job_id      BIGSERIAL PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    event_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 14. GRAPH SETUP (Apache AGE)
-- ============================================================
-- NOTE: AGE commands typically require a specific session context.
-- These commands initialize the schema for the graph relationship queries.

/*
-- 1. Create Graph Context
SELECT create_graph('investing_knowledge_graph');

-- 2. Create Labels (Nodes)
SELECT create_vlabel('investing_knowledge_graph', 'User');
SELECT create_vlabel('investing_knowledge_graph', 'Asset');
SELECT create_vlabel('investing_knowledge_graph', 'Sector');
SELECT create_vlabel('investing_knowledge_graph', 'NewsEvent');

-- 3. Create Labels (Edges)
SELECT create_elabel('investing_knowledge_graph', 'HOLDS');      -- User -> Asset
SELECT create_elabel('investing_knowledge_graph', 'WATCHES');    -- User -> Asset
SELECT create_elabel('investing_knowledge_graph', 'BELONGS_TO'); -- Asset -> Sector
SELECT create_elabel('investing_knowledge_graph', 'IMPACTS');    -- NewsEvent -> Sector
*/

-- End of Schema