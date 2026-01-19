-- ============================================================
-- LEO Data Activation & Alert Center – Unified Database Schema
-- Database: PostgreSQL 16+
-- Architecture: Multi-tenant, Event-Driven, Hybrid (SQL + Vector + Graph)
-- ============================================================

-- =========================
-- 1. REQUIRED EXTENSIONS
-- =========================
-- crypto: Used for gen_random_uuid() and hashing (SHA256) for idempotency.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- vector: Enables high-dimensional vector storage for RAG and Semantic Search.
CREATE EXTENSION IF NOT EXISTS vector;
-- citext: "Case-Insensitive Text" simplifies email/username comparisons.
CREATE EXTENSION IF NOT EXISTS citext;
-- age: Apache AGE for Graph Database capabilities (Nodes/Edges within Postgres).
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE functionality and set path to include graph catalog
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- =========================
-- 2. SHARED UTILITIES
-- =========================

-- Function: Auto-update 'updated_at' timestamp
-- Usage: Applied via trigger to all mutable tables to track modification time.
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- 3. TENANT (CORE NAMESPACE)
-- =========================
-- The root of the multi-tenant architecture. 
-- Tenant ID remains UUID to ensure global uniqueness across distributed systems.
CREATE TABLE IF NOT EXISTS tenant (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name TEXT NOT NULL,
    status      TEXT DEFAULT 'active', -- 'active', 'suspended', 'archived'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger: Maintain updated_at
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
-- 4. CDP PROFILES (The "User" Entity)
-- ============================================================
-- Represents the core customer identity.
-- ID Type: TEXT (Allows flexibility for external IDs or UUID strings)
CREATE TABLE IF NOT EXISTS cdp_profiles (
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text, 
    ext_id          TEXT, -- External System ID (e.g., Salesforce ID, Shopify ID)

    -- Contact Info (using CITEXT for case-insensitive email matching)
    email           CITEXT,
    mobile_number   TEXT,
    zalo_number     TEXT,

    -- Demographics
    first_name      TEXT,
    last_name       TEXT,
    job_title       TEXT,
    company_name    TEXT,

    -- Computed Data (JSONB for flexibility)
    segments        JSONB NOT NULL DEFAULT '[]'::jsonb, -- Current active segments
    data_labels     JSONB NOT NULL DEFAULT '[]'::jsonb, -- Tags like 'VIP', 'ChurnRisk'
    
    -- Audit Trail: Denormalized, append-only list of segment history
    segment_snapshots JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Raw Data: Unstructured attributes ingested from sources
    raw_attributes  JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- AI Personalization:
    -- Represents user's aggregate reading history or investing interests.
    -- Used for dot-product similarity search against News/Alerts.
    interest_embedding vector(1536),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Ensure one profile per external ID per tenant
    CONSTRAINT uq_cdp_profile_ext UNIQUE (tenant_id, ext_id)
);

-- Trigger: Maintain updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cdp_profiles_updated_at' AND tgrelid = 'cdp_profiles'::regclass
    ) THEN
        CREATE TRIGGER trg_cdp_profiles_updated_at BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- Logic Guard: Ensure segment history is never deleted, only appended to.
CREATE OR REPLACE FUNCTION prevent_snapshot_removal()
RETURNS TRIGGER AS $$
BEGIN
    IF jsonb_array_length(NEW.segment_snapshots) < jsonb_array_length(OLD.segment_snapshots) THEN
        RAISE EXCEPTION 'Data Integrity Violation: segment_snapshots is append-only';
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_email ON cdp_profiles (tenant_id, email);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_segments ON cdp_profiles USING GIN (segments jsonb_path_ops); -- Fast JSON query
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_raw ON cdp_profiles USING GIN (raw_attributes);

