-- ============================================================
-- Sample Test Data for AI-Driven Marketing Automation
-- ============================================================
-- Purpose:
--   - Populate tenants
--   - Populate realistic marketing events
--   - Trigger embedding jobs automatically
--   - Enable semantic search testing
--
-- Assumptions:
--   - Run as postgres or migration user (bypass RLS)
--   - marketing_event trigger generates marketing_event_id
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Create sample tenants
-- ============================================================

INSERT INTO tenant (tenant_id, tenant_name)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'Acme Retail'),
    ('22222222-2222-2222-2222-222222222222', 'Globex Education'),
    ('33333333-3333-3333-3333-333333333333', 'NeoBank Digital')
ON CONFLICT (tenant_id) DO NOTHING;


-- ============================================================
-- 2. Insert marketing events (marketing_event_id auto-generated)
-- ============================================================

-- ---------- Tenant: Acme Retail ----------
INSERT INTO marketing_event (
    tenant_id,
    event_name,
    event_description,
    event_type,
    event_channel,
    start_at,
    end_at,
    location,
    event_url,
    campaign_code,
    target_audience,
    budget_amount,
    owner_team,
    owner_email,
    status
)
VALUES
(
    '11111111-1111-1111-1111-111111111111',
    'Black Friday Mega Sale',
    'Massive Black Friday promotion offering discounts up to 50 percent on electronics, fashion, and home appliances.',
    'promotion',
    'email',
    now() + interval '7 days',
    now() + interval '10 days',
    'Online',
    'https://acme.example.com/black-friday',
    'BF2025',
    'Existing customers and loyalty members',
    50000,
    'Growth Marketing',
    'growth@acme.example.com',
    'planned'
),
(
    '11111111-1111-1111-1111-111111111111',
    'TikTok Flash Deal Weekend',
    'Short-form video campaign targeting Gen Z with limited-time flash deals promoted via TikTok influencers.',
    'promotion',
    'tiktok',
    now() + interval '14 days',
    now() + interval '16 days',
    'Vietnam',
    'https://tiktok.com/@acmeretail',
    'TTFLASH01',
    'Gen Z mobile-first shoppers',
    20000,
    'Social Media Team',
    'social@acme.example.com',
    'planned'
);


-- ---------- Tenant: Globex Education ----------
INSERT INTO marketing_event (
    tenant_id,
    event_name,
    event_description,
    event_type,
    event_channel,
    start_at,
    end_at,
    location,
    event_url,
    campaign_code,
    target_audience,
    budget_amount,
    owner_team,
    owner_email,
    status
)
VALUES
(
    '22222222-2222-2222-2222-222222222222',
    'AI for Business Webinar',
    'Educational webinar introducing practical AI use cases for business leaders and non-technical managers.',
    'webinar',
    'linkedin',
    now() + interval '5 days',
    now() + interval '5 days' + interval '2 hours',
    'Online',
    'https://globex.edu/webinars/ai-for-business',
    'AIWEB2025',
    'Business executives and MBA students',
    3000,
    'Education Marketing',
    'edu-marketing@globex.edu',
    'planned'
),
(
    '22222222-2222-2222-2222-222222222222',
    'Open Day Campus Tour',
    'On-site campus open day allowing prospective students to experience classrooms, meet faculty, and explore programs.',
    'offline',
    'event',
    now() + interval '20 days',
    now() + interval '20 days' + interval '6 hours',
    'Ho Chi Minh City Campus',
    NULL,
    'OPENDAY2025',
    'High school students and parents',
    10000,
    'Admissions',
    'admissions@globex.edu',
    'planned'
);


-- ---------- Tenant: NeoBank Digital ----------
INSERT INTO marketing_event (
    tenant_id,
    event_name,
    event_description,
    event_type,
    event_channel,
    start_at,
    end_at,
    location,
    event_url,
    campaign_code,
    target_audience,
    budget_amount,
    owner_team,
    owner_email,
    status
)
VALUES
(
    '33333333-3333-3333-3333-333333333333',
    'Zero Fee Digital Account Launch',
    'Product launch campaign promoting a zero-fee digital banking account with instant KYC and cashback rewards.',
    'product_launch',
    'facebook',
    now() + interval '3 days',
    now() + interval '30 days',
    'Vietnam',
    'https://neobank.example.com/zero-fee',
    'ZFREE01',
    'Young professionals and freelancers',
    80000,
    'Product Marketing',
    'product@neobank.example.com',
    'active'
),
(
    '33333333-3333-3333-3333-333333333333',
    'Referral Program Push',
    'Referral incentive campaign encouraging users to invite friends and earn cashback rewards.',
    'promotion',
    'in_app',
    now() + interval '1 day',
    now() + interval '45 days',
    'Mobile App',
    NULL,
    'REF2025',
    'Existing active users',
    25000,
    'CRM Team',
    'crm@neobank.example.com',
    'active'
);

-- ============================================================
-- 3. Verify generated data (optional sanity checks)
-- ============================================================

-- Check events per tenant
-- SELECT tenant_id, COUNT(*) FROM marketing_event GROUP BY tenant_id;

-- Check embedding job queue (should be auto-filled)
-- SELECT status, COUNT(*) FROM embedding_job GROUP BY status;

-- Preview embedding text
-- SELECT tenant_id, marketing_event_id, embedding_text FROM event_content_for_embedding LIMIT 5;

COMMIT;
