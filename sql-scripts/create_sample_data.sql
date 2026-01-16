-- ============================================================
-- SAMPLE TEST DATA GENERATION
-- System: Leo Data Activation & Alert Center
-- Purpose: Generate 10 Users, 20 Assets, Graph Relations, and News
-- Idempotency: Supports re-running (Updates existing data)
-- ============================================================

-- 1. SETUP EXTENSIONS & PATHS
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- ============================================================
-- A. RELATIONAL DATA (SQL)
-- ============================================================

-- 1. Create Test Tenant
INSERT INTO tenant (tenant_id, tenant_name, status)
VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Alpha Investment Fund', 'active')
ON CONFLICT (tenant_id) DO UPDATE 
SET tenant_name = EXCLUDED.tenant_name, status = EXCLUDED.status;

-- 2. Create Users (CDP Profiles)
INSERT INTO cdp_profiles (tenant_id, profile_id, email, first_name, last_name, segments) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000001', 'alice.tech@test.com', 'Alice', 'TechFan', '["High Growth", "Tech"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000002', 'bob.safe@test.com', 'Bob', 'Conservative', '["Dividend", "Retirement"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000003', 'charlie.crypto@test.com', 'Charlie', 'Degen', '["Crypto", "High Risk"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000004', 'david.trader@test.com', 'David', 'DayTrader', '["Forex", "Active"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000005', 'eve.energy@test.com', 'Eve', 'OilBaron', '["Energy", "Commodities"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000006', 'frank.finance@test.com', 'Frank', 'Banker', '["Finance", "Value"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000007', 'grace.diversified@test.com', 'Grace', 'ETF', '["Balanced"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000008', 'harry.healthcare@test.com', 'Harry', 'Doctor', '["Healthcare"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000009', 'irene.insider@test.com', 'Irene', 'Whale', '["Large Cap"]'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', '00000000-0000-0000-0000-000000000010', 'jack.newbie@test.com', 'Jack', 'Student', '["Learning"]')
ON CONFLICT (profile_id) DO UPDATE 
SET segments = EXCLUDED.segments, email = EXCLUDED.email;

-- 3. Create Instruments (Assets)
INSERT INTO instruments (tenant_id, symbol, name, type, sector) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'AAPL', 'Apple Inc.', 'STOCK', 'Technology'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'MSFT', 'Microsoft Corp.', 'STOCK', 'Technology'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'NVDA', 'Nvidia Corp.', 'STOCK', 'Technology'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'TSLA', 'Tesla Inc.', 'STOCK', 'Automotive'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'AMZN', 'Amazon.com', 'STOCK', 'Consumer Cyclical'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'JPM', 'JPMorgan Chase', 'STOCK', 'Finance'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'BAC', 'Bank of America', 'STOCK', 'Finance'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'V', 'Visa Inc.', 'STOCK', 'Finance'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'JNJ', 'Johnson & Johnson', 'STOCK', 'Healthcare'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'PFE', 'Pfizer Inc.', 'STOCK', 'Healthcare'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'XOM', 'Exxon Mobil', 'STOCK', 'Energy'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'CVX', 'Chevron Corp.', 'STOCK', 'Energy'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'NEE', 'NextEra Energy', 'STOCK', 'Energy'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'BTC', 'Bitcoin', 'CRYPTO', 'Crypto'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'ETH', 'Ethereum', 'CRYPTO', 'Crypto'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'SOL', 'Solana', 'CRYPTO', 'Crypto'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'EURUSD', 'Euro / US Dollar', 'FOREX', 'Forex'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'GBPUSD', 'British Pound / USD', 'FOREX', 'Forex'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'USDJPY', 'USD / Japenese Yen', 'FOREX', 'Forex'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'GOLD', 'Gold Spot', 'COMMODITY', 'Commodities')
ON CONFLICT (tenant_id, symbol) DO UPDATE 
SET name = EXCLUDED.name, sector = EXCLUDED.sector;

-- 4. Create News Events
INSERT INTO news_feed (news_id, tenant_id, title, related_symbols, sentiment_score) VALUES
(1, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Fed Announces Rate Hike', ARRAY['EURUSD', 'JPM', 'GOLD'], -0.5),
(2, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Apple Releases iPhone 16', ARRAY['AAPL'], 0.8),
(3, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Oil Prices Surge Due to Supply Cut', ARRAY['XOM', 'CVX'], 0.7),
(4, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Bitcoin Halving Event Approaches', ARRAY['BTC', 'ETH'], 0.9),
(5, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Tech Sector Hit by Regulation Fears', ARRAY['MSFT', 'NVDA', 'AAPL'], -0.6),
(6, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'New Vaccine Approval Pending', ARRAY['PFE', 'JNJ'], 0.6),
(7, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Bank of America Earnings Beat Estimates', ARRAY['BAC'], 0.5),
(8, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Tesla Gigafactory Expansion Delays', ARRAY['TSLA'], -0.3),
(9, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Crypto Exchange Hack Reported', ARRAY['SOL', 'ETH'], -0.9),
(10, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'USD Strengthens Against Euro', ARRAY['EURUSD'], 0.4),
(11, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Market Rally Continues', ARRAY['AAPL', 'MSFT'], 0.3),
(12, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Inflation Data Concerns', ARRAY['GOLD', 'EURUSD'], -0.4),
(13, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Nvidia AI Chip Demand Soars', ARRAY['NVDA'], 0.9),
(14, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Amazon Prime Day Records', ARRAY['AMZN'], 0.6),
(15, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Visa Transaction Volume Up', ARRAY['V'], 0.2),
(16, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Clean Energy Bill Passed', ARRAY['NEE'], 0.7),
(17, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Healthcare Sector Analysis', ARRAY['JNJ', 'PFE'], 0.1),
(18, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Solana Network Outage', ARRAY['SOL'], -0.8),
(19, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Gold Hits All Time High', ARRAY['GOLD'], 0.8),
(20, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Forex Volatility Alert', ARRAY['GBPUSD', 'USDJPY'], -0.2),
(21, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Microsoft Cloud Growth', ARRAY['MSFT'], 0.5),
(22, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Exxon Discovery in Guyana', ARRAY['XOM'], 0.4),
(23, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Global Supply Chain Issues', ARRAY['AAPL', 'TSLA'], -0.4),
(24, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Interest Rate Decision Tomorrow', ARRAY['JPM', 'BAC'], 0.0),
(25, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Ethereum 2.0 Updates', ARRAY['ETH'], 0.6),
(26, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Consumer Spending Slows', ARRAY['AMZN'], -0.3),
(27, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Chevron Dividends Increase', ARRAY['CVX'], 0.3),
(28, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'NextEra Wind Projects', ARRAY['NEE'], 0.5),
(29, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Yen Weakens further', ARRAY['USDJPY'], 0.3),
(30, 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Tech Layouts Resume', ARRAY['MSFT', 'AMZN'], -0.5)
ON CONFLICT (news_id) DO UPDATE 
SET title = EXCLUDED.title, sentiment_score = EXCLUDED.sentiment_score;

-- ============================================================
-- B. GRAPH DATA (APACHE AGE)
-- ============================================================

-- 1. Create Graph (Idempotent Check)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM ag_catalog.ag_graph 
        WHERE name = 'investing_knowledge_graph'
    ) THEN
        PERFORM ag_catalog.create_graph('investing_knowledge_graph');
    END IF;
END $$;

-- 2. Create/Update Graph Nodes (Using MERGE for Idempotency)
-- 'MERGE' ensures we don't create duplicates if run twice.

 -- Create Users
SELECT * FROM ag_catalog.cypher('investing_knowledge_graph', $$
    MERGE (:User {id: '00000000-0000-0000-0000-000000000001', name: 'Alice'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000002', name: 'Bob'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000003', name: 'Charlie'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000004', name: 'David'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000005', name: 'Eve'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000006', name: 'Frank'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000007', name: 'Grace'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000008', name: 'Harry'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000009', name: 'Irene'})
    MERGE (:User {id: '00000000-0000-0000-0000-000000000010', name: 'Jack'})
$$) as (a agtype);

 -- Create Sectors
SELECT * FROM ag_catalog.cypher('investing_knowledge_graph', $$
    MERGE (:Sector {name: 'Technology'})
    MERGE (:Sector {name: 'Finance'})
    MERGE (:Sector {name: 'Healthcare'})
    MERGE (:Sector {name: 'Energy'})
    MERGE (:Sector {name: 'Crypto'})
    MERGE (:Sector {name: 'Forex'})
    MERGE (:Sector {name: 'Automotive'})
    MERGE (:Sector {name: 'Commodities'})
$$) as (a agtype);

-- 3. Create Asset Nodes & Sector Links
 -- Match Sectors, Merge Assets and Relationships
SELECT * FROM ag_catalog.cypher('investing_knowledge_graph', $$
   
    MATCH (t:Sector {name: 'Technology'}), (f:Sector {name: 'Finance'}),
          (h:Sector {name: 'Healthcare'}), (e:Sector {name: 'Energy'}),
          (c:Sector {name: 'Crypto'})
    
    MERGE (aapl:Asset {symbol: 'AAPL', name: 'Apple'}) MERGE (aapl)-[:BELONGS_TO]->(t)
    MERGE (msft:Asset {symbol: 'MSFT', name: 'Microsoft'}) MERGE (msft)-[:BELONGS_TO]->(t)
    MERGE (nvda:Asset {symbol: 'NVDA', name: 'Nvidia'}) MERGE (nvda)-[:BELONGS_TO]->(t)
    MERGE (jpm:Asset {symbol: 'JPM', name: 'JPMorgan'}) MERGE (jpm)-[:BELONGS_TO]->(f)
    MERGE (btc:Asset {symbol: 'BTC', name: 'Bitcoin'}) MERGE (btc)-[:BELONGS_TO]->(c)
    MERGE (eth:Asset {symbol: 'ETH', name: 'Ethereum'}) MERGE (eth)-[:BELONGS_TO]->(c)
    MERGE (pfe:Asset {symbol: 'PFE', name: 'Pfizer'}) MERGE (pfe)-[:BELONGS_TO]->(h)
    MERGE (xom:Asset {symbol: 'XOM', name: 'Exxon'}) MERGE (xom)-[:BELONGS_TO]->(e)
$$) as (a agtype);

-- 4. Create Relationships (HOLDS / WATCHES)
-- Create/Merge Edges
SELECT * FROM ag_catalog.cypher('investing_knowledge_graph', $$
    MATCH (alice:User {name: 'Alice'}), (bob:User {name: 'Bob'}), (charlie:User {name: 'Charlie'}),
          (aapl:Asset {symbol: 'AAPL'}), (msft:Asset {symbol: 'MSFT'}), 
          (btc:Asset {symbol: 'BTC'}), (jpm:Asset {symbol: 'JPM'}), (xom:Asset {symbol: 'XOM'})

    MERGE (alice)-[:HOLDS]->(aapl)
    MERGE (alice)-[:WATCHES]->(msft)
    MERGE (bob)-[:HOLDS]->(jpm)
    MERGE (bob)-[:WATCHES]->(xom)
    MERGE (charlie)-[:HOLDS]->(btc)
    MERGE (charlie)-[:WATCHES]->(aapl)
$$) as (a agtype);

-- 5. Create News & Impacts
-- Merge News Events and Merge Impacts
SELECT * FROM ag_catalog.cypher('investing_knowledge_graph', $$
    MATCH (tech:Sector {name: 'Technology'}), 
          (fin:Sector {name: 'Finance'}),
          (crypto:Sector {name: 'Crypto'})

    MERGE (n1:NewsEvent {id: 1, title: 'Fed Rate Hike'})
    MERGE (n5:NewsEvent {id: 5, title: 'Tech Regulation'})

    MERGE (n1)-[:IMPACTS {sentiment: 'negative'}]->(fin)
    MERGE (n1)-[:IMPACTS {sentiment: 'negative'}]->(crypto)
    MERGE (n5)-[:IMPACTS {sentiment: 'negative'}]->(tech)
$$) as (a agtype);

-- ============================================================
-- C. MANUAL TEST SCENARIO
-- ============================================================

-- Create a rule for Alice to test the Minute Worker
INSERT INTO alert_rules (tenant_id, profile_id, symbol, alert_type, condition_logic, status)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 
    '00000000-0000-0000-0000-000000000001', 
    'AAPL', 'PRICE', '{"operator": ">", "value": 150}', 'ACTIVE'
)
ON CONFLICT DO NOTHING;

-- Simulate Market Price update
INSERT INTO market_snapshot (symbol, price) VALUES ('AAPL', 155.00)
ON CONFLICT (symbol) DO UPDATE SET price = 155.00;

-- Verification Message
DO $$
BEGIN
    RAISE NOTICE 'Test Data Generation Complete. Run verification query to test.';
END $$;