# Đặc Tả Kiểm Thử và Bằng Chứng

## Hợp đồng thực thi kiểm thử

Cung cấp **một lệnh duy nhất**, ghi trong README root, chạy toàn bộ unit test và end-to-end test. Lệnh phải trả về non-zero khi có bất kỳ thất bại nào và ghi log từng kịch bản vào `logs/<scenario>/<run-id>.jsonl`. Lệnh thứ hai (hoặc `--verify-determinism`) chạy một kịch bản **hai lần** với cùng cấu hình và so sánh byte log thô cùng state hash cuối.

Mỗi cấu hình kịch bản khai báo: `chain_id`, seed, validator keys/order, hành vi Byzantine, fixture giao dịch, topology, phân phối delay, giới hạn băng thông/tốc độ, kế hoạch drop/duplicate/reordering, logical time ổn định, và lịch timeout.

## Ma trận end-to-end bắt buộc

| ID | Kịch bản | Kiểm tra |
|---|---|---|
| T1 | Chạy bình thường, không có lỗi | Mọi node đúng đắn finalize height, hash và state hash cuối giống nhau. |
| T2 | Thông điệp trùng lặp và sắp xếp lại | Mỗi tuple vote đếm tối đa một validator; không có finalization xung đột. |
| T3 | Chữ ký không hợp lệ và domain sai | Router từ chối thông điệp, ghi lý do, không có chuyển đổi state/vote tiếp theo. |
| T4 | Replay hoặc giao dịch trùng lặp | Một `tx_id` được áp dụng không quá một lần trong lịch sử đã finalize. |
| T5 | Drop/delay trước synchrony | Bất biến safety duy trì suốt; không có hai hash finalize tại một height. |
| T6 | Proposer im lặng / crash | Proposal timeout/round transition xảy ra và proposer đúng đắn sau đó finalize. |
| T7 | Tối đa `f` validator equivocating | Equivocation được ghi log; các node đúng đắn không finalize block xung đột. |
| T8 | Cùng seed, hai lần chạy | Log chuẩn thô và state hash cuối byte-identical. |

## Unit test

- Chữ ký chỉ xác thực dưới đúng domain và public key tương ứng; thay đổi bất kỳ trường ký nào quan trọng đều làm xác thực thất bại.
- Canonical encoding cho byte giống nhau cho các giá trị ngữ nghĩa bằng nhau và sorted-state hash ổn định.
- Namespace owner sai, nonce sai, giao dịch trùng, và giao dịch không hợp lệ bên trong block đều bị từ chối.
- Xác thực header bắt được: parent sai, proposer sai, height sai, tx root sai, state hash sai, và signature sai.
- Vote set bỏ qua duplicate, từ chối non-member/trường không hợp lệ, phát hiện equivocation, và chỉ đạt quorum khi có đủ validator riêng biệt.
- Locking guard ngăn validator vote block khác trừ khi có bằng chứng quorum later-round.
- Chuyển đổi trạng thái timeout/round là xác định.

## Schema log

Ghi canonical JSON Lines: thứ tự key cố định, không có whitespace không cần thiết, UTF-8, newline sau mỗi sự kiện. Các trường chung bắt buộc: `event_no`, `logical_time`, `node_id`, `event_type`, `height`, `round`, và `details`. `details` có thứ tự key cố định theo `event_type`.

Các loại sự kiện tối thiểu: `SEND`, `DELIVER`, `DROP`, `DELAY`, `DUPLICATE`, `PEER_BLOCK`, `PEER_UNBLOCK`, `REJECT`, `PROPOSE`, `PREVOTE`, `PRECOMMIT`, `LOCK`, `TIMEOUT`, `ROUND_CHANGE`, `FINALIZE`, `EQUIVOCATION`, và `CRASH`/`RESTART` khi được mô phỏng.

Assertion cuối phải export bản tóm tắt compact: `(height, hash)` đã finalize theo từng node đúng đắn, state hash cuối, số thông điệp bị từ chối theo lý do, và SHA-256 của log. Log thô là **bằng chứng chính thức**.
