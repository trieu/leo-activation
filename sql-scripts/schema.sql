-- ============================================================
-- AI-Driven Marketing Automation – Core Data Schema
-- ============================================================
-- This schema is designed for:
--  - Multi-tenant SaaS (tenant isolation via tenant_id + RLS)
--  - Deterministic event identity (hash-based event_id)
--  - High-scale ingestion (partitioning by tenant)
--  - AI semantic search (pgvector embeddings)
--  - Async background embedding jobs
-- ============================================================


-- =========================
-- Required Extensions
-- =========================
-- pgcrypto:
--  - gen_random_uuid() for tenant_id
--  - digest() for SHA-256 event hashing
--
-- vector (pgvector):
--  - store and index embedding vectors for semantic search
--
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;


-- =========================
-- Tenant Table
-- =========================
-- Each tenant represents an isolated customer/account
-- in the SaaS platform.
--
-- tenant_id is UUID to:
--  - avoid guessable IDs
--  - simplify cross-system references
--  - scale safely in distributed environments
--
CREATE TABLE tenant (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =========================
-- Marketing Event (Partitioned)
-- =========================
-- Core business entity:
-- campaigns, webinars, promotions, offline events, etc.
--
-- Design goals:
--  - Deterministic ID (hash) instead of sequence
--  - Tenant-scoped primary key
--  - Optimized for read + AI enrichment
--
CREATE TABLE marketing_event (
    -- Multi-tenant isolation key
    tenant_id         UUID NOT NULL
        REFERENCES tenant(tenant_id)
        ON DELETE CASCADE,

    -- Deterministic event identifier
    -- Generated via SHA-256 hash in trigger
    event_id          TEXT NOT NULL,

    -- Human & semantic content
    event_name        TEXT NOT NULL,
    event_description TEXT,

    -- Used heavily for filtering, analytics, and models
    event_type        TEXT NOT NULL,      -- e.g. webinar, email, offline
    event_channel     TEXT NOT NULL,      -- e.g. facebook, email, tiktok

    -- Temporal semantics (important for analytics & planning)
    start_at          TIMESTAMPTZ NOT NULL,
    end_at            TIMESTAMPTZ NOT NULL,
    timezone          TEXT NOT NULL DEFAULT 'UTC',

    -- Contextual metadata
    location          TEXT,
    event_url         TEXT,

    -- Marketing-specific dimensions
    campaign_code     TEXT,
    target_audience   TEXT,
    budget_amount     NUMERIC(12,2),
    currency          CHAR(3) DEFAULT 'USD',

    -- Ownership & accountability
    owner_team        TEXT,
    owner_email       TEXT,

    -- Lifecycle state
    -- planned → active → completed → cancelled
    status            TEXT NOT NULL DEFAULT 'planned',

    -- =========================
    -- AI / Embedding Fields
    -- =========================
    -- pgvector embedding for semantic search, clustering,
    -- recommendation, and LLM retrieval.
    --
    -- 1536 matches OpenAI / Gemini common embedding size
    --
    embedding         VECTOR(1536),

    -- Tracks embedding lifecycle
    -- pending | processing | ready | failed
    embedding_status  TEXT NOT NULL DEFAULT 'pending',
    embedding_updated_at TIMESTAMPTZ,

    -- Auditing
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Composite PK ensures:
    --  - no cross-tenant collision
    --  - efficient tenant-scoped queries
    CONSTRAINT pk_marketing_event
        PRIMARY KEY (tenant_id, event_id),

    -- Data sanity check
    CONSTRAINT chk_event_time
        CHECK (end_at > start_at)

) PARTITION BY HASH (tenant_id);


-- =========================
-- Hash Partitions
-- =========================
-- 16 partitions is a good baseline:
--  - parallelism for reads/writes
--  - manageable planner overhead
--
-- Can be increased later (32 / 64) if tenants grow unevenly
--
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format(
            'CREATE TABLE marketing_event_p%s
             PARTITION OF marketing_event
             FOR VALUES WITH (MODULUS 16, REMAINDER %s);',
            i, i
        );
    END LOOP;
END $$;


-- =========================
-- Deterministic Event ID Generator
-- =========================
-- Generates a SHA-256 hash from business-meaningful fields.
--
-- Why this matters:
--  - Idempotent inserts (safe replays)
--  - Natural upserts
--  - Prevents accidental duplicates
--
-- Including created_at ensures:
--  - Same campaign reused later ≠ same event
--
CREATE OR REPLACE FUNCTION generate_marketing_event_id()
RETURNS TRIGGER AS $$
DECLARE
    hash_input TEXT;
BEGIN
    hash_input := lower(
        trim(
            concat_ws(
                '||',
                NEW.event_name,
                NEW.event_type,
                NEW.event_channel,
                COALESCE(NEW.location, ''),
                COALESCE(NEW.event_url, ''),
                COALESCE(NEW.owner_team, ''),
                COALESCE(NEW.campaign_code, ''),
                NEW.created_at::text
            )
        )
    );

    -- SHA-256 hex string (64 chars)
    NEW.event_id := encode(digest(hash_input, 'sha256'), 'hex');

    -- Always update updated_at on insert
    NEW.updated_at := now();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Trigger fires only on INSERT
-- (updates should not regenerate event_id)
CREATE TRIGGER trg_event_hash
BEFORE INSERT ON marketing_event
FOR EACH ROW
EXECUTE FUNCTION generate_marketing_event_id();


-- =========================
-- Embedding Job Queue
-- =========================
-- Lightweight job table for async workers.
--
-- Pattern:
--  - DB trigger enqueues
--  - Worker SELECT ... FOR UPDATE SKIP LOCKED
--  - Update embedding + status
--
CREATE TABLE embedding_job (
    job_id     BIGSERIAL PRIMARY KEY,
    tenant_id  UUID NOT NULL,
    event_id   TEXT NOT NULL,

    -- pending | processing | done | failed
    status     TEXT NOT NULL DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Used for job locking / lease mechanism
    locked_at  TIMESTAMPTZ
);


-- =========================
-- Enqueue Embedding Job Trigger
-- =========================
-- Automatically enqueue a job when:
--  - New event is created
--  - Semantic content changes
--
-- This keeps AI pipelines eventually consistent
-- without blocking writes.
--
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
-- Tenant-scoped filtering by lifecycle
CREATE INDEX idx_event_status
ON marketing_event (tenant_id, status);

-- Time-based queries (calendars, planning, analytics)
CREATE INDEX idx_event_start
ON marketing_event (tenant_id, start_at);

-- Vector index for semantic search
-- ivfflat is fast and memory-efficient
-- lists=100 is a reasonable starting point
--
-- IMPORTANT:
--  - Requires ANALYZE after enough rows
--  - Tune lists based on dataset size
--
CREATE INDEX idx_event_embedding
ON marketing_event
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);


