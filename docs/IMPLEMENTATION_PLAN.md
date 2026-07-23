# Kế Hoạch Triển Khai

## Milestone 0 — Repository scaffold

Tạo các thư mục bắt buộc `src/`, `tests/`, `logs/`, và `config/`; thêm hướng dẫn README root và một lệnh test duy nhất. Commit fixture khóa validator xác định và file kịch bản. **Định nghĩa hoàn thành:** kịch bản no-op chạy được và tạo ra canonical log.

## Milestone 1 — Các primitive xác định

Triển khai canonical encoding, SHA-256 helpers, Ed25519 signing/verification, identity fixtures, transactions, sorted-state hashing, và deterministic executor. **Định nghĩa hoàn thành:** unit test crypto/state pass và cùng một block thực thi hai lần cho byte/hash giống nhau.

## Milestone 2 — Xác thực dữ liệu và lưu trữ

Triển khai headers, bodies, vote objects, block store, ledger snapshot, và tất cả validation guards theo đặc tả giao thức. Thực thi quy tắc header-first body acceptance. **Định nghĩa hoàn thành:** dữ liệu không hợp lệ không thể thay đổi trạng thái đang chờ hoặc đã finalize; block validation test suite pass.

## Milestone 3 — Mạng xác định

Triển khai envelope routing, logical scheduler, seeded fault injection, giới hạn băng thông/rate limits, chặn peer tạm thời, và canonical event logs. **Định nghĩa hoàn thành:** chuỗi giao gói đã scripted — kể cả thông điệp trùng/sắp xếp lại — replay giống hệt nhau.

## Milestone 4 — Đồng thuận và khôi phục

Triển khai proposer selection, prevote/precommit guards, quorum accounting, locks, round timeouts, finalization, crash/restart từ snapshot đã finalize, và gossip. **Định nghĩa hoàn thành:** T1, T2, T5, T6, T7 pass với runtime safety assertions bật.

## Milestone 5 — Bằng chứng và nộp bài

Hoàn thành T3, T4, T8; thêm tóm tắt kịch bản; viết `REPORT.pdf` từ kết quả test thực tế; xác nhận cấu trúc folder và tên ZIP. **Định nghĩa hoàn thành:** checkout sạch có thể chạy mọi test từ lệnh đã ghi và tạo ra tất cả artifacts bắt buộc.

## Gợi ý phân chia luồng công việc

| Luồng | Đầu ra | Phụ thuộc vào |
|---|---|---|
| Primitives | encoding, crypto, state, fixtures | không có |
| Simulation | scheduler, network, logs, scenarios | canonical event schema |
| Consensus | vote set, locking, rounds, finalization | primitives + network interface |
| QA/reporting | test harness, reproducibility checker, bằng chứng báo cáo | tất cả luồng |

## Nguyên tắc phát triển

- Coi bất kỳ lặp không xác định, đọc clock, gọi random, hay serializer default nào là defect trừ khi được kiểm soát tường minh.
- Giữ consensus mutation single-threaded dưới simulator scheduler; parallelism không cần thiết cho bài này và làm phức tạp reproducibility.
- Thêm test trước khi nới lỏng validation guard hoặc thay đổi encoded fields.
- Ghi version đặc tả và fingerprint cấu hình vào mọi log để kết quả luôn giải thích được.
