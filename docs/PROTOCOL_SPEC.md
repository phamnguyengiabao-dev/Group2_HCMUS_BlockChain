# Đặc Tả Giao Thức v0.1

## 1. Hằng số và danh tính

- `chain_id`: định danh ASCII bất biến, duy nhất cho một mạng kiểm thử.
- `validator_set`: sắp xếp theo lexicographic public-key bytes; mỗi validator có trọng số 1.
- `n = 3f + 1`; `QUORUM = 2f + 1`.
- `height` bắt đầu từ 1. `round` bắt đầu từ 0 cho mỗi height.
- Sơ đồ chữ ký: Ed25519. Hash: SHA-256. Hash là 32 byte, serialize thành hex viết thường chỉ ở ranh giới UI/log.

Simulator cung cấp các khóa kiểm thử xác định từ fixture cố định. Các khóa đó chỉ dùng cho testing, không phải thiết kế quản lý khóa production.

## 2. Mã hóa chuẩn và ký số

Tất cả giá trị được hash hoặc ký đều dùng canonical bytes:

1. Record được mã hóa với các trường theo **đúng thứ tự** liệt kê dưới đây.
2. Số nguyên: unsigned 64-bit big-endian; boolean: 1 byte (`00`/`01`).
3. Byte string: `u32 length || bytes`; text: UTF-8 NFC bytes.
4. `block_hash` tùy chọn: 1 byte presence + 32 byte hash khi có.
5. List giữ nguyên thứ tự; map sắp xếp theo raw UTF-8 key bytes.

`sign(domain, payload)` ký `utf8(domain) || 00 || payload`. Domain bắt buộc: `TX:<chain_id>`, `HEADER:<chain_id>`, và `VOTE:<chain_id>`. Bộ xác thực phải dùng domain mong đợi theo loại thông điệp — **không dùng** domain do người gửi cung cấp.

## 3. Mô hình dữ liệu

| Đối tượng | Các trường chuẩn (theo thứ tự) |
|---|---|
| Transaction | `chain_id, nonce, sender_pubkey, key, value_bytes, signature` |
| Unsigned transaction | Transaction không có `signature` |
| Block header | `chain_id, height, round, parent_hash, tx_root, state_hash, proposer_pubkey, signature` |
| Block body | `transactions[]` đã sắp xếp |
| Vote | `chain_id, height, round, phase, block_hash_or_nil, validator_pubkey, signature` |

`tx_id = SHA256(canonical unsigned transaction || signature)`. `block_hash = SHA256(canonical signed header)`. `tx_root` là SHA-256 của concatenation có thứ tự các `tx_id`, có tiền tố là count; block rỗng có hash của count bằng 0. State commitment là `SHA256(encode(sorted(key, value_bytes) pairs))` có tiền tố là entry count.

## 4. Quy tắc giao dịch và thực thi

Giao dịch hợp lệ khi và chỉ khi:

- `chain_id` khớp, chữ ký xác thực trong `TX:<chain_id>`, và `nonce` đúng bằng nonce tiếp theo của người gửi.
- `key` bắt đầu bằng `hex(SHA256(sender_pubkey)) + "/"` — chỉ ảnh hưởng đến namespace của người gửi.
- Kích thước key/value và block-size trong giới hạn cấu hình.
- `tx_id` chưa xuất hiện trong lịch sử đã finalize. Trùng trong cùng một block là không hợp lệ.

Áp dụng giao dịch theo đúng thứ tự body. Với mỗi giao dịch hợp lệ: `state[key] = value_bytes` và tăng nonce người gửi. Bất kỳ giao dịch không hợp lệ nào sẽ **invalidate toàn bộ block đề xuất** — không được bỏ qua silently. Execution không được đọc wall-clock time, giá trị ngẫu nhiên, trạng thái filesystem cục bộ, hay thứ tự nhận.

## 5. Xác thực block

Tại `(height, round)`, proposer index là `(height + round) mod n` trong tập validator đã sắp xếp. Header/body chỉ được chấp nhận khi **tất cả** điều kiện sau đúng:

1. `chain_id`, height, round, parent hash, proposer mong đợi, và chữ ký `HEADER` hợp lệ.
2. Mở rộng từ head đã finalize cục bộ (hoặc lưu như candidate đang chờ có parent đã biết); lịch sử finalize không bao giờ bị thay thế.
3. `tx_root` tính toán khớp header; tất cả giao dịch hợp lệ và áp dụng theo thứ tự vào trạng thái parent.
4. Post-state hash tính toán khớp `state_hash`.
5. Body chỉ được xử lý **sau** khi header hợp lệ tương ứng đã được xử lý.

Node ghi log mã từ chối cụ thể cho guard đầu tiên thất bại và **không relay** object không hợp lệ.

## 6. State machine đồng thuận

Mỗi height, validator giữ: `round`, `locked_block_hash?`, `locked_round?`, `valid_block_hash?`, `prevotes`, `precommits`, và bản ghi vote đã ký theo validator. Gửi **tối đa một prevote và một precommit** cho mỗi `(height, round)`.

1. **Đề xuất.** Proposer mong đợi broadcast header hợp lệ rồi body. Các validator khác chờ đến proposal timeout.
2. **Prevote.** Validator prevote proposal hợp lệ nếu unlocked hoặc khớp lock. Validator locked có thể prevote proposal khác hợp lệ chỉ sau khi quan sát quorum prevote round sau cho proposal đó. Ngược lại, prevote `NIL`.
3. **Lock.** Khi quorum prevote cho block không-NIL ở round `r`: đặt `locked_block_hash`, `locked_round = r`; đặt `valid_block_hash`.
4. **Precommit.** Khi quorum prevote không-NIL: precommit block đó. Khi quorum prevote NIL hoặc timeout mà không có quorum không-NIL: precommit NIL.
5. **Finalize.** Khi quorum precommit hợp lệ cho cùng block không-NIL: xác thực lại, append ledger đã finalize, commit state, xóa consensus state cục bộ của height, bắt đầu `height + 1, round 0`.
6. **Đổi round.** Khi precommit timeout mà không finalize: tăng round, reset chỉ tập vote theo round. Locks vẫn giữ nguyên. Broadcast/ghi round transition theo cách xác định.

Kiểm tra chấp nhận vote: `chain_id`, tư cách validator, chữ ký/domain, height, round, phase, và hash candidate đã biết. Vote hợp lệ đầu tiên từ một validator cho một tuple được giữ lại; vote trùng chính xác bị bỏ qua; vote thứ hai xung đột ghi log equivocation nhưng không thay thế vote đầu.

## 7. Bất biến an toàn

- Validator đúng đắn không bao giờ ký hai vote cùng phase cho một `(height, round)`.
- Validator đúng đắn chỉ prevote block đã được xác thực đầy đủ và tuân theo lock của mình.
- Finalization yêu cầu `QUORUM` precommit riêng biệt cho đúng một block hash.
- Block và state đã finalize là append-only; node không bao giờ rollback height đã finalize.
- Tất cả node đúng đắn thực thi một block có thứ tự trên cùng parent đều có `state_hash` giống nhau.

## 8. Khôi phục và quan sát

Tại mỗi finalization, persist nguyên tử `finalized_height`, `finalized_hash`, canonical state, sender nonces, và block. Khi restart, load snapshot và bỏ proposals/votes chưa finalize; chúng có thể học lại từ peers. Mỗi sự kiện send/receive/drop/delay/duplicate/reject/vote/lock/timeout/finalize có một `event_no` tăng đơn điệu và logical timestamp.
