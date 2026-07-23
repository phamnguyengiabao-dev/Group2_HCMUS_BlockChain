# Đặc Tả Kiểm Thử và Bằng Chứng

## Hợp đồng thực thi kiểm thử

- Cung cấp **một lệnh duy nhất** (ghi trong README root) chạy toàn bộ unit test và end-to-end test.
- Lệnh phải trả về non-zero khi có bất kỳ thất bại nào.
- Ghi log từng kịch bản vào `logs/<scenario>/<run-id>.jsonl`.
- Lệnh thứ hai (hoặc `--verify-determinism`) chạy kịch bản **hai lần** với cùng cấu hình và so sánh byte log thô cùng state hash cuối.

**Mỗi cấu hình kịch bản phải khai báo:**
`chain_id`, seed, validator keys/order, hành vi Byzantine, fixture giao dịch, topology, phân phối delay, giới hạn băng thông/tốc độ, kế hoạch drop/duplicate/reordering, logical time ổn định, và lịch timeout.

---

## Ma trận kiểm thử end-to-end bắt buộc (T1–T8)

| ID | Kịch bản | Kiểm tra |
|---|---|---|
| **T1** | Chạy bình thường, không có lỗi | Mọi node đúng đắn finalize các height, hash và state hash cuối giống nhau. |
| **T2** | Thông điệp trùng lặp và sắp xếp lại | Mỗi tuple vote đếm tối đa một validator; không có finalization xung đột. |
| **T3** | Chữ ký không hợp lệ và domain sai | Router từ chối thông điệp, ghi lý do, không có chuyển đổi state/vote tiếp theo. |
| **T4** | Replay hoặc giao dịch trùng lặp | Một `tx_id` được áp dụng không quá một lần trong lịch sử đã finalize. |
| **T5** | Drop/delay trước synchrony | Bất biến safety duy trì suốt; không có hai hash finalize tại một height. |
| **T6** | Proposer im lặng / crash | Proposal timeout/round transition xảy ra và proposer đúng đắn sau đó finalize. |
| **T7** | Tối đa `f` validator equivocating | Equivocation được ghi log; các node đúng đắn không finalize block xung đột. |
| **T8** | Cùng seed, hai lần chạy | Log chuẩn thô và state hash cuối byte-identical. |

---

## Unit Test

### Mật mã (Cryptography)
- Chữ ký chỉ xác thực dưới đúng domain và public key tương ứng.
- Thay đổi bất kỳ trường ký nào quan trọng đều làm xác thực thất bại.

### Mã hóa và Hash (Encoding & Hashing)
- Canonical encoding cho byte giống nhau cho các giá trị ngữ nghĩa bằng nhau.
- Sorted-state hash ổn định.

### Giao dịch (Transaction)
- Namespace owner sai bị từ chối.
- Nonce sai bị từ chối.
- Giao dịch trùng lặp bị từ chối.
- Giao dịch không hợp lệ bên trong block bị từ chối.

### Xác thực Block Header
- Bắt được: parent sai, proposer sai, height sai, tx root sai, state hash sai, chữ ký sai.

### Tập Vote (Vote Set)
- Bỏ qua vote trùng.
- Từ chối non-member và trường không hợp lệ.
- Phát hiện equivocation.
- Chỉ đạt quorum khi có đủ validator riêng biệt.

### Locking
- Guard locking ngăn validator vote block khác trừ khi có bằng chứng quorum later-round.

### Timeout và Round
- Chuyển đổi trạng thái timeout/round là xác định.

---

## Schema Log (Định dạng log)

**Format:** Canonical JSON Lines — thứ tự key cố định, không có whitespace không cần thiết, UTF-8, newline sau mỗi sự kiện.

**Các trường bắt buộc chung:**

| Trường | Mô tả |
|---|---|
| `event_no` | Số sự kiện tăng đơn điệu |
| `logical_time` | Logical timestamp trong simulator |
| `node_id` | Định danh node |
| `event_type` | Loại sự kiện |
| `height` | Chiều cao block |
| `round` | Round hiện tại |
| `details` | Thứ tự key cố định theo `event_type` |

**Các loại sự kiện tối thiểu:**

| Nhóm | Loại sự kiện |
|---|---|
| Mạng | `SEND`, `DELIVER`, `DROP`, `DELAY`, `DUPLICATE` |
| Peer | `PEER_BLOCK`, `PEER_UNBLOCK` |
| Giao thức | `REJECT`, `PROPOSE`, `PREVOTE`, `PRECOMMIT` |
| Đồng thuận | `LOCK`, `TIMEOUT`, `ROUND_CHANGE`, `FINALIZE`, `EQUIVOCATION` |
| Node | `CRASH`, `RESTART` (khi được mô phỏng) |

---

## Báo cáo tổng kết kiểm thử

Assertion cuối phải export một bản tóm tắt compact bao gồm:
- `(height, hash)` đã finalize theo từng node đúng đắn
- State hash cuối
- Số thông điệp bị từ chối theo lý do
- SHA-256 của log

> Log thô là **bằng chứng chính thức**. Bản tóm tắt chỉ để tiện tra cứu nhanh.
