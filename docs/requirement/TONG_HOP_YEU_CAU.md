# Tổng Hợp Đầy Đủ Yêu Cầu Dự Án — Lab 01 Blockchain Simulator

> Tài liệu này tổng hợp toàn bộ yêu cầu từ `Lab01.pdf`, `Lab01-presentation.pdf` và các tài liệu kỹ thuật thành một nguồn tham chiếu duy nhất.

---

## 1. Mục Tiêu Tổng Quan

Xây dựng một **blockchain Layer-1 tối giản dạng mô phỏng (simulator)** thỏa mãn:

- Các validator đúng đắn hội tụ về một chuỗi block đã finalize dù mạng bị lỗi (trễ, trùng, sắp xếp lại, rớt thông điệp).
- Một node đúng đắn **không bao giờ** finalize hai block khác nhau tại cùng một chiều cao.
- Sau khi mạng ổn định, chuỗi phải tiến triển khi proposer đúng đắn được chọn.

---

## 2. Yêu Cầu Chức Năng

### 2.1 Tập Validator và Danh Tính

| # | Yêu cầu |
|---|---|
| F-01 | Tập validator cố định mỗi lần chạy, thỏa `n = 3f + 1`, hỗ trợ ít nhất 8 node (f=2). |
| F-02 | Mỗi validator có một cặp khóa Ed25519 cố định cho mỗi lần chạy. |
| F-03 | `chain_id` là ASCII bất biến, duy nhất cho một mạng kiểm thử. |
| F-04 | Tập validator được sắp xếp theo lexicographic public key bytes; mỗi validator có trọng số 1. |

### 2.2 Mật Mã và Mã Hóa

| # | Yêu cầu |
|---|---|
| F-05 | Sử dụng chữ ký Ed25519 cho giao dịch, header và vote. |
| F-06 | Sử dụng SHA-256 (32 byte) cho tất cả hash; serialize thành hex viết thường chỉ ở UI/log. |
| F-07 | Mã hóa chuẩn (canonical encoding): trường theo đúng thứ tự, số nguyên unsigned 64-bit big-endian, boolean 1 byte, byte string có `u32 length` prefix. |
| F-08 | Domain separation bắt buộc: `TX:<chain_id>`, `HEADER:<chain_id>`, `VOTE:<chain_id>`. |
| F-09 | Bộ xác thực phải dùng domain mong đợi theo loại thông điệp, không tin domain từ người gửi. |

### 2.3 Mô Hình Dữ Liệu

| # | Yêu cầu |
|---|---|
| F-10 | **Transaction:** `chain_id, nonce, sender_pubkey, key, value_bytes, signature` (theo đúng thứ tự). |
| F-11 | **Block header:** `chain_id, height, round, parent_hash, tx_root, state_hash, proposer_pubkey, signature`. |
| F-12 | **Block body:** danh sách `transactions[]` đã sắp xếp. |
| F-13 | **Vote:** `chain_id, height, round, phase, block_hash_or_nil, validator_pubkey, signature`. |
| F-14 | `tx_id = SHA256(canonical unsigned tx \|\| signature)`. |
| F-15 | `block_hash = SHA256(canonical signed header)`. |
| F-16 | `tx_root = SHA256(count \|\| tx_id[0] \|\| tx_id[1] \|\| ...)`. Block rỗng là hash của count=0. |
| F-17 | State commitment = `SHA256(entry_count \|\| sorted(key, value_bytes) pairs)`. |

### 2.4 Giao Dịch và Thực Thi

| # | Yêu cầu |
|---|---|
| F-18 | Giao dịch hợp lệ: `chain_id` khớp, chữ ký đúng, nonce chính xác bằng nonce tiếp theo. |
| F-19 | `key` phải bắt đầu bằng `hex(SHA256(sender_pubkey)) + "/"` (namespace người gửi). |
| F-20 | Key/value size và block-size phải trong giới hạn cấu hình. |
| F-21 | `tx_id` không được tồn tại trong lịch sử đã finalize; trùng trong cùng block là không hợp lệ. |
| F-22 | Áp dụng giao dịch theo đúng thứ tự body. |
| F-23 | Giao dịch không hợp lệ **invalidate toàn bộ block** — không được bỏ qua silently. |
| F-24 | Execution không được đọc wall-clock time, random, filesystem cục bộ, hay thứ tự nhận. |

### 2.5 Xác Thực Block

| # | Yêu cầu |
|---|---|
| F-25 | Proposer tại `(height, round)` = index `(height + round) mod n` trong validator set đã sắp xếp. |
| F-26 | Header hợp lệ: `chain_id`, height, round, parent hash, proposer mong đợi và chữ ký HEADER đúng. |
| F-27 | Block chỉ mở rộng từ head đã finalize cục bộ hoặc là candidate có parent đã biết. |
| F-28 | `tx_root` tính toán phải khớp header; tất cả giao dịch hợp lệ và áp dụng đúng thứ tự. |
| F-29 | Post-state hash tính toán phải khớp `state_hash`. |
| F-30 | **Header-first rule:** Body chỉ được xử lý SAU khi header hợp lệ tương ứng đã được xử lý. |
| F-31 | Node ghi log mã từ chối cụ thể cho guard đầu tiên thất bại; không relay object không hợp lệ. |

### 2.6 Đồng Thuận (Consensus)

