# Yêu Cầu và Phạm Vi

## Mục tiêu

Xây dựng một blockchain Layer-1 tối giản dạng mô phỏng (simulator), trong đó các validator đúng đắn hội tụ về một chuỗi block đã finalize dù thông điệp bị trễ, trùng lặp, sắp xếp lại hoặc bị rớt tạm thời. Một node đúng đắn **không bao giờ** được finalize hai block khác nhau ở cùng một chiều cao. Sau khi mạng ổn định, chuỗi phải tiến triển khi một proposer đúng đắn cuối cùng được chọn.

## Trong phạm vi

- Tập validator cố định cho mỗi lần chạy, thỏa `n = 3f + 1`; hỗ trợ ít nhất tám node.
- Giao dịch, header và vote được ký số; khóa công khai và `chain_id` cố định cho mỗi lần chạy.
- Thực thi trạng thái key-value xác định (deterministic) và cam kết trạng thái (state commitment) trong mỗi header.
- Mạng P2P mô phỏng với delay, giới hạn băng thông/tốc độ, nhân bản thông điệp, sắp xếp lại, rớt, và chặn peer tạm thời — đều có thể cấu hình.
- Truyền header trước (header-first propagation): body chỉ được chấp nhận sau khi header tương ứng đã được chấp nhận.
- Bỏ phiếu hai pha (`PREVOTE`, `PRECOMMIT`), locking, rounds, timeouts và finalization.
- Log sự kiện có cấu trúc, unit test, kịch bản end-to-end, và một điểm vào kiểm thử duy nhất có thể tái tạo.

## Ngoài phạm vi

- Tập validator động, staking, kinh tế token, phí gas, smart contract, thực thi song song, và mạng socket thực.
- Lưu trữ cấp độ production hoặc tạo khóa ngẫu nhiên mật mã bên trong simulator.
- Merkle Patricia Trie đầy đủ — hash chuẩn của toàn bộ trạng thái đã sắp xếp là đủ cho bài lab này.

## Tiêu chí chấp nhận

| Hạng mục | Kết quả yêu cầu |
|---|---|
| An toàn | Không có hai block finalize khác nhau tại cùng một chiều cao giữa các node đúng đắn, kể cả trước khi có synchrony. |
| Hoạt động | Sau điểm ổn định và khi chọn được proposer đúng đắn, một chiều cao sau đó phải được finalize. |
| Hợp lệ | Parent không hợp lệ, proposer sai, chữ ký/domain sai, giao dịch sai, state hash sai, hoặc trường vote sai đều bị từ chối và ghi log. |
| Kiểm đếm vote | Vote trùng lặp không tăng trọng số; chỉ một vote hợp lệ mỗi validator cho mỗi `(height, round, phase)`. |
| Tất định | Cùng kịch bản/cấu hình/seed tạo ra log byte-identical và state hash cuối giống nhau trên hai lần chạy. |
| Bằng chứng | T1–T8 từ đề bài đều pass từ một lệnh duy nhất. |
| Nộp bài | Bao gồm `src/`, `tests/`, `logs/`, `config/`, `README.md`, và `REPORT.pdf` tối đa 10 trang trong folder đặt tên theo tên nhóm. |

## Truy xuất nguồn gốc yêu cầu

| Yêu cầu bài Lab | Tài liệu chính | Kiểm tra bằng |
|---|---|---|
| Mật mã và mã hóa xác định | Đặc tả giao thức | Unit test mật mã và serialization |
| Mạng không đáng tin cậy và quy tắc header-first | Kiến trúc | Integration test mạng |
| Quy tắc locking/vote | Đặc tả giao thức | Unit test consensus + T2/T5/T7 |
| Thực thi xác định | Đặc tả giao thức | Unit test trạng thái + T8 |
| Log và lệnh kiểm thử tái tạo | Đặc tả kiểm thử | T1–T8 và script rerun |

## Các lựa chọn cần quyết định trước khi code

Baseline dùng Ed25519 và canonical JSON-like bytes theo đặc tả giao thức. Nếu ngôn ngữ lập trình không đảm bảo serializer ổn định, hãy triển khai bộ mã hóa nhị phân tường minh thay thế. Chọn dung lượng block mặc định, lịch timeout, và chính sách lưu giữ dữ liệu trong `config/default.json` (hoặc file cấu hình tương đương); mỗi giá trị này phải được đưa vào fingerprint kịch bản được ghi vào log.
