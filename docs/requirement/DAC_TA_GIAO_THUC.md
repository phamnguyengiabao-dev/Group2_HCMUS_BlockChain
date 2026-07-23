# Đặc Tả Giao Thức v0.1

## 1. Hằng số và danh tính

| Tham số | Mô tả |
|---|---|
| `chain_id` | Định danh ASCII bất biến, duy nhất cho một mạng kiểm thử |
| `validator_set` | Sắp xếp theo byte public key lexicographic; mỗi validator có trọng số 1 |
| `n = 3f + 1` | Tổng số validator; `QUORUM = 2f + 1` |
| `height` | Bắt đầu từ 1; `round` bắt đầu từ 0 cho mỗi height |
| Chữ ký | Ed25519; Hash: SHA-256 (32 byte, serialize thành hex viết thường chỉ ở UI/log) |

> Simulator cung cấp các khóa kiểm thử xác định từ fixture cố định — chỉ dùng cho test, không phải thiết kế quản lý khóa production.

---

## 2. Mã hóa chuẩn và ký số

Tất cả giá trị được hash hoặc ký đều dùng **canonical bytes**:

1. Record được mã hóa với các trường theo **đúng thứ tự** liệt kê dưới đây.
2. Số nguyên: unsigned 64-bit big-endian; boolean: 1 byte (`00`/`01`).
3. Byte string: `u32 length || bytes`; text: UTF-8 NFC bytes.
4. `block_hash` tùy chọn: 1 byte presence + 32 byte hash (khi có).
5. List giữ nguyên thứ tự; map sắp xếp theo UTF-8 key bytes.

**Hàm ký:** `sign(domain, payload)` ký `utf8(domain) || 00 || payload`

**Các domain bắt buộc:**
- `TX:<chain_id>` — cho giao dịch
- `HEADER:<chain_id>` — cho block header
- `VOTE:<chain_id>` — cho vote

> Bộ xác thực phải dùng domain mong đợi theo loại thông điệp, **không dùng** domain do người gửi cung cấp.

---

## 3. Mô hình dữ liệu

| Đối tượng | Các trường chuẩn (theo thứ tự) |
|---|---|
| Transaction | `chain_id, nonce, sender_pubkey, key, value_bytes, signature` |
| Unsigned transaction | Transaction không có `signature` |
| Block header | `chain_id, height, round, parent_hash, tx_root, state_hash, proposer_pubkey, signature` |
| Block body | `transactions[]` đã sắp xếp |
| Vote | `chain_id, height, round, phase, block_hash_or_nil, validator_pubkey, signature` |

**Công thức tính:**
- `tx_id = SHA256(canonical unsigned transaction || signature)`
- `block_hash = SHA256(canonical signed header)`
- `tx_root` = SHA-256 của concatenation các `tx_id` theo thứ tự, có tiền tố là count; block rỗng có hash của count bằng 0
- **State commitment** = `SHA256(encode(sorted(key, value_bytes) pairs))` có tiền tố là entry count

---

## 4. Quy tắc giao dịch và thực thi

Giao dịch hợp lệ khi và chỉ khi:

- `chain_id` khớp, chữ ký hợp lệ trong `TX:<chain_id>`, và `nonce` đúng bằng nonce tiếp theo của người gửi.
- `key` bắt đầu bằng `hex(SHA256(sender_pubkey)) + "/"` — chỉ ảnh hưởng đến namespace của người gửi.
- Kích thước key/value và block-size trong giới hạn cấu hình.
- `tx_id` chưa xuất hiện trong lịch sử đã finalize. Trùng lặp trong cùng một block là không hợp lệ.

**Quy trình thực thi:**
1. Áp dụng giao dịch đúng theo thứ tự trong body.
2. Với mỗi giao dịch hợp lệ: `state[key] = value_bytes` và tăng nonce người gửi.
3. Bất kỳ giao dịch không hợp lệ nào sẽ **invalidate toàn bộ block đề xuất** — không bỏ qua silently.
4. Execution không được đọc wall-clock time, giá trị ngẫu nhiên, trạng thái filesystem cục bộ, hay thứ tự nhận.

---

## 5. Xác thực block

Proposer tại `(height, round)` = `(height + round) mod n` trong tập validator đã sắp xếp.