-- Security: Enable Row Level Security (RLS)
ALTER TABLE cdp_profiles ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 5. CAMPAIGN (STRATEGY)
-- ============================================================
-- Marketing initiatives container.
-- ID Type: TEXT
CREATE TABLE IF NOT EXISTS campaign (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    campaign_id    TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    
    campaign_code  TEXT NOT NULL, -- Human readable code (e.g., 'SUMMER-2026')
    campaign_name  TEXT NOT NULL,
    objective      TEXT, -- 'AWARENESS', 'CONVERSION', etc.
    status         TEXT NOT NULL DEFAULT 'active',
    
    start_at       TIMESTAMPTZ,
    end_at         TIMESTAMPTZ,
    
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_campaign PRIMARY KEY (tenant_id, campaign_id),
    CONSTRAINT uq_campaign_code UNIQUE (tenant_id, campaign_code)
);

-- ============================================================
-- 6. MARKETING EVENT (EXECUTION)
-- ============================================================
-- Specific actions within a campaign (e.g., "Send Email Tuesday").
-- Partitioned by Tenant for scalability.
CREATE TABLE IF NOT EXISTS marketing_event (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    event_id       TEXT NOT NULL, -- Client-provided or generated ID
    campaign_id    TEXT, -- Reference to Parent Campaign
    
    event_name     TEXT NOT NULL,
    event_type     TEXT NOT NULL, -- 'BROADCAST', 'TRIGGER', 'API'
    event_channel  TEXT NOT NULL, -- 'EMAIL', 'SMS', 'PUSH'
    
    start_at       TIMESTAMPTZ NOT NULL,
    end_at         TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'planned',
    
    -- AI Context: Embedding of the event description for "Campaign RAG"
    embedding      VECTOR(1536),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_marketing_event PRIMARY KEY (tenant_id, event_id),
    CONSTRAINT fk_marketing_event_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
) PARTITION BY HASH (tenant_id);

-- Create Partitions (Modulus 16)
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS marketing_event_p%s PARTITION OF marketing_event FOR VALUES WITH (MODULUS 16, REMAINDER %s);', i, i);
    END LOOP;
END $$;

-- ============================================================
-- 7. SEGMENT SNAPSHOTS & MEMBERS
-- ============================================================
-- Static lists of users captured at a specific point in time.
-- ID Type: TEXT

CREATE TABLE IF NOT EXISTS segment_snapshot (
    tenant_id        UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id      TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    
    segment_name     TEXT NOT NULL,
    segment_version  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_segment_snapshot PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS segment_snapshot_member (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id  TEXT NOT NULL,
    profile_id   TEXT NOT NULL, -- FK to cdp_profiles
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_segment_snapshot_member PRIMARY KEY (tenant_id, snapshot_id, profile_id),
    CONSTRAINT fk_snapshot_member_snapshot FOREIGN KEY (tenant_id, snapshot_id) REFERENCES segment_snapshot (tenant_id, snapshot_id) ON DELETE CASCADE,
    CONSTRAINT fk_snapshot_member_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
);

-- ============================================================
-- 8. ALERT CENTER - REFERENCE DATA
-- ============================================================

-- 8.1 Instruments (Assets/Books/Indices)
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id   BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE, -- NULL = Global Asset
    
    symbol          VARCHAR(20) NOT NULL, -- e.g. 'AAPL', 'BTC-USD'
    name            TEXT NOT NULL,
    type            VARCHAR(50) NOT NULL, -- 'STOCK', 'CRYPTO', 'FX'
    sector          VARCHAR(100),
    meta_data       JSONB DEFAULT '{}'::jsonb,
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    CONSTRAINT uq_instrument_symbol UNIQUE (tenant_id, symbol)
);

