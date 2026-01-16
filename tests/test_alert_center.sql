-- ============================================================
-- 1. VERIFY RELATIONAL DATA
-- ============================================================
-- Check if we have 10 users
SELECT count(*) as user_count FROM cdp_profiles;

-- Check if we have 20 assets
SELECT count(*) as asset_count FROM instruments;

-- Check if Alice's test rule exists
SELECT * FROM alert_rules WHERE symbol = 'AAPL';

-- ============================================================
-- 2. VERIFY GRAPH DATA (Nodes & Edges)
-- ============================================================
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Check if Alice HOLDS Apple in the Graph
SELECT * FROM cypher('investing_knowledge_graph', $$
    MATCH (u:User {name: 'Alice'})-[r:HOLDS]->(a:Asset {symbol: 'AAPL'})
    RETURN u.name, type(r), a.symbol
$$) as (user_name agtype, relation agtype, asset agtype);

-- Check if the "Tech Regulation" news IMPACTS the "Technology" sector
SELECT * FROM cypher('investing_knowledge_graph', $$
    MATCH (n:NewsEvent {id: 5})-[r:IMPACTS]->(s:Sector)
    RETURN n.title, type(r), s.name
$$) as (news_title agtype, relation agtype, sector_name agtype);

-- ============================================================
-- 3. SIMULATE ALERT TRIGGERING AND NOTIFICATION GENERATION
-- ------------------------------------------------------------

-- A. Simulate "Minute Worker" (Price Alert)
-- STEP 1: FORCE MARKET CONDITIONS
-- ------------------------------------------------------------
-- Update the market snapshot to trigger the rule
INSERT INTO market_snapshot (symbol, price, last_updated)
VALUES ('AAPL', 155.50, NOW())
ON CONFLICT (symbol) DO UPDATE 
SET price = EXCLUDED.price, last_updated = NOW();

-- ------------------------------------------------------------
-- STEP 2: RUN WORKER QUERY
-- ------------------------------------------------------------
-- This returns the payload for your Notification Service
SELECT 
    p.email, 
    p.first_name,
    r.symbol, 
    r.condition_logic->>'operator' as operator,
    r.condition_logic->>'value' as target_price,
    m.price as current_price,
    'PRICE_ALERT' as notification_type
FROM alert_rules r
JOIN market_snapshot m ON r.symbol = m.symbol
JOIN cdp_profiles p ON r.profile_id = p.profile_id
WHERE 
    r.status = 'ACTIVE' 
    AND r.alert_type = 'PRICE'
    -- Logic: If Rule is ">" AND Current > Target
    AND (
        (r.condition_logic->>'operator' = '>' AND m.price >= (r.condition_logic->>'value')::numeric)
    );

-- ------------------------------------------------------------
-- STEP 1: DEFINE INCOMING SIGNAL
-- ------------------------------------------------------------
-- Assume the Crawler just inserted News ID 5 ("Tech Regulation")
-- We want to find WHO to alert based on their Portfolio (Graph)

-- ------------------------------------------------------------
-- STEP 2: RUN AGENT QUERY (Graph Traversal)
-- ------------------------------------------------------------
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- 1. Trace Impact: News -> Sector
-- 2. Trace Ownership: Sector <- Asset <- User
SELECT * FROM cypher('investing_knowledge_graph', $$
    MATCH (n:NewsEvent {id: 5})

    MATCH (n)-[:IMPACTS]->(s:Sector)
   
    MATCH (s)<-[:BELONGS_TO]-(a:Asset)<-[:HOLDS]-(u:User)
    
    RETURN u.id, u.name, a.symbol, s.name, n.title
$$) as (user_uuid agtype, user_name agtype, asset_symbol agtype, sector agtype, news_title agtype);

-- ------------------------------------------------------------
-- STEP 3: MOCK DELIVERY LOGGING
-- ------------------------------------------------------------
-- If the above query returns "Alice" (because she holds AAPL), 
-- the Agent would insert into the log:
INSERT INTO delivery_log (tenant_id, event_id, profile_id, channel, delivery_status, sent_at)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 
    'NEWS_EVENT_5', 
    '00000000-0000-0000-0000-000000000001', -- Alice's ID
    'WEB_PUSH', 
    'SENT', 
    NOW()
);

-- Check the log
SELECT * FROM delivery_log ORDER BY created_at DESC LIMIT 10;