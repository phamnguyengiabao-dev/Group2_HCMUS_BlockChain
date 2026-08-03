# Phân Công Công Việc — Blockchain Lab01 (5 Thành Viên)

> Nguồn tham chiếu: `TONG_HOP_YEU_CAU.md`, `PHAN_CONG_VIEC.md`, `DAC_TA_GIAO_THUC.md`, `KIEN_TRUC.md`, `DAC_TA_KIEM_THU.md`

---

## Thông Tin Nhóm

| STT | Thành viên | Vai trò | Viết tắt |
|-----|------------|---------|----------|
| 1 | **Phạm Nguyễn Gia Bảo** | Team Leader, Project Manager | **Bảo** |
| 2 | **Nguyễn Minh Hiếu** | Software Engineer | **Hiếu** |
| 3 | **Võ Kim Khôi** | Software Engineer | **Khôi** |
| 4 | **Lê Quốc Khánh** | Software Engineer | **Khánh** |
| 5 | **Trương Nhật Huy** | Software Engineer | **Huy** |

---

## Quy Tắc Phân Công

- **Giai đoạn 0:** Leader làm toàn bộ — **đã hoàn thành** ✅
- **Giai đoạn 1–5:** Mỗi giai đoạn **chia đều cho cả 5 người**
- **Bảo (TeamLeader):** Mỗi giai đoạn chỉ nhận **1-2 task coding** để dành thời gian review PR, tích hợp milestone và resolve blockers. Ngoài task coding, Bảo còn chịu trách nhiệm **2 task management** được tính điểm mỗi giai đoạn (xem bên dưới).
- Các thành viên còn lại (Hiếu, Khôi, Khánh, Huy): nhận số task tương đương nhau mỗi giai đoạn

### Định Nghĩa Task Management Của Leader (Tính Điểm)

| Task ID | Công việc | Ưu tiên | Độ khó | Ngày | Trọng số/giai đoạn | Ghi chú |
|---------|-----------|---------|--------|------|---------------------|---------|
| MG-PR | Review & approve toàn bộ PR của giai đoạn — đọc diff, kiểm tra correctness, canonical sort, test coverage | 8 | 5 | 2 | 80 | Áp dụng cho G1→G5 (5 giai đoạn × 80 = **400**) |
| MG-INT | Tích hợp milestone: merge branches, resolve conflicts, chạy full test suite, update trạng thái tài liệu | 7 | 4 | 1 | 28 | Áp dụng cho G1→G5 (5 giai đoạn × 28 = **140**) |

---

## Cách Tính Điểm Đóng Góp

```
Trọng số nhiệm vụ  = Độ ưu tiên × Độ khó × Số ngày thực hiện
Điểm đóng góp      = Trọng số × Mức độ hoàn thành checklist (0.0–1.0)
Mức độ năng suất   = Tổng điểm / Tổng trọng số
```

**Thang Độ ưu tiên & Độ khó:** 1–10

---

## GIAI ĐOẠN 0 — Repository Scaffold ✅ HOÀN THÀNH

> **Thời gian:** 2026-07-21 (1 ngày) | **Người thực hiện: Phạm Nguyễn Gia Bảo**

| Task ID | Công việc | Đầu ra | Ưu tiên | Độ khó | Ngày | Trọng số | Trạng thái |
|---------|-----------|--------|---------|--------|------|----------|------------|
| T0-01 | Tạo thư mục `src/`, `tests/`, `logs/`, `config/` + `__init__.py` đúng vị trí; Python package structure hợp lệ | Cấu trúc thư mục | 8 | 2 | 1 | 16 | ✅ Done |
| T0-02 | Viết `README.md` root: hướng dẫn cài đặt, lệnh test, mô tả dự án + cấu trúc thư mục | `README.md` | 6 | 2 | 1 | 12 | ✅ Done |
| T0-03 | Tạo `config/default.json`: block_capacity, timeout_schedule (3 loại), retention_policy, network limits — căn cứ PROTOCOL_SPEC.md | `config/default.json` | 7 | 4 | 1 | 28 | ✅ Done |
| T0-04 | Tạo 8 cặp khóa Ed25519 deterministic (seed-based HKDF); format `{pubkey_hex: privkey_hex}`; thứ tự lexicographic | `config/validator_keys.json` | 9 | 6 | 1 | 54 | ✅ Done |
| T0-05 | Tạo 3 scenario config files: `scenario_noop.json`, `scenario_t1.json`, `scenario_t8.json`; mỗi file có fault_config, network_params, max_height, seed | `config/scenario_*.json` | 8 | 4 | 1 | 32 | ✅ Done |
| T0-06 | Implement `src/event_log.py` (canonical JSONL writer, fixed key order, event_no monotonic) + `src/scenario_runner.py` (load config, init nodes, simulation loop) + `tests/test_noop.py` (3 tests pass) + `tests/verify_determinism.py` | 4 files | 9 | 8 | 3 | 216 | ✅ Done |