-- 8.2 Real-time Market Snapshot
-- High-write throughput table.
CREATE TABLE IF NOT EXISTS market_snapshot (
    symbol          VARCHAR(20) PRIMARY KEY,
    price           NUMERIC(18, 5),
    change_percent  NUMERIC(5, 2),
    volume          BIGINT,
    last_updated    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 9. ALERT CENTER - RULES ENGINE
-- ============================================================

-- Enums for Type Safety
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_source_enum') THEN
        CREATE TYPE alert_source_enum AS ENUM ('USER_MANUAL', 'AI_AGENT');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_status_enum') THEN
        CREATE TYPE alert_status_enum AS ENUM ('ACTIVE', 'PAUSED', 'TRIGGERED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS alert_rules (
    -- ID is a deterministic hash (TEXT/VARCHAR) based on the rule logic.
    rule_id         VARCHAR(64) NOT NULL, 
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    
    -- UPDATED: profile_id is now TEXT to match cdp_profiles PK
    profile_id      TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    
    -- Target Asset
    symbol          VARCHAR(20) NOT NULL, 
    
    -- Configuration
    alert_type      VARCHAR(50) NOT NULL, -- 'PRICE', 'NEWS', 'AI_SIGNAL'
    source          alert_source_enum DEFAULT 'USER_MANUAL',
    
    -- The Condition (e.g., {"operator": ">", "value": 150})
    condition_logic JSONB NOT NULL,
    
    status          alert_status_enum DEFAULT 'ACTIVE',
    frequency       VARCHAR(50) DEFAULT 'ONCE', 
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    -- Composite PK for multi-tenancy
    CONSTRAINT pk_alert_rules PRIMARY KEY (tenant_id, rule_id)
);

-- Idempotency Logic: Generate Hash ID based on Rule Content
-- Ensures we don't create duplicate rules for the same user/symbol/condition.
CREATE OR REPLACE FUNCTION generate_alert_rule_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.rule_id := encode(
        digest(
            lower(concat_ws('||',
                NEW.tenant_id::text,
                NEW.profile_id, -- Already text
                NEW.symbol,
                NEW.alert_type,
                NEW.frequency,
                NEW.condition_logic::text 
            )),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for Hash and Timestamp
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_alert_rules_hash' AND tgrelid = 'alert_rules'::regclass) THEN
        CREATE TRIGGER trg_alert_rules_hash BEFORE INSERT ON alert_rules
        FOR EACH ROW EXECUTE FUNCTION generate_alert_rule_hash();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_alert_rules_updated_at' AND tgrelid = 'alert_rules'::regclass) THEN
        CREATE TRIGGER trg_alert_rules_updated_at BEFORE UPDATE ON alert_rules
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- Index for the "Worker" that scans active rules
CREATE INDEX IF NOT EXISTS idx_alert_rules_worker 
ON alert_rules (symbol, status) 
WHERE status = 'ACTIVE';

-- RLS Policy
ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_tenant_rls' AND tablename = 'alert_rules') THEN
        CREATE POLICY alert_rules_tenant_rls ON alert_rules
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
    END IF;
END $$;

-- ============================================================
-- 10. ALERT CENTER - SEMANTIC NEWS & SIGNALS
-- ============================================================

CREATE TABLE IF NOT EXISTS news_feed (
    news_id         BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    
    -- Metadata extracted by AI
    related_symbols VARCHAR(20)[],
    sentiment_score NUMERIC(3,2),
    
    -- Hybrid Search: Vector Embedding
    content_embedding vector(1536),
    
    published_at    TIMESTAMPTZ DEFAULT now()
);

-- HNSW Index: High-performance vector similarity search
CREATE INDEX IF NOT EXISTS idx_news_embedding 
ON news_feed USING hnsw (content_embedding vector_cosine_ops);

-- ============================================================
-- 11. AGENT TASK (AI DECISION TRACE)
-- ============================================================
-- Logs AI reasoning and actions.
-- ID Type: TEXT
CREATE TABLE IF NOT EXISTS agent_task (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    task_id      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,

    agent_name   TEXT NOT NULL, 
    task_type    TEXT NOT NULL,
    task_goal    TEXT,

    -- Linkage to other entities (All converted to TEXT)
    campaign_id  TEXT,
    event_id     TEXT,
    snapshot_id  TEXT, 
    
    related_news_id BIGINT REFERENCES news_feed(news_id),

    -- Chain of Thought (CoT) storage
    reasoning_summary TEXT,
    reasoning_trace   JSONB,

    status       TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_agent_task_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
);

-- ============================================================
-- 12. DELIVERY LOG (EXECUTION TRUTH)
-- ============================================================
-- Final record of messages sent to users.
-- ID Type: TEXT where applicable.
CREATE TABLE IF NOT EXISTS delivery_log (
    tenant_id     UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    delivery_id   BIGSERIAL PRIMARY KEY,
    
    campaign_id   TEXT, -- FK to campaign
    event_id      TEXT NOT NULL,
    
    profile_id    TEXT NOT NULL, -- FK to cdp_profiles (TEXT)
    
    channel       TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    provider_response JSONB,
    
    sent_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 13. EMBEDDING QUEUE
-- ============================================================
-- Asynchronous queue for processing embeddings.
CREATE TABLE IF NOT EXISTS embedding_job (
    job_id      BIGSERIAL PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    event_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 14. SYSTEM BOOTSTRAP: DEFAULT TENANT
-- ============================================================

-- 1. Safely insert default 'master app' tenant
-- Uses SELECT ... WHERE NOT EXISTS for concurrency-safe idempotency
INSERT INTO tenant (tenant_name, status)
SELECT 'master app', 'active'
WHERE NOT EXISTS (
    SELECT 1 FROM tenant WHERE tenant_name = 'master app'
);

-- 2. Set the Session Context
-- We set 'app.current_tenant_id' so that RLS policies on other tables 
-- (like alert_rules) will allow inserts immediately after this block.
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    -- Fetch the ID of the master app
    SELECT tenant_id INTO v_tenant_id 
    FROM tenant 
    WHERE tenant_name = 'master app';

    -- Set the config variable. 
    -- Parameter 3 (is_local) is FALSE, meaning this applies to the whole session,
    -- not just this transaction block.
    PERFORM set_config('app.current_tenant_id', v_tenant_id::text, false);
    
    -- Optional: Log to console for verification
    RAISE NOTICE 'Session configured for Tenant: master app (%)', v_tenant_id;
END $$;

-- ============================================================
-- 15. BEHAVIORAL EVENTS (THE FEEDBACK LOOP)
-- ============================================================
-- Captures high-frequency user actions for AI training & triggering.
-- Partitioned by time (Monthly) because this table grows huge.

CREATE TABLE IF NOT EXISTS behavioral_events (
    event_id        BIGSERIAL, -- High throughput, avoid UUID overhead here if possible, or use UUIDv7
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT NOT NULL, -- No FK constraint for write speed? Or keep FK for integrity. Let's keep FK.
    
    event_type      TEXT NOT NULL, -- 'VIEW', 'CLICK', 'DISMISS', 'SHARE', 'CONVERT'
    
    -- Context: What did they interact with?
    entity_type     TEXT, -- 'NEWS', 'ALERT', 'ASSET', 'CAMPAIGN'
    entity_id       TEXT, -- The ID of the news/alert/asset
    
    -- AI Feedback: Did this interaction signal positive or negative interest?
    sentiment_val   INTEGER DEFAULT 0, -- +1 (Positive), -1 (Negative), 0 (Neutral)
    
    meta_data       JSONB DEFAULT '{}'::jsonb, -- Store URL clicked, device info, etc.
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT fk_behavioral_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
) PARTITION BY RANGE (created_at);

-- Create partitions for the next 12 months automatically
DO $$
DECLARE
    start_date DATE := date_trunc('month', now());
    partition_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..11 LOOP
        partition_date := start_date + (i || ' month')::interval;
        partition_name := 'behavioral_events_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF behavioral_events FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + '1 month'::interval
        );
    END LOOP;
END $$;

-- Indexes for Analytics & AI Training
CREATE INDEX IF NOT EXISTS idx_behavioral_profile_time 
    ON behavioral_events (profile_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_behavioral_entity 
    ON behavioral_events (entity_type, entity_id);

-- RLS
ALTER TABLE behavioral_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY behavioral_events_tenant_rls ON behavioral_events
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);