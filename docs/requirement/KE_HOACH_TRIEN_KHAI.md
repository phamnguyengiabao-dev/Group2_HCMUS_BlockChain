# Kế Hoạch Triển Khai

## Tổng quan các Milestone

| Milestone | Tên | Phụ thuộc |
|---|---|---|
| M0 | Repository scaffold | — |
| M1 | Các primitive xác định | M0 |
| M2 | Xác thực dữ liệu và lưu trữ | M1 |
| M3 | Mạng xác định | M2 |
| M4 | Đồng thuận và khôi phục | M3 |
| M5 | Bằng chứng và nộp bài | M4 |

---

## Milestone 0 — Repository Scaffold

**Mục tiêu:** Tạo cấu trúc thư mục và điểm vào kiểm thử.

**Công việc:**
- Tạo thư mục bắt buộc: `src/`, `tests/`, `logs/`, `config/`
- Thêm README root với hướng dẫn và một lệnh test duy nhất
- Commit các fixture khóa validator xác định và file kịch bản
- Tạo cấu hình mặc định `config/default.json`

**Định nghĩa hoàn thành:** Kịch bản no-op chạy được và tạo ra canonical log.

---

## Milestone 1 — Các Primitive Xác Định

**Mục tiêu:** Nền tảng mật mã và thực thi xác định.

**Công việc:**
- Canonical encoding (mã hóa nhị phân theo đặc tả)
- SHA-256 helpers
- Ed25519 signing và verification
- Identity fixtures (khóa kiểm thử cố định)
- Transaction object và xác thực
- Sorted-state hashing
- Deterministic executor

**Định nghĩa hoàn thành:** Unit test crypto/state pass; cùng một block thực thi hai lần cho byte/hash giống nhau.

---

## Milestone 2 — Xác Thực Dữ Liệu và Lưu Trữ

**Mục tiêu:** Toàn bộ data model và các guard xác thực.

**Công việc:**
- Block header object
- Block body object
- Vote object
- Block store (lưu header và body)
- Ledger snapshot
- Tất cả validation guards theo đặc tả giao thức
- Thực thi quy tắc header-first (body chỉ nhận sau header)

**Định nghĩa hoàn thành:** Dữ liệu không hợp lệ không thể thay đổi trạng thái đang chờ hoặc đã finalize; block validation test suite pass.

---

## Milestone 3 — Mạng Xác Định

**Mục tiêu:** Simulated network với fault injection.

**Công việc:**
- Envelope routing
- Logical scheduler (priority queue `(logical_time, insertion_sequence)`)
- Seeded fault injection (drop, delay, duplicate, reorder)
- Giới hạn băng thông và rate limit
- Chặn peer tạm thời (peer blocking)
- Canonical event logs (JSON Lines)

**Định nghĩa hoàn thành:** Chuỗi giao gói đã scripted — kể cả thông điệp trùng/sắp xếp lại — replay giống hệt nhau.

---

## Milestone 4 — Đồng Thuận và Khôi Phục

**Mục tiêu:** Consensus engine đầy đủ và crash recovery.

**Công việc:**
- Proposer selection (`(height + round) mod n`)
- Prevote guard và quorum accounting
- Precommit guard
- Locking và lock tracking
- Round timeout
- Finalization
- Crash/restart từ snapshot đã finalize
- Gossip service

**Định nghĩa hoàn thành:** T1, T2, T5, T6, T7 pass với runtime safety assertions bật.

---

## Milestone 5 — Bằng Chứng và Nộp Bài

**Mục tiêu:** Hoàn thiện test và đóng gói nộp bài.

**Công việc:**
- Hoàn thành T3, T4, T8
- Thêm tóm tắt kịch bản
- Viết `REPORT.pdf` từ kết quả test thực tế (tối đa 10 trang)
- Xác nhận cấu trúc folder và đặt tên ZIP
- Đảm bảo checkout sạch có thể chạy mọi test từ một lệnh

**Định nghĩa hoàn thành:** Checkout sạch có thể chạy mọi test từ lệnh đã ghi và tạo ra tất cả artifacts bắt buộc.

---

## Nguyên tắc phát triển (Development Guardrails)

| Nguyên tắc | Mô tả |
|---|---|
| **Xác định tuyệt đối** | Lặp không xác định, đọc clock, gọi random, hay serializer default đều là defect trừ khi được kiểm soát tường minh |
| **Single-threaded consensus** | Giữ consensus mutation single-threaded dưới simulator scheduler; parallelism không cần thiết và làm phức tạp reproducibility |
| **Test trước khi relaxing** | Thêm test trước khi nới lỏng validation guard hoặc thay đổi encoded fields |
| **Fingerprint kịch bản** | Ghi version đặc tả và fingerprint cấu hình vào mọi log để kết quả luôn giải thích được |
