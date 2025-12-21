-- Create tenant
INSERT INTO tenant (tenant_name)
VALUES ('Acme SaaS')
RETURNING tenant_id;

-- Assume returned tenant_id:
-- 11111111-1111-1111-1111-111111111111

-- Set tenant context
SET app.current_tenant_id = '11111111-1111-1111-1111-111111111111';

-- Insert events
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
    owner_team,
    owner_email,
    budget_amount
)
VALUES
(
    '11111111-1111-1111-1111-111111111111',
    'AI Growth Webinar',
    'Scaling SaaS with AI-driven marketing',
    'webinar',
    'online',
    '2025-01-15 15:00+00',
    '2025-01-15 16:30+00',
    'Zoom',
    'https://acme.com/ai-webinar',
    'Q1_AI',
    'Growth',
    'growth@acme.com',
    5000
),
(
    '11111111-1111-1111-1111-111111111111',
    'Customer Summit',
    'Annual customer conference',
    'conference',
    'in_person',
    '2025-03-10 09:00+00',
    '2025-03-12 17:00+00',
    'San Francisco',
    'https://acme.com/summit',
    'SUMMIT_2025',
    'Marketing',
    'marketing@acme.com',
    25000
);

-- Verify
SELECT tenant_id, event_id, event_name, embedding_status
FROM marketing_event;
