---
marp: true
title: LEO Activation – Kế Hoạch Triển Khai POC 12 Ngày
theme: default
paginate: true
header: 'LEO Activation (POC) • Sprint Plan v2.2 (VN)'
footer: 'Jan 08, 2026'
style: |
  section { font-size: 22px; }
  h1 { color: #2d3436; }
  h2 { color: #0984e3; }
  strong { color: #d63031; }
  code { background: #f1f2f6; color: #e17055; padding: 2px 5px; border-radius: 4px; }
---

# LEO Activation Platform
## Kế Hoạch Triển Khai POC 12 Ngày

**Mục tiêu:** Xây dựng "Bộ não & Cơ bắp" AI-first cho LEO CDP.  
**Core Tech:** FunctionGemma (AI), PostgreSQL 16 (Core), Celery (Async).  
**Ràng buộc:** 12 ngày phải có Demo.

**Owner:** Product & Engineering  
**Ngày:** 8/1/2026

> **"Code wins arguments. Ship it."**


<!--
Speaker Notes:
Slide mở đầu. Nói rõ đây là POC có deadline cứng.
Không bàn mở rộng scope. Không tranh luận tool.
Mục tiêu duy nhất: ship được hệ activation chạy thật.
-->

---

## Product Vision – LEO Activation

**LEO Activation không phải là hệ gửi thông báo.**  
Nó là **Decision & Execution Engine** nằm giữa CDP và các kênh.

### Chúng ta muốn giải quyết điều gì?

- CDP hiện nay **biết rất nhiều**, nhưng **làm rất ít**
- Campaign được thiết kế thủ công, **chậm và không phản hồi theo ngữ cảnh**
- Multi-channel tồn tại, nhưng **không có “bộ não” điều phối** tự động cho **personalization** theo từng profile

### LEO Activation tồn tại để:

- Biến **dữ liệu → quyết định → hành động** trong *thời gian đúng*
- Cho phép **AI ra quyết định có kiểm soát**, không phải đoán mò
- Mọi hành động activation đều **trace logs được – audit logs được – giải thích được lý do hành động**

> **Activation không phải là gửi tin.  
> Activation là chọn đúng hành động, cho đúng người, vào đúng thời điểm.**

<!--
Speaker Notes:
Slide này là để thống nhất tư duy trước khi xem kiến trúc.
LEO Activation không cạnh tranh với tool gửi tin.
Nó cạnh tranh với sự chậm chạp và thủ công trong việc ra quyết định.
Nếu audience chỉ nhớ 1 điều:
Activation = decision system, không phải messaging system.
-->


---

![bg right:55% fit](../leo-activation-framework.png)

## Bức tranh tổng thể  về Flow

1. **Ingest (Thu thập):** Đồng bộ dữ liệu từ LEO CDP (ArangoDB) → Postgres.  
2. **Think (Tư duy):** FunctionGemma phân tích Profile + Context → Quyết định "Làm gì".  
3. **Target (Nhắm mục tiêu):** Snapshot Segment (bất biến).  
4. **Act (Hành động):** Dispatch tới các kênh (Chat, Zalo, Facebook, Email, Web Push, App Push).

<!--
Speaker Notes:
Slide này để mọi người cùng nhìn một bản đồ.
Không đi chi tiết kỹ thuật.
Chỉ cần hiểu activation là một luồng xuyên suốt, không phải 1 service lẻ.
-->

---

## Timeline Sprint (12 Ngày)

* **Phase 1: Nền tảng (Ngày 1-3)**
* **Phase 2: Bộ não AI (Ngày 4-7)**
* **Phase 3: Cơ bắp thực thi (Ngày 8-10)**
* **Phase 4: Ổn định hóa (Ngày 11-12)**

<!--
Speaker Notes:
Timeline này khóa cứng.
Không có chuyện “làm song song cho nhanh” nếu chưa xong phase dưới.
-->

---

# Phase 1: Nền tảng (Ngày 1-3)
## Mục tiêu: Cấu trúc database chuẩn, đầy đủ và tin cậy để scale.

<!--
Speaker Notes:
Phase này không sexy nhưng quyết định toàn bộ hệ.
Nếu nền sai, AI phía trên chỉ là diễn.
-->

---

## [LEO Activation – 01] Khởi tạo Database & Extensions

**WHY – Vì sao task này tồn tại?**  
Activation là hệ thống ghi nhận sự thật. Nếu schema sai, mọi quyết định AI phía trên đều sai nhưng không ai biết.

**Mô tả:**  
Khởi tạo PostgreSQL 16 với schema production đã cung cấp. Đảm bảo kích hoạt đầy đủ extensions (`vector`, `pgcrypto`).

**Technical Tasks:**
1. Chạy `schema.sql` với Postgres instance.  
2. Kiểm tra Partitioning trên bảng `marketing_event`.  
3. Kiểm tra RLS (Row Level Security).

**Definition of Done (DoD):**
- [ ] `\d marketing_event` hiển thị đủ 16 partitions.  
- [ ] Insert vào `cdp_profiles` chỉ thành công khi có `tenant_id` hợp lệ.  
- [ ] Trigger `update_timestamp()` hoạt động đúng.

<!--
Speaker Notes:
Partition và RLS là hai thứ không sửa muộn được.
Làm đúng ngay từ POC thì production mới đỡ đau.
-->

---

## [LEO Activation – 02] Worker Đồng bộ Dữ liệu (ArangoDB → Postgres)

**WHY – Vì sao task này tồn tại?**  
Activation runtime không được phụ thuộc GraphDB. Mọi quyết định phải chạy trên dữ liệu đã ổn định.

**Mô tả:**  
Xây dựng Celery worker để kéo dữ liệu profile từ LEO CDP ArangoDB và upsert vào bảng `cdp_profiles` của Activation.

**Technical Tasks:**
1. Tạo `SyncProfileWorker`.  
2. Map các thuộc tính từ Arango sang Postgres.  
3. Xử lý logic `ON CONFLICT (tenant_id, ext_id)`.

**Definition of Done (DoD):**
- [ ] Độ trễ Sync < 200ms cho batch 100 profiles.  
- [ ] JSONB query được qua GIN index.  
- [ ] Không sinh ra profile trùng lặp.

<!--
Speaker Notes:
Đây là mạch máu.
Sync sai = AI sai = activation sai.
-->

---

## [LEO Activation – 03] Segment Snapshot Engine

**WHY – Vì sao task này tồn tại?**  
Không snapshot thì không audit được. Không audit thì không giải thích được.

**Mô tả:**  
Implement logic "đóng băng". Khi campaign kích hoạt, hệ thống phải ghi lại chính xác ai đang ở trong segment tại thời điểm đó.

**Technical Tasks:**
1. API: `POST /snapshot/create`.  
2. Query profiles → insert snapshot → insert members.  
3. Kiểm tra trigger `prevent_snapshot_removal`.

**Definition of Done (DoD):**
- [ ] Tạo snapshot cho 10k profiles trong < 2 giây.  
- [ ] Cố tình xóa snapshot bị DB reject.  
- [ ] `snapshot_id` link đúng với `tenant_id`.

<!--
Speaker Notes:
Snapshot là bằng chứng.
Sau này khách hỏi “vì sao tôi nhận tin”, câu trả lời nằm ở đây.
-->

---

# Phase 2: Bộ não AI (Ngày 4-7)
## Mục tiêu: Text-to-Function & Truy vết Quyết định.

<!--
Speaker Notes:
AI không chỉ trả lời cho vui.
AI phải ra quyết định có log, có trách nhiệm.
-->

---

## [LEO Activation – 04] FunctionGemma Model Service

**WHY – Vì sao task này tồn tại?**  
Marketing không viết code. AI phải dịch ngôn ngữ tự nhiên thành hành động có cấu trúc trong Python.

**Mô tả:**  
Deploy FunctionGemma model (qua API wrapper) để dịch intent marketing thành các function call có cấu trúc.

**Technical Tasks:**
1. Setup LLM Gateway.  
2. Định nghĩa Tools/Functions Schema.  
3. Implement Prompt Template sử dụng context từ `cdp_profiles`.

**Definition of Done (DoD):**
- [ ] Text → JSON Function Call đúng cú pháp.  
- [ ] Latency < 2s.

<!--
Speaker Notes:
Không quan tâm AI nói hay.
Chỉ quan tâm AI gọi đúng hàm.
-->

---

## [LEO Activation – 05] Agent Task Orchestrator

**WHY – Vì sao task này tồn tại?**  
AI không lifecycle, trạng thái và trace thì trở thành hộp đen — không debug, không audit, không kiểm soát được.

**Mô tả:**  
Vòng lặp cốt lõi quản lý vòng đời của một tác vụ AI, sử dụng bảng `agent_task`.

**Technical Tasks:**
1. API `POST /activate/agent`.  
2. Tạo record `agent_task`.  
3. Lưu `reasoning_trace` & `reasoning_summary`.  
4. Retry logic.

**Definition of Done (DoD):**
- [ ] Lưu được trace suy luận.  
- [ ] Retry tối đa 3 lần.  
- [ ] RLS đúng tenant.

<!--
Speaker Notes:
Agent Task là nhật ký suy nghĩ của AI.
Debug AI = đọc bảng này.
-->

---

# Phase 3: Cơ bắp thực thi (Ngày 8-10)

---

## [LEO Activation – 06] Unified Dispatcher & Delivery Log

**WHY – Vì sao task này tồn tại?**  
Không có delivery log thì không có sự thật.

**Mô tả:**  
Lớp trừu tượng điều phối lệnh tới các channel adapter và ghi log kết quả.

**Technical Tasks:**
1. Dispatcher (Factory).  
2. Ghi log trước & sau khi gửi.  
3. Deterministic `event_id`.

**Definition of Done (DoD):**
- [ ] Log đủ status & response.  
- [ ] Fail log → không gửi.

<!--
Speaker Notes:
Tin log, không tin lời kể.
-->

---

## [LEO Activation – 07] Channel Adapter: Zalo OA & Email

**WHY – Vì sao task này tồn tại?**  
Việt Nam = Zalo + Email. Không làm tốt thì demo không thuyết phục.

**Mô tả:**  
Implement các connector cụ thể cho thị trường Việt Nam.

**Technical Tasks:**
- Zalo Adapter.  
- Email Adapter.  
- Chuẩn hóa số điện thoại.

**Definition of Done (DoD):**
- [ ] Gửi ZNS thành công.  
- [ ] Số rác không crash worker.

<!--
Speaker Notes:
Test cả case xấu nhất.
Channel hay chết vì lỗi bẩn.
-->

---



## [LEO Activation – 08] Channel Adapter: Facebook Page

**WHY – Vì sao task này tồn tại?**  
Facebook Page vẫn là kênh CSKH và remarketing quan trọng. 

**Mô tả:**  
Implement adapter gửi tin nhắn qua Facebook Page API, phục vụ các use case CSKH và campaign remarketing.

**Technical Tasks:**
1. Tích hợp Facebook Page Messaging API.
2. Quản lý Page Access Token (expire / refresh).
3. Mapping `psid` từ `cdp_profiles`.
4. Xử lý lỗi phổ biến: token expired, permission denied, rate limit.

**Definition of Done (DoD):**
- [ ] Gửi message thành công tới Page Inbox.
- [ ] Token hết hạn phải log rõ lỗi, không crash worker.
- [ ] `delivery_log` ghi nhận đầy đủ response từ Meta API.

<!--
Speaker Notes:
FB Page API rất hay chết vì token và permission.
Phải log đủ để phân biệt lỗi hệ hay lỗi Meta.
Không được trộn FB logic chung với Zalo hay Email.
-->

---

## [LEO Activation – 09] Channel Adapter: Push & Telegram

**WHY – Vì sao task này tồn tại?**  
Realtime channel cho thấy hệ còn sống.

**Mô tả:**  
Các kênh thông báo thời gian thực.

**Technical Tasks:**
1. Telegram Bot API.  
2. Push (FCM / PushAlert).  
3. Queue riêng.

**Definition of Done (DoD):**
- [ ] Push < 1s.  
- [ ] Telegram không lỗi Markdown.

<!--
Speaker Notes:
Realtime trả lời chậm = cảm giác hệ đang chết hay status = down 
-->

---

# Phase 4: Ổn định hóa (Ngày 11-12)

---

## [LEO Activation – 10] End-to-End Traceability Test

**WHY – Vì sao task này tồn tại?**  
Hệ không trace được = không vận hành được.

**Mô tả:**  
Kiểm chứng "Luồng vàng" từ Event tới Delivery Log.

**Definition of Done (DoD):**
- [ ] 1 query join ra full journey.  
- [ ] Không orphan log.

<!--
Speaker Notes:
Đây là bài test cho CTO.
-->

---

## [LEO Activation – 11] Load Testing & Documentation

**WHY – Vì sao task này tồn tại?**  
Demo không được sập.

**Mô tả:**  
Đảm bảo hệ thống chịu được tải Demo POC.

**Definition of Done (DoD):**
- [ ] 5k events/phút ổn định.  
- [ ] API error < 1%.

<!--
Speaker Notes:
Load test để ngủ ngon trước demo.
-->

---

## Hành động ngay (Day 0)

1. **Chốt phạm vi POC & đóng scope**
   - Freeze danh sách tính năng trong tài liệu này. Nếu có yêu cầu mới → đưa sang phase sau POC.

2. **Dựng hạ tầng nền (Postgres + Queue)**
   - Provision PostgreSQL 16 + bật extensions cần thiết, khởi tạo Celery broker & worker skeleton.

3. **Verify schema & chiến lược partition**
   - Lead Dev review `schema.sql`, đặc biệt bảng `marketing_event`. Xác nhận partition, index, RLS chạy đúng ngay từ đầu.

4. **Chuẩn hoá contract dữ liệu & API**
   - Chốt format `cdp_profiles`, `agent_task`, `delivery_log`. Freeze request/response cho các API chính.

5. **Tạo backlog & phân công rõ ràng**
   - Đẩy toàn bộ task `[LEO Activation – xx]` vào Jira. 
   - Gán owner rõ cho từng ticket trước khi bắt đầu Day 1.