-- =========================
-- Row-Level Security (RLS)
-- =========================
-- Enforces tenant isolation at the database level.
--
-- Application MUST set:
--   SET app.current_tenant_id = '<uuid>';
--
ALTER TABLE marketing_event ENABLE ROW LEVEL SECURITY;


CREATE POLICY tenant_rls
ON marketing_event
USING (
    tenant_id = current_setting('app.current_tenant_id')::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.current_tenant_id')::uuid
);


-- ============================================================
-- Clean Semantic View for AI Embeddings
-- ============================================================
-- Purpose:
--   Produce a deterministic, human-readable text block
--   optimized for LLM embeddings and semantic search.
--
-- This view:
--   - Removes noisy fields (ids, timestamps, money math)
--   - Normalizes casing and spacing
--   - Preserves marketing meaning
-- ============================================================

CREATE OR REPLACE VIEW event_content_for_embedding AS
SELECT
    me.tenant_id,
    me.event_id,

    -- =========================
    -- Canonical Embedding Text
    -- =========================
    trim(
        regexp_replace(
            concat_ws(
                E'\n\n',

                -- Event title
                format(
                    'Event: %s',
                    initcap(me.event_name)
                ),

                -- Description (most important semantic signal)
                me.event_description,

                -- Core classification
                format(
                    'Type: %s | Channel: %s',
                    initcap(me.event_type),
                    initcap(me.event_channel)
                ),

                -- Campaign context
                CASE
                    WHEN me.campaign_code IS NOT NULL
                    THEN format('Campaign code: %s', me.campaign_code)
                END,

                -- Target audience
                CASE
                    WHEN me.target_audience IS NOT NULL
                    THEN format('Target audience: %s', me.target_audience)
                END,

                -- Location context (important for geo semantics)
                CASE
                    WHEN me.location IS NOT NULL
                    THEN format('Location: %s', me.location)
                END,

                -- Ownership / organizational context
                CASE
                    WHEN me.owner_team IS NOT NULL
                    THEN format('Owned by team: %s', me.owner_team)
                END

            ),
            -- Collapse multiple spaces/newlines into clean text
            '\s+',
            ' ',
            'g'
        )
    ) AS embedding_text,

    -- Useful metadata for downstream jobs
    me.updated_at

FROM marketing_event me
WHERE
    -- Only embed events that make semantic sense
    me.status <> 'cancelled';