| # | Yêu cầu |
|---|---|
| F-32 | Mỗi height: validator giữ `round`, `locked_block_hash`, `locked_round`, `valid_block_hash`, tập vote. |
| F-33 | Tối đa một prevote và một precommit cho mỗi `(height, round)`. |
| F-34 | **Proposal:** Proposer broadcast header trước rồi body. Validators khác chờ đến proposal timeout. |
| F-35 | **Prevote:** Vote proposal hợp lệ nếu unlocked hoặc khớp lock; nếu locked thì chỉ vote khác khi có quorum prevote later-round. Ngược lại vote NIL. |
| F-36 | **Lock:** Khi quorum prevote cho block không-NIL ở round r → set `locked_block_hash`, `locked_round = r`, `valid_block_hash`. |
| F-37 | **Precommit:** Quorum prevote không-NIL → precommit block đó. Quorum NIL hoặc timeout → precommit NIL. |
| F-38 | **Finalize:** Quorum precommit không-NIL → xác thực lại, append ledger, commit state, start `height+1, round 0`. |
| F-39 | **Round change:** Precommit timeout → tăng round, reset tập vote theo round, giữ nguyên locks. |
| F-40 | Vote chỉ chấp nhận khi: `chain_id` khớp, là member hợp lệ, chữ ký/domain đúng, height/round/phase khớp, hash candidate đã biết. |
| F-41 | Vote trùng chính xác bị bỏ qua; vote thứ hai xung đột ghi log equivocation, không thay thế vote đầu. |

### 2.7 Mạng Mô Phỏng

| # | Yêu cầu |
|---|---|
| F-42 | Mạng P2P mô phỏng với delay, drop, duplicate, reorder có thể cấu hình. |
| F-43 | Giới hạn băng thông và rate limit. |
| F-44 | Chặn peer tạm thời (peer blocking/unblocking). |
| F-45 | Mọi quyết định ngẫu nhiên lấy từ PRNG có seed do scenario runner sở hữu. |
| F-46 | Scheduler: priority queue `(logical_time, insertion_sequence)`; logical time — không phải wall-clock. |
| F-47 | Lặp validators, peers, messages theo thứ tự bytes chuẩn — không bao giờ theo map iteration order. |
| F-48 | Replay với cùng seed cho kết quả byte-identical. |

### 2.8 Log Sự Kiện

| # | Yêu cầu |
|---|---|
| F-49 | Canonical JSON Lines: thứ tự key cố định, không whitespace thừa, UTF-8, newline sau mỗi sự kiện. |
| F-50 | Trường bắt buộc: `event_no`, `logical_time`, `node_id`, `event_type`, `height`, `round`, `details`. |
| F-51 | Hỗ trợ tối thiểu các loại: `SEND`, `DELIVER`, `DROP`, `DELAY`, `DUPLICATE`, `PEER_BLOCK`, `PEER_UNBLOCK`, `REJECT`, `PROPOSE`, `PREVOTE`, `PRECOMMIT`, `LOCK`, `TIMEOUT`, `ROUND_CHANGE`, `FINALIZE`, `EQUIVOCATION`, `CRASH`, `RESTART`. |

### 2.9 Khôi Phục (Recovery)

| # | Yêu cầu |
|---|---|
| F-52 | Tại mỗi finalize: persist nguyên tử `finalized_height`, `finalized_hash`, state, nonces và block. |
| F-53 | Khi restart: load snapshot, bỏ proposals/votes chưa finalize (học lại từ peers). |

---

## 3. Yêu Cầu Phi Chức Năng

| # | Yêu cầu |
|---|---|
| NF-01 | **Tất định (Determinism):** Cùng seed tạo log byte-identical và state hash giống nhau trên 2 lần chạy. |
| NF-02 | **An toàn (Safety):** Không có hai block finalize khác nhau tại cùng chiều cao. |
| NF-03 | **Hoạt động (Liveness):** Sau stabilization + proposer đúng, chiều cao sau đó được finalize. |
| NF-04 | **Hợp lệ (Validity):** Mọi vi phạm giao thức đều bị từ chối và ghi log. |
| NF-05 | **Single-threaded consensus:** Không dùng parallelism; mọi mutation đồng thuận dưới scheduler. |
| NF-06 | **Không trạng thái ngoài:** Execution không phụ thuộc clock, filesystem, hay random ngoài seed. |

---

## 4. Yêu Cầu Nộp Bài

| # | Yêu cầu |
|---|---|
| S-01 | Cấu trúc thư mục: `src/`, `tests/`, `logs/`, `config/`, `README.md`. |
| S-02 | `REPORT.pdf` tối đa 10 trang. |
| S-03 | Đặt trong folder và ZIP theo tên nhóm đúng quy định. |
| S-04 | Một lệnh duy nhất chạy toàn bộ T1–T8. |
| S-05 | Script hoặc flag `--verify-determinism` kiểm tra reproducibility. |

---

## 5. Ma Trận Test Bắt Buộc (T1–T8)

| ID | Kịch bản | Tiêu chí pass |
|---|---|---|
| T1 | Chạy bình thường, không lỗi | Mọi node finalize height/hash/state hash giống nhau |
| T2 | Thông điệp trùng + sắp xếp lại | Vote count đúng; không finalization xung đột |
| T3 | Chữ ký sai / domain sai | Router từ chối + ghi log; không có state transition |
| T4 | Replay / giao dịch trùng | `tx_id` dùng tối đa một lần trong lịch sử |
| T5 | Drop/delay trước synchrony | Safety bất biến; không 2 hash tại một height |
| T6 | Proposer crash / im lặng | Timeout + round change; proposer sau finalize được |
| T7 | f validator equivocating | Equivocation log; node đúng không finalize xung đột |
| T8 | Cùng seed × 2 lần | Log byte-identical; state hash giống nhau |

---

## 6. Ngoài Phạm Vi (Không Làm)

- Dynamic validator sets, staking, gas/fees, smart contract, parallel execution.
- Real socket networking (production network).
- Production-grade key management.
- Merkle Patricia Trie đầy đủ.
- Bất kỳ tính năng nào không có trong Lab01.pdf.