Một header/body chỉ được chấp nhận khi **tất cả** điều kiện sau đúng:

1. `chain_id`, height, round, parent hash, proposer mong đợi và chữ ký `HEADER` hợp lệ.
2. Mở rộng từ head đã finalize cục bộ (hoặc lưu như candidate đang chờ có parent đã biết); lịch sử finalize không bao giờ bị thay thế.
3. `tx_root` tính toán khớp với header; tất cả giao dịch hợp lệ và được áp dụng theo thứ tự vào trạng thái parent.
4. Post-state hash tính toán khớp với `state_hash`.
5. Body chỉ được xử lý **sau** khi header hợp lệ tương ứng đã được xử lý.

> Node ghi log một mã từ chối cụ thể cho guard đầu tiên thất bại và **không relay** object không hợp lệ.

---

## 6. State machine đồng thuận

Mỗi validator giữ cho mỗi height: `round`, `locked_block_hash?`, `locked_round?`, `valid_block_hash?`, `prevotes`, `precommits`, và bản ghi vote đã ký theo validator. Gửi **tối đa một prevote và một precommit** cho mỗi `(height, round)`.

### Các bước đồng thuận

**1. Đề xuất (Proposal)**
- Proposer mong đợi broadcast header hợp lệ rồi body.
- Các validator khác chờ đến khi proposal timeout.

**2. Prevote**
- Validator prevote cho proposal hợp lệ nếu không locked hoặc proposal khớp với lock của mình.
- Validator đang locked có thể prevote proposal khác hợp lệ chỉ sau khi quan sát được quorum prevote round sau cho proposal đó.
- Ngược lại, prevote `NIL`.

**3. Lock**
- Khi quorum prevote cho block không-NIL ở round `r`: đặt `locked_block_hash`, `locked_round = r`; đặt `valid_block_hash`.

**4. Precommit**
- Khi quorum prevote cho block không-NIL: precommit block đó.
- Khi quorum prevote NIL, hoặc prevote timeout mà không có quorum không-NIL: precommit NIL.

**5. Finalize**
- Khi quorum precommit hợp lệ cho cùng một block không-NIL:
  - Xác thực block một lần nữa.
  - Append vào ledger đã finalize, commit state.
  - Xóa consensus state cục bộ của height.
  - Bắt đầu `height + 1, round 0`.

**6. Đổi round (Round change)**
- Khi precommit timeout mà không finalize: tăng round, reset chỉ tập vote theo round.
- Locks vẫn giữ nguyên.
- Broadcast/ghi chú round transition theo cách xác định.

---

## 7. Kiểm tra chấp nhận vote

Kiểm tra: `chain_id`, tư cách validator, chữ ký/domain, height, round, phase, và hash candidate đã biết.
- Vote hợp lệ đầu tiên từ một validator cho một tuple được giữ lại.
- Vote trùng chính xác (exact duplicate) bị bỏ qua.
- Vote thứ hai xung đột: ghi log là **equivocation** nhưng không thay thế vote đầu tiên.

---

## 8. Bất biến an toàn

| Bất biến | Mô tả |
|---|---|
| Không vote hai lần | Validator đúng đắn không bao giờ ký hai vote cùng phase cho một `(height, round)` |
| Tuân thủ lock | Validator đúng đắn chỉ prevote block đã được xác thực đầy đủ và tuân theo lock của mình |
| Quorum finalize | Finalization yêu cầu `QUORUM` precommit riêng biệt cho đúng một block hash |
| Append-only | Block và state đã finalize là append-only; node không bao giờ rollback height đã finalize |
| Đồng nhất state | Tất cả node đúng đắn thực thi một block có thứ tự trên cùng parent đều có được `state_hash` giống nhau |

---

## 9. Khôi phục và quan sát

- Tại mỗi lần finalize: persist nguyên tử `finalized_height`, `finalized_hash`, canonical state, sender nonces và block.
- Khi restart: load snapshot và bỏ proposals/votes chưa finalize; chúng có thể học lại từ peers.
- Mỗi sự kiện send/receive/drop/delay/duplicate/reject/vote/lock/timeout/finalize có một `event_no` tăng đơn điệu và logical timestamp.