> **G0 tổng trọng số: 358** | Ghi chú: T0-06 nặng nhất (4 files, 2 module nguồn đầy đủ, test suite pass)

> **Ghi chú trạng thái (cập nhật 2026-07-29):**
> - `src/event_log.py` và `src/scenario_runner.py` đã được implement đầy đủ trong giai đoạn scaffold (thuộc T0-06 mở rộng).
> - `tests/test_noop.py` và `tests/verify_determinism.py` đã pass (log JSONL đúng format, event_no monotonic, determinism xác nhận cho noop scenario).

---

## GIAI ĐOẠN 1 — Primitive Xác Định

> **Tổng: 15 task** — Bảo: 2 task | Hiếu: 3 task | Khôi: 3 task | Khánh: 3 task | Huy: 4 task

**Dependency:** Giai đoạn 0 ✅

### 1A — Canonical Encoding (`src/encoding.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số | Trạng thái |
|---------|-----------|------|-------|---------|--------|------|----------|------------|
| T1-01 | `encode_uint64`, `encode_bool`, `encode_bytes`, `encode_str` — unsigned 64-bit big-endian, boolean 1 byte, byte string với u32 length prefix | `src/encoding.py` | **Bảo** | 9 | 5 | 1 | 45 | ✅ Done (commit `8d5f3e3`) |
| T1-02 | `encode_optional_hash` — presence byte + 32 byte hash; raise ValueError nếu sai size | `src/encoding.py` | **Khánh** | 8 | 4 | 1 | 32 | ✅ Done (commit `8d5f3e3`) |
| T1-03 | Sorted map encoder — sắp xếp theo UTF-8 key bytes trước khi concatenate | `src/encoding.py` | ~~Huy~~ → **Khánh** | 8 | 5 | 1 | 40 | ✅ Done (commit `8d5f3e3`, Khánh thực hiện) |
| T1-04 | Unit test encoding: byte-identical cho giá trị ngữ nghĩa bằng nhau; test tất cả 5 hàm (`encode_uint64`, `encode_bool`, `encode_bytes`, `encode_str`, `encode_optional_hash`) | `tests/test_encoding.py` | **Huy** | 9 | 4 | 1 | 36 | ✅ Done — tất cả 5 hàm đều có test, 47 tests pass |

> **Ghi chú phân bổ lại T1-03 & T1-04:**
> - Khánh đã implement T1-02, **và T1-03** trong cùng một commit → ghi nhận Khánh cho cả 3 task.
> - T1-04: `tests/test_encoding.py` hiện có đầy đủ test cho tất cả 5 hàm (`encode_uint64`, `encode_bool`, `encode_bytes`, `encode_str`, `encode_optional_hash`) + `encode_sorted_map` — **hoàn thành**.

### 1B — Cryptography (`src/crypto.py`, `src/identity.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số | Trạng thái |
|---------|-----------|------|-------|---------|--------|------|----------|------------|
| T1-05 | Tích hợp SHA-256; viết `hash_bytes(data) -> bytes` trả 32 bytes | `src/crypto.py` | **Khánh** | 9 | 3 | 1 | 27 | ✅ Done — 8 tests pass |
| T1-06 | Ed25519 `sign(domain, payload)`: ký `utf8(domain) \|\| 0x00 \|\| payload` với domain separation | `src/crypto.py` | **Khôi** | 9 | 6 | 1 | 54 | ✅ Done — tests pass |
| T1-07 | `verify(domain, pubkey, payload, signature)` — kiểm tra chữ ký với domain mong đợi | `src/crypto.py` | **Khôi** | 9 | 6 | 1 | 54 | ✅ Done — tests pass |
| T1-08 | Unit test crypto: sai domain → fail, sai key → fail, sai payload → fail, đúng → pass | `tests/test_crypto.py` | **Hiếu** | 9 | 5 | 1 | 45 | ✅ Done — 14 tests pass |
| T1-09 | Load và validate identity fixtures từ `validator_keys.json`; trả về sorted validator list | `src/identity.py` | **Bảo** | 7 | 3 | 1 | 21 | ✅ Done — 10 tests pass |

### 1C — State & Executor (`src/state.py`, `src/transaction.py`, `src/executor.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số | Trạng thái |
|---------|-----------|------|-------|---------|--------|------|----------|------------|
| T1-10 | Sorted key-value state map: insert/get/delete; dùng sorted dict để đảm bảo thứ tự | `src/state.py` | **Huy** | 8 | 5 | 2 | 80 | ✅ Done — `src/state.py` đầy đủ |
| T1-11 | State commitment: `SHA256(encode(entry_count) \|\| sorted(key, value_bytes) pairs)` | `src/state.py` | **Huy** | 8 | 6 | 1 | 48 | ✅ Done — `state_hash()` implement |
| T1-12 | Transaction object + validation: chain_id, nonce, namespace prefix, size limits, signature | `src/transaction.py` | **Khánh** | 9 | 7 | 2 | 126 | ✅ Done — 8 tests pass |
| T1-13 | Deterministic executor: apply tx list theo thứ tự → post-state + updated nonces; tx không hợp lệ → invalidate toàn block | `src/executor.py` | **Khôi** | 9 | 8 | 2 | 144 | ✅ Done — 22 tests pass (P1 atomicity, P2 determinism, P3 no-double-apply, P4 order) |
| T1-14 | Unit test determinism: cùng block thực thi 2 lần → byte/hash giống nhau | `tests/test_executor.py` | **Hiếu** | 9 | 5 | 1 | 45 | ✅ Done — 22 tests pass |
| T1-15 | Unit test transaction: namespace sai, nonce sai, tx trùng, kích thước vượt giới hạn → reject | `tests/test_transaction.py` | ~~Hiếu~~ → **Bảo** | 9 | 5 | 1 | 45 | ✅ Done — 8 tests pass |

