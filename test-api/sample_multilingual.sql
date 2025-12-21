-- ============================================================
-- Multilingual Sample Data (Vietnam)
-- Domains: Travel & Stock Trading Education
-- Languages: Vietnamese + English
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Tenants
-- ============================================================

INSERT INTO tenant (tenant_id, tenant_name)
VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'VietTravel Academy'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'VN Stock Learning Hub')
ON CONFLICT (tenant_id) DO NOTHING;


-- ============================================================
-- 2. Travel & Tourism (Multilingual)
-- ============================================================

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
    -- Vietnamese first, English second (natural bilingual pattern)
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'Du lịch Phú Quốc mùa hè | Phu Quoc Summer Travel',
    'Chương trình du lịch Phú Quốc mùa hè dành cho gia đình và nhóm bạn trẻ. 
     Ưu đãi combo vé máy bay và khách sạn, trải nghiệm biển đảo, ẩm thực địa phương. 
     Summer travel program to Phu Quoc Island with flight and hotel packages, beach activities, and local food experiences.',
    'travel_campaign',
    'facebook',
    now() + interval '10 days',
    now() + interval '40 days',
    'Phu Quoc, Vietnam',
    'https://viettravel.example.com/phu-quoc-summer',
    'PQSUMMER25',
    'Gia đình trẻ, nhóm bạn, khách du lịch nội địa',
    60000,
    'Travel Marketing',
    'marketing@viettravel.example.com',
    'planned'
),
(
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'Tour miền Trung di sản | Central Vietnam Heritage Tour',
    'Hành trình khám phá Huế, Đà Nẵng và Hội An với hướng dẫn viên chuyên nghiệp.
     Cultural heritage tour covering Hue, Da Nang, and Hoi An, focusing on history, architecture, and local culture.',
    'travel_campaign',
    'website',
    now() + interval '20 days',
    now() + interval '50 days',
    'Hue – Da Nang – Hoi An',
    'https://viettravel.example.com/central-heritage',
    'HERITAGE25',
    'Khách du lịch yêu văn hóa và lịch sử',
    45000,
    'Tour Operations',
    'ops@viettravel.example.com',
    'planned'
);


-- ============================================================
-- 3. Stock Trading & Investment Education (Multilingual)
-- ============================================================

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
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'Đầu tư chứng khoán cơ bản | Stock Market Fundamentals',
    'Khóa học nhập môn đầu tư chứng khoán dành cho người mới bắt đầu tại Việt Nam.
     Nội dung bao gồm cách đọc báo cáo tài chính, quản lý rủi ro và tâm lý đầu tư.
     Beginner-friendly stock investment course covering financial statements, risk management, and investor psychology.',
    'education',
    'webinar',
    now() + interval '7 days',
    now() + interval '7 days' + interval '3 hours',
    'Online',
    'https://vnstock.example.com/fundamentals',
    'STOCK101',
    'Nhà đầu tư cá nhân mới, sinh viên kinh tế',
    8000,
    'Education Team',
    'edu@vnstock.example.com',
    'planned'
),
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'Phân tích kỹ thuật cổ phiếu | Technical Analysis Workshop',
    'Workshop chuyên sâu về phân tích kỹ thuật cổ phiếu Việt Nam.
     Học cách sử dụng biểu đồ giá, chỉ báo RSI, MACD và chiến lược vào lệnh.
     Advanced workshop on technical analysis using price charts, RSI, MACD, and entry strategies.',
    'education',
    'offline',
    now() + interval '15 days',
    now() + interval '15 days' + interval '5 hours',
    'Ho Chi Minh City',
    NULL,
    'TA2025',
    'Nhà đầu tư cá nhân trung cấp',
    12000,
    'Trading Education',
    'trading@vnstock.example.com',
    'planned'
),
(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'Quản lý rủi ro & tâm lý giao dịch | Risk Management and Trading Psychology',
    'Chương trình đào tạo tập trung vào quản lý rủi ro và kiểm soát cảm xúc khi giao dịch chứng khoán.
     Training program focused on risk control, position sizing, and emotional discipline in trading.',
    'education',
    'youtube',
    now() + interval '5 days',
    now() + interval '35 days',
    'Vietnam',
    'https://youtube.com/@vnstockacademy',
    'RISK2025',
    'Nhà đầu tư đang giao dịch thường xuyên',
    15000,
    'Content Team',
    'content@vnstock.example.com',
    'active'
);

-- ============================================================
-- 4. Sanity Checks (optional)
-- ============================================================

-- Expect multilingual embedding text
-- SELECT embedding_text FROM event_content_for_embedding LIMIT 5;

-- Expect embedding jobs auto-created
-- SELECT status, COUNT(*) FROM embedding_job GROUP BY status;

COMMIT;