**✅ Milestone 1 HOÀN THÀNH:** 15/15 task pass (110 tests xanh). T1-13 (`src/executor.py`) và T1-14 (`tests/test_executor.py`) hoàn thành ngày 2026-08-02.

---

## GIAI ĐOẠN 2 — Data Model và Xác Thực

> **Tổng: 14 task** — Bảo: 1 task | Hiếu: 3 task | Khôi: 4 task | Khánh: 3 task | Huy: 3 task

**Dependency:** Giai đoạn 1 (T1-01 → T1-15)

### 2A — Block Header & Body (`src/block.py`, `src/block_validator.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số | Trạng thái |
|---------|-----------|------|-------|---------|--------|------|----------|------------|
| T2-01 | Block Header object với đúng thứ tự fields theo spec; `block_hash = SHA256(canonical signed header)` | `src/block.py` | **Khánh** | 9 | 7 | 2 | 126 | ✅ Done (PR #8) |
| T2-02 | `tx_root = SHA256(encode(count) \|\| tx_id[0] \|\| tx_id[1] \|\| ...)`; block rỗng = hash(count=0) | `src/block.py` | **Huy** | 8 | 5 | 1 | 40 | ✅ Done (PR #10) |
| T2-03 | Header validation guards (F-26): chain_id, height, round, parent_hash, expected proposer, HEADER domain signature | `src/block_validator.py` | **Khôi** | 9 | 7 | 2 | 126 | ✅ Done (PR #10) |
| T2-04 | Block Body object + full candidate validation (F-27–F-29): tx_root khớp, all txs valid, post-state hash khớp | `src/block.py` | **Khôi** | 9 | 7 | 2 | 126 | ✅ Done (PR #10) |
| T2-05 | Unit test block: parent sai / proposer sai / height sai / tx_root sai / state_hash sai / signature sai → tất cả đều bị bắt | `tests/test_block.py` | ~~Hiếu~~ → **Bảo** | 9 | 6 | 1 | 54 | ✅ Done — 35 tests pass |

### 2B — Vote & VoteSet (`src/vote.py`, `src/vote_set.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T2-06 | Vote object với tất cả validation guards (F-40): chain_id, member check, VOTE domain signature, height/round/phase khớp | `src/vote.py` | **Huy** | 8 | 6 | 1 | 48 |
| T2-07 | VoteSet: lưu votes theo key `(height, round, phase, validator_pubkey)` | `src/vote_set.py` | **Khánh** | 8 | 6 | 1 | 48 |
| T2-08 | Duplicate detection (bỏ qua) và equivocation detection (ghi log, không thay thế vote đầu) trong VoteSet | `src/vote_set.py` | **Khôi** | 8 | 7 | 1 | 56 |
| T2-09 | Quorum counting: `has_quorum()` chỉ trả True khi có `>= 2f+1` validators **riêng biệt** | `src/vote_set.py` | **Bảo** | 9 | 6 | 1 | 54 |
| T2-10 | Unit test vote_set: duplicate bỏ qua, non-member từ chối, equivocation log, quorum chỉ đạt đủ validators | `tests/test_vote_set.py` | **Hiếu** | 9 | 6 | 1 | 54 |

### 2C — Block Store & Ledger (`src/block_store.py`, `src/ledger.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T2-11 | Block Store: `store_header()`, `store_body()`; enforce header-first rule (F-30) — body chỉ được xử lý sau header hợp lệ | `src/block_store.py` | **Khôi** | 8 | 6 | 1 | 48 |
| T2-12 | Ledger/State Store: append-only finalized chain + state snapshot; không bao giờ rollback | `src/ledger.py` | **Huy** | 8 | 7 | 1 | 56 |
| T2-13 | Atomic persist (F-52): ghi nguyên tử `finalized_height`, `finalized_hash`, state, nonces, block | `src/ledger.py` | **Hiếu** | 9 | 8 | 1 | 72 |
| T2-14 | Crash recovery (F-53): load từ snapshot, discard unfinalized proposals/votes | `src/ledger.py` | **Khánh** | 9 | 8 | 1 | 72 |

**✅ Milestone 2 done khi:** Invalid data không thể mutate pending/finalized state; block validation test suite pass.

---

## GIAI ĐOẠN 3 — Mạng Xác Định

> **Tổng: 16 task** — Bảo: 1 task | Hiếu: 4 task | Khôi: 4 task | Khánh: 4 task | Huy: 3 task

**Dependency:** Giai đoạn 2 (T2-01 → T2-14)

### 3A — Event Log (`src/event_log.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T3-01 | Định nghĩa canonical event schema: 18 event types (`SEND`, `DELIVER`, `DROP`, `DELAY`, `DUPLICATE`, `PEER_BLOCK`, `PEER_UNBLOCK`, `REJECT`, `PROPOSE`, `PREVOTE`, `PRECOMMIT`, `LOCK`, `TIMEOUT`, `ROUND_CHANGE`, `FINALIZE`, `EQUIVOCATION`, `CRASH`, `RESTART`) với fixed field order | `src/event_log.py` | **Khánh** | 8 | 5 | 1 | 40 |
| T3-02 | Canonical JSON Lines writer: fixed key order, không whitespace thừa, UTF-8, newline sau mỗi event | `src/event_log.py` | **Huy** | 8 | 5 | 1 | 40 |
| T3-03 | Đảm bảo `event_no` tăng monotonically và `logical_time` chính xác trong mọi event | `src/event_log.py` | **Huy** | 8 | 4 | 1 | 32 |

### 3B — Simulated Network (`src/network.py`, `src/scheduler.py`, `src/fault_injector.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T3-04 | Envelope type: `(sender, receiver, payload, logical_time, insertion_seq)`; serialize đúng | `src/network.py` | **Khánh** | 7 | 4 | 1 | 28 |
| T3-05 | Deterministic scheduler: priority queue `(logical_time, insertion_seq)`; tie-break theo insertion_seq | `src/scheduler.py` | **Hiếu** | 9 | 7 | 2 | 126 |
| T3-06 | Seeded PRNG (seed do scenario runner sở hữu): `Random(seed)` không bao giờ gọi `random.random()` global | `src/scheduler.py` | **Khôi** | 9 | 6 | 1 | 54 |
| T3-07 | Fault injector: drop / delay / duplicate / reorder từ scenario config; dùng PRNG từ T3-06 | `src/fault_injector.py` | **Khánh** | 8 | 7 | 2 | 112 |
| T3-08 | Bandwidth limit và rate limiting: kiểm tra bytes/tick không vượt `bandwidth_limit_bytes_per_tick` | `src/network.py` | **Hiếu** | 6 | 6 | 1 | 36 |
| T3-09 | Peer blocking/unblocking tạm thời: `block_peer(id)` / `unblock_peer(id)` log `PEER_BLOCK`/`PEER_UNBLOCK` | `src/network.py` | **Bảo** | 6 | 5 | 1 | 30 |
| T3-10 | Canonical iteration order: audit toàn bộ code, sửa mọi chỗ dùng dict/set iteration → dùng `sorted()` | toàn bộ `src/` | **Huy** | 9 | 6 | 1 | 54 |

### 3C — Message Router (`src/router.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T3-11 | Message Router: kiểm tra envelope shape, chain_id, sender identity, chữ ký; router không tin metadata — chỉ tin chữ ký | `src/router.py` | **Khôi** | 8 | 7 | 2 | 112 |
| T3-12 | Router ghi log `REJECT` với rejection code cụ thể cho từng guard thất bại | `src/router.py` | **Hiếu** | 7 | 5 | 1 | 35 |
| T3-13 | Router không relay object không hợp lệ — drop hoàn toàn sau khi log | `src/router.py` | **Khôi** | 8 | 4 | 1 | 32 |

### 3D — Scenario Runner (`src/scenario.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T3-14 | Scenario Runner: load config → khởi tạo nodes → seed PRNG → chạy simulation loop → shutdown | `src/scenario.py` | **Khánh** | 9 | 8 | 3 | 216 |
| T3-15 | Ghi `spec_version` và `config_fingerprint` (SHA-256 của sorted JSON config) vào đầu mỗi log | `src/scenario.py` | **Hiếu** | 7 | 4 | 1 | 28 |
| T3-16 | Assertion engine: sau simulation kiểm tra safety (không 2 hash cùng height) và liveness (chain tiến triển) | `src/scenario.py` | **Khôi** | 9 | 7 | 2 | 126 |

**✅ Milestone 3 done khi:** Scripted delivery sequence (duplicate/reorder) replay byte-identical.

---

## GIAI ĐOẠN 4 — Consensus Engine

> **Tổng: 12 task** — Bảo: 1 task | Hiếu: 3 task | Khôi: 3 task | Khánh: 3 task | Huy: 2 task

**Dependency:** Giai đoạn 3 (T3-01 → T3-16)

### 4A — Consensus State Machine (`src/consensus.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T4-01 | ConsensusState per height: `round`, `locked_block_hash`, `locked_round`, `valid_block_hash`, `prevotes`, `precommits` | `src/consensus.py` | **Hiếu** | 9 | 8 | 2 | 144 |
| T4-02 | Proposer selection: `validator_set[sorted][(height + round) % n]`; dùng sorted validator set từ T1-09 | `src/consensus.py` | **Khánh** | 9 | 5 | 1 | 45 |
| T4-03 | Proposal handler: proposer broadcast HEADER trước rồi BODY; non-proposer chờ proposal timeout rồi prevote NIL | `src/consensus.py` | **Khôi** | 9 | 8 | 2 | 144 |
| T4-04 | Prevote guard (F-35): prevote block nếu unlocked hoặc khớp lock; prevote block khác chỉ khi có quorum prevote later-round; ngược lại prevote NIL | `src/consensus.py` | **Hiếu** | 9 | 9 | 2 | 162 |
| T4-05 | Lock logic (F-36): quorum prevote non-NIL tại round r → set `locked_block_hash = block`, `locked_round = r`, `valid_block_hash = block` | `src/consensus.py` | **Khánh** | 9 | 8 | 1 | 72 |
| T4-06 | Precommit logic (F-37): quorum prevote non-NIL → precommit block; quorum prevote NIL hoặc timeout → precommit NIL | `src/consensus.py` | **Khôi** | 9 | 8 | 1 | 72 |
| T4-07 | Finalization (F-38): quorum precommit non-NIL → xác thực lại block → append ledger → commit state → reset consensus state → start height+1 round 0 | `src/consensus.py` | **Huy** | 10 | 9 | 2 | 180 |
| T4-08 | Round change (F-39): precommit timeout → tăng round → reset vote sets theo round → giữ nguyên locks | `src/consensus.py` | **Bảo** | 9 | 7 | 1 | 63 |
| T4-09 | "Gửi tối đa một vote" guard (F-33): enforce per `(height, round, phase)` — không ký 2 votes cùng phase | `src/consensus.py` | **Khánh** | 9 | 5 | 1 | 45 |

### 4B — Gossip & Crash Recovery (`src/gossip.py`, mở rộng `src/scenario.py`)

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T4-10 | Gossip Service: sau finalize relay block và votes tới peers; log `SEND` event | `src/gossip.py` | **Huy** | 8 | 7 | 2 | 112 |
| T4-11 | Crash simulation: dừng node tại logical_time chỉ định, xóa in-memory cache, giữ nguyên snapshot đã finalize; log `CRASH` | `src/scenario.py` | **Hiếu** | 8 | 6 | 1 | 48 |
| T4-12 | Restart simulation: load snapshot từ ledger, rebuild consensus state từ network gossip; log `RESTART` | `src/scenario.py` | **Khôi** | 8 | 7 | 1 | 56 |

**✅ Milestone 4 done khi:** T1, T2, T5, T6, T7 pass với safety assertions bật.

---

## GIAI ĐOẠN 5 — Test Suite & Nộp Bài

> **Tổng: 11 task** — Bảo: 1 task | Hiếu: 2 task | Khôi: 2 task | Khánh: 3 task | Huy: 3 task

**Dependency:** Giai đoạn 4 (T4-01 → T4-12)

### 5A — End-to-End Test Scenarios

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T5-01 | Viết scenario T1 (normal run): 8 nodes, no fault, max_height=3 → assert mọi node finalize cùng height/hash/state_hash | `config/scenario_t1.json` + `tests/test_t1.py` | **Khánh** | 9 | 5 | 1 | 45 |
| T5-02 | Viết scenario T2 (duplicate + reorder): inject duplicate messages và reorder → assert vote count đúng, không finalize xung đột | `config/scenario_t2.json` + `tests/test_t2.py` | **Khánh** | 9 | 6 | 1 | 54 |
| T5-03 | Viết scenario T3 (bad signature + wrong domain): inject messages với signature sai, domain sai → assert router từ chối + log, không state transition | `config/scenario_t3.json` + `tests/test_t3.py` | **Hiếu** | 9 | 6 | 1 | 54 |
| T5-04 | Viết scenario T4 (replay + duplicate tx): submit cùng tx_id 2 lần → assert tx_id chỉ được apply tối đa 1 lần | `config/scenario_t4.json` + `tests/test_t4.py` | **Khôi** | 9 | 6 | 1 | 54 |
| T5-05 | Viết scenario T5 (drop/delay): drop và delay messages trước synchrony → assert safety bất biến, không 2 block hash cùng height | `config/scenario_t5.json` + `tests/test_t5.py` | **Huy** | 9 | 7 | 2 | 126 |
| T5-06 | Viết scenario T6 (proposer crash): proposer im lặng tại height 1 → assert round change xảy ra, proposer khác finalize được | `config/scenario_t6.json` + `tests/test_t6.py` | **Huy** | 9 | 7 | 1 | 63 |
| T5-07 | Viết scenario T7 (equivocation): f=2 validators gửi conflicting votes → assert equivocation logged, honest nodes không finalize xung đột | `config/scenario_t7.json` + `tests/test_t7.py` | **Khôi** | 9 | 8 | 2 | 144 |
| T5-08 | Viết scenario T8 (determinism): cùng seed chạy 2 lần → assert log bytes byte-identical, state hash giống nhau | `config/scenario_t8.json` + `tests/test_t8.py` | **Khánh** | 10 | 5 | 1 | 50 |

### 5B — Summary, Report & Submit

| Task ID | Công việc | File | Người | Ưu tiên | Độ khó | Ngày | Trọng số |
|---------|-----------|------|-------|---------|--------|------|----------|
| T5-09 | Export compact summary (`src/summary.py`): `(height, hash)` per node, state hash cuối, rejection counts theo lý do, SHA-256 của log | `src/summary.py` | **Hiếu** | 7 | 5 | 1 | 35 |
| T5-10 | `--verify-determinism` script: chạy T8 scenario 2 lần, diff log bytes + state hash, exit 0 nếu identical | `tests/verify_determinism.py` | **Bảo** | 9 | 4 | 1 | 36 |
| T5-11 | Viết `REPORT.pdf`: kết quả T1–T8 thực tế, phân tích safety/liveness, ≤ 10 trang | `REPORT.pdf` | **Huy** | 10 | 5 | 2 | 100 |

**✅ Milestone 5 done khi:** Clean checkout chạy một lệnh → T1–T8 all pass, `--verify-determinism` pass, đủ artifacts.

---

---

## Bảng Tổng Hợp Phân Công Theo Thành Viên

### Phạm Nguyễn Gia Bảo (Team Leader — 1 task coding + 2 task management/giai đoạn)

**Phần G0 — đã hoàn thành:**

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G0 | T0-01→T0-06 | Toàn bộ scaffold + event_log + scenario_runner | **241** | ✅ Done |

**Phần G1–G5 — coding tasks:**

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | T1-09 | Load/validate identity fixtures | 21 | ✅ Done |
| G1 | T1-15 | Unit test transaction rejection *(chuyển từ Hiếu)* | 45 | ✅ Done |
| G2 | T2-05 | Unit test block validation *(chuyển từ Hiếu)* | 54 | ✅ Done — 35 tests pass |
| G2 | T2-09 | Quorum counting `has_quorum()` | 54 | 🔲 Chưa làm |
| G3 | T3-09 | Peer blocking/unblocking | 30 | 🔲 Chưa làm |
| G4 | T4-08 | Round change logic | 63 | 🔲 Chưa làm |
| G5 | T5-10 | `--verify-determinism` script | 36 | 🔲 Chưa làm |
| **Subtotal coding G1–G5** | | | **303** | |

**Phần G1–G5 — management tasks (tính điểm):**

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | MG-PR | Review & approve toàn bộ PR giai đoạn 1 | 80 | 🔲 |
| G1 | MG-INT | Tích hợp milestone 1, resolve conflicts, full test suite | 28 | 🔲 |
| G2 | MG-PR | Review & approve toàn bộ PR giai đoạn 2 | 80 | 🔲 |
| G2 | MG-INT | Tích hợp milestone 2 | 28 | 🔲 |
| G3 | MG-PR | Review & approve toàn bộ PR giai đoạn 3 | 80 | 🔲 |
| G3 | MG-INT | Tích hợp milestone 3 | 28 | 🔲 |
| G4 | MG-PR | Review & approve toàn bộ PR giai đoạn 4 | 80 | 🔲 |
| G4 | MG-INT | Tích hợp milestone 4 | 28 | 🔲 |
| G5 | MG-PR | Review & approve toàn bộ PR giai đoạn 5 | 80 | 🔲 |
| G5 | MG-INT | Tích hợp milestone 5, đóng gói nộp bài | 28 | 🔲 |
| **Subtotal management G1–G5** | | | **540** | |

| Hạng mục | Trọng số |
|----------|----------|
| G0 coding | 241 |
| G1–G5 coding | 303 |
| G1–G5 management | 540 |
| **Tổng Bảo** | **1.084** |

### Nguyễn Minh Hiếu (3–4 tasks/giai đoạn)

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | T1-08 | Unit test crypto | 45 | ✅ Done |
| G1 | T1-14 | Unit test determinism executor | 45 | ✅ Done — 22 tests pass |
| G2 | T2-10 | Unit test vote_set | 54 | 🔲 Chưa làm |
| G2 | T2-13 | Atomic persist ledger | 72 | 🔲 Chưa làm |
| G3 | T3-05 | Deterministic scheduler | 126 | 🔲 Chưa làm |
| G3 | T3-08 | Bandwidth + rate limit | 36 | 🔲 Chưa làm |
| G3 | T3-12 | Router rejection logging | 35 | 🔲 Chưa làm |
| G3 | T3-15 | Ghi spec_version + config fingerprint | 28 | 🔲 Chưa làm |
| G4 | T4-01 | ConsensusState model | 144 | 🔲 Chưa làm |
| G4 | T4-04 | Prevote guard (phức tạp nhất) | 162 | 🔲 Chưa làm |
| G4 | T4-11 | Crash simulation | 48 | 🔲 Chưa làm |
| G5 | T5-03 | Scenario T3 (bad sig/domain) | 54 | 🔲 Chưa làm |
| G5 | T5-09 | Export compact summary | 35 | 🔲 Chưa làm |
| **Tổng** | **13 tasks** | *(T1-15 → Bảo, T2-05 → Bảo)* | **884** | |

### Võ Kim Khôi (3–4 tasks/giai đoạn)

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | T1-06 | Ed25519 `sign()` với domain separation | 54 | ✅ Done |
| G1 | T1-07 | Ed25519 `verify()` | 54 | ✅ Done |
| G1 | T1-13 | Deterministic executor | 144 | ✅ Done — 22 tests pass |
| G2 | T2-03 | Header validation guards (F-26) | 126 | 🔲 Chưa làm |
| G2 | T2-04 | Block Body + candidate validation | 126 | 🔲 Chưa làm |
| G2 | T2-08 | Duplicate + equivocation detection | 56 | 🔲 Chưa làm |
| G2 | T2-11 | Block Store + header-first rule | 48 | 🔲 Chưa làm |
| G3 | T3-06 | Seeded PRNG | 54 | 🔲 Chưa làm |
| G3 | T3-11 | Message Router | 112 | 🔲 Chưa làm |
| G3 | T3-13 | Router không relay invalid object | 32 | 🔲 Chưa làm |
| G3 | T3-16 | Assertion engine safety/liveness | 126 | 🔲 Chưa làm |
| G4 | T4-03 | Proposal handler | 144 | 🔲 Chưa làm |
| G4 | T4-06 | Precommit logic | 72 | 🔲 Chưa làm |
| G4 | T4-12 | Restart simulation | 56 | 🔲 Chưa làm |
| G5 | T5-04 | Scenario T4 (replay/duplicate tx) | 54 | 🔲 Chưa làm |
| G5 | T5-07 | Scenario T7 (equivocation f validators) | 144 | 🔲 Chưa làm |
| **Tổng** | **16 tasks** | | **1.402** | |

### Lê Quốc Khánh (3–4 tasks/giai đoạn)

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | T1-01 | Canonical encoder cơ bản | 45 | ✅ Done |
| G1 | T1-02 | `encode_optional_hash` | 32 | ✅ Done |
| G1 | T1-03 | Sorted map encoder *(gộp vào cùng commit T1-01/02)* | 40 | ✅ Done |
| G1 | T1-05 | `hash_bytes()` SHA-256 | 27 | ✅ Done |
| G1 | T1-12 | Transaction object + validation | 126 | ✅ Done |
| G2 | T2-01 | Block Header object | 126 | 🔲 Chưa làm |
| G2 | T2-07 | VoteSet storage | 48 | 🔲 Chưa làm |
| G2 | T2-14 | Crash recovery (load snapshot) | 72 | 🔲 Chưa làm |
| G3 | T3-01 | Canonical event schema (18 types) | 40 | 🔲 Chưa làm |
| G3 | T3-04 | Envelope type | 28 | 🔲 Chưa làm |
| G3 | T3-07 | Fault injector (drop/delay/dup/reorder) | 112 | 🔲 Chưa làm |
| G3 | T3-14 | Scenario Runner chính | 216 | 🔲 Chưa làm |
| G4 | T4-02 | Proposer selection formula | 45 | 🔲 Chưa làm |
| G4 | T4-05 | Lock logic | 72 | 🔲 Chưa làm |
| G4 | T4-09 | "Tối đa 1 vote" guard | 45 | 🔲 Chưa làm |
| G5 | T5-01 | Scenario T1 (normal run) | 45 | 🔲 Chưa làm |
| G5 | T5-02 | Scenario T2 (dup + reorder) | 54 | 🔲 Chưa làm |
| G5 | T5-08 | Scenario T8 (determinism) | 50 | 🔲 Chưa làm |
| **Tổng** | **17 tasks** | *(T1-03 ghi nhận thêm do thực hiện vượt phân công; T1-05 và T1-12 hoàn thành trong G1)* | **1.250** | |

### Trương Nhật Huy (3–4 tasks/giai đoạn)

| Giai đoạn | Task | Mô tả ngắn | Trọng số | Trạng thái |
|-----------|------|------------|----------|------------|
| G1 | T1-03 | ~~Sorted map encoder~~ → **đã được Khánh thực hiện** | ~~40~~ | ✅ Done (Khánh) |
| G1 | T1-04 | Unit test encoding: tất cả 5 hàm + sorted_map đã có test đầy đủ | 36 | ✅ Done — 47 tests pass |
| G1 | T1-10 | State map (sorted key-value) | 80 | ✅ Done |
| G1 | T1-11 | State commitment hash | 48 | ✅ Done |
| G2 | T2-02 | `tx_root` computation | 40 | 🔲 Chưa làm |
| G2 | T2-06 | Vote object + guards | 48 | 🔲 Chưa làm |
| G2 | T2-12 | Ledger append-only + snapshot | 56 | 🔲 Chưa làm |
| G3 | T3-02 | JSON Lines writer canonical | 40 | 🔲 Chưa làm |
| G3 | T3-03 | event_no monotonic + logical_time | 32 | 🔲 Chưa làm |
| G3 | T3-10 | Canonical iteration order audit | 54 | 🔲 Chưa làm |
| G4 | T4-07 | Finalization pipeline (quan trọng nhất) | 180 | 🔲 Chưa làm |
| G4 | T4-10 | Gossip Service | 112 | 🔲 Chưa làm |
| G5 | T5-05 | Scenario T5 (drop/delay) | 126 | 🔲 Chưa làm |
| G5 | T5-06 | Scenario T6 (proposer crash) | 63 | 🔲 Chưa làm |
| G5 | T5-11 | Viết REPORT.pdf | 100 | 🔲 Chưa làm |
| **Tổng** | **14 tasks thực tế** | *(T1-03 chuyển sang Khánh; T1-04 hoàn thành đầy đủ)* | **1.015** | |

---

## Tóm Tắt So Sánh Tải Công Việc

> **Cập nhật trạng thái: 2026-08-02** — G1 hoàn thành 100%. Bao gồm G0, coding G1–G5, và management tasks của Bảo.

| Thành viên | Tổng trọng số | Breakdown | Tasks đã Done | Ghi chú |
|------------|---------------|-----------|---------------|---------|
| **Bảo** | **1.084** | G0: 241 + Coding G1–G5: 303 + Management G1–G5: 540 | G0 ✅, T1-09 ✅, T1-15 ✅ | TL: review PR + tích hợp milestone + 7 coding tasks G1–G5 |
| **Hiếu** | **884** | 13 tasks coding G1–G5 | T1-08 ✅, **T1-14 ✅** | T1-14 hoàn thành (22 tests pass) |
| **Khôi** | **1.402** | 16 tasks coding G1–G5 | T1-06 ✅, T1-07 ✅, **T1-13 ✅** | T1-13 executor hoàn thành trong G1 |
| **Khánh** | **1.250** | 17 tasks coding G1–G5 | **T1-01 ✅, T1-02 ✅, T1-03 ✅, T1-05 ✅, T1-12 ✅** | 5/17 tasks G1 done |
| **Huy** | **1.015** | 14 tasks coding G1–G5 | **T1-04 ✅, T1-10 ✅, T1-11 ✅** | 3/14 tasks G1 done |
| **Trung bình** | **1.127** | | | |

### Trạng Thái Tổng Quan Theo Giai Đoạn

| Giai đoạn | Tổng task | Đã xong | Còn lại | Trạng thái |
|-----------|-----------|---------|---------|------------|
| G0 | 6 | 6 | 0 | ✅ HOÀN THÀNH |
| G1 | 15 | 15 (tất cả) | 0 | ✅ HOÀN THÀNH — 110 tests xanh |
| G2 | 14 | 0 | 14 | 🔲 Chưa bắt đầu |
| G3 | 16 | 0 | 16 | 🔲 Chưa bắt đầu |
| G4 | 12 | 0 | 12 | 🔲 Chưa bắt đầu |
| G5 | 11 | 0 | 11 | 🔲 Chưa bắt đầu |

> **✅ G1 hoàn thành (2026-08-02):** T1-13 (`src/executor.py`) và T1-14 (`tests/test_executor.py`) đã được implement và pass 22 tests. Tổng cộng 110 tests xanh.
>
> **Việc cần làm tiếp theo:** Bắt đầu **Giai đoạn 2** — Data Model và Xác Thực (T2-01 → T2-14).

---

## Timeline Tổng Quan

```
Tuần 1  │ G1: tất cả 5 người làm song song các phần của mình
Tuần 2  │ G2: tất cả 5 người tiếp tục (Bảo review G1 PRs)
Tuần 3  │ G3: tất cả 5 người (Bảo review G2 PRs)
Tuần 4  │ G4: tất cả 5 người (Bảo review G3 PRs) — Milestone 3
Tuần 5  │ G5: tất cả 5 người (Bảo review G4 PRs) — Milestone 4
Tuần 6  │ Run T1–T8, viết report, đóng gói (Bảo lead submit)
```

---

## Quy Tắc Làm Việc

| Quy tắc | Mô tả |
|---------|-------|
| **Branch per task** | Mỗi người = 1 branch, commit tên task và tạo PR để merge vào `main` |
| **Test đi kèm** | Mọi PR coding phải có unit test tương ứng |
| **Review bởi Bảo** | Bảo review và approve tất cả PR trước khi merge |
| **Không wall-clock** | Tuyệt đối không dùng `time.time()`, `datetime.now()`, `random.random()` global |
| **Canonical sort** | Mọi loop trên dict/set phải qua `sorted()` |
| **Cập nhật file** | Sau khi hoàn thành task, cập nhật `% hoàn thành` trong file Excel gantt chart|
