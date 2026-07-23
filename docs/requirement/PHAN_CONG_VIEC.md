# Phân Chia Công Việc — Lab 01 Blockchain Simulator

> Tài liệu này chia toàn bộ yêu cầu thành các công đoạn, task cụ thể với thứ tự phụ thuộc rõ ràng. Mỗi task có ID duy nhất để tham chiếu.

---

## Tổng Quan Công Đoạn

```
GIAI ĐOẠN 0: Scaffold
         ↓
GIAI ĐOẠN 1: Primitive (Mật mã + Thực thi)
         ↓
GIAI ĐOẠN 2: Data Model + Validation
         ↓
GIAI ĐOẠN 3: Simulated Network
         ↓
GIAI ĐOẠN 4: Consensus Engine
         ↓
GIAI ĐOẠN 5: Test Suite + Nộp bài
```

---

## GIAI ĐOẠN 0 — Repository Scaffold

**Mục tiêu:** Tạo cấu trúc dự án và nền tảng cấu hình.

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T0-01 | Tạo thư mục `src/`, `tests/`, `logs/`, `config/` | Cấu trúc thư mục | — |
| T0-02 | Viết `README.md` root với hướng dẫn cài đặt và lệnh test | `README.md` | T0-01 |
| T0-03 | Tạo `config/default.json` với: block capacity, timeout schedule, retention policy | File cấu hình mặc định | T0-01 |
| T0-04 | Tạo fixture khóa validator xác định (8 cặp khóa Ed25519 cố định cho test) | `config/validator_keys.json` | T0-01 |
| T0-05 | Tạo file kịch bản mẫu (scenario config) với đầy đủ các trường yêu cầu | `config/scenario_*.json` | T0-03, T0-04 |
| T0-06 | Viết entry point test duy nhất (no-op scenario) tạo canonical log | `tests/run_all.sh` hoặc script tương đương | T0-02, T0-05 |

**✅ Milestone 0 done khi:** No-op scenario chạy và tạo canonical log.

---

## GIAI ĐOẠN 1 — Primitive Xác Định

**Mục tiêu:** Xây dựng nền tảng mật mã và thực thi không có trạng thái ngoài.

### 1A. Mã Hóa Chuẩn (Canonical Encoding)

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T1-01 | Triển khai canonical encoder: unsigned 64-bit big-endian, boolean 1 byte, byte string với u32 length prefix | `src/encoding.{ext}` | T0-01 |
| T1-02 | Triển khai encoder cho optional field (presence byte + 32 byte hash) | Mở rộng encoding module | T1-01 |
| T1-03 | Triển khai sorted map encoder (sắp xếp theo UTF-8 key bytes) | Mở rộng encoding module | T1-01 |
| T1-04 | Unit test: byte giống nhau cho giá trị ngữ nghĩa bằng nhau | `tests/test_encoding.*` | T1-01, T1-02, T1-03 |

### 1B. Mật Mã (Cryptography)

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T1-05 | Tích hợp SHA-256; viết helper `hash_bytes()` | `src/crypto.{ext}` | T1-01 |
| T1-06 | Tích hợp Ed25519; viết `sign(domain, payload)` với domain separation | Mở rộng crypto module | T1-05 |
| T1-07 | Viết `verify(domain, pubkey, payload, signature)` | Mở rộng crypto module | T1-06 |
| T1-08 | Unit test: chữ ký chỉ xác thực đúng domain + public key; thay đổi bất kỳ trường nào → fail | `tests/test_crypto.*` | T1-06, T1-07 |
| T1-09 | Load/validate identity fixtures từ T0-04 | `src/identity.{ext}` | T0-04, T1-07 |

### 1C. State và Thực Thi

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T1-10 | Triển khai sorted key-value state map | `src/state.{ext}` | T1-01 |
| T1-11 | Triển khai state commitment: `SHA256(entry_count \|\| sorted(key,val) pairs)` | Mở rộng state module | T1-05, T1-10 |
| T1-12 | Triển khai Transaction object với xác thực (chain_id, nonce, namespace, size limits) | `src/transaction.{ext}` | T1-01, T1-06, T1-10 |
| T1-13 | Triển khai deterministic executor: áp dụng transaction list → post-state + nonces | `src/executor.{ext}` | T1-10, T1-12 |
| T1-14 | Unit test: cùng block thực thi 2 lần → byte/hash giống nhau | `tests/test_executor.*` | T1-13 |
| T1-15 | Unit test: namespace sai, nonce sai, tx trùng, tx không hợp lệ trong block đều bị từ chối | `tests/test_transaction.*` | T1-12, T1-13 |

**✅ Milestone 1 done khi:** Tất cả unit test crypto/state pass; determinism xác nhận.

---

## GIAI ĐOẠN 2 — Data Model và Xác Thực

**Mục tiêu:** Block header, body, vote và tất cả validation guards.

### 2A. Block Header và Body

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T2-01 | Triển khai Block Header object; `block_hash = SHA256(canonical signed header)` | `src/block.{ext}` | T1-01, T1-06 |
| T2-02 | Triển khai `tx_root` computation: `SHA256(count \|\| tx_ids[])` | Mở rộng block module | T1-05, T1-12 |
| T2-03 | Triển khai header validation (guard F-26: chain_id, height, round, parent hash, proposer, signature) | `src/block_validator.{ext}` | T2-01, T1-07 |
| T2-04 | Triển khai Block Body và full candidate validation (guard F-27–F-29) | Mở rộng block module | T2-01, T1-13 |
| T2-05 | Unit test: parent sai, proposer sai, height sai, tx_root sai, state hash sai, signature sai đều bị bắt | `tests/test_block.*` | T2-03, T2-04 |

### 2B. Vote và Vote Set

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T2-06 | Triển khai Vote object với validation guards (F-40) | `src/vote.{ext}` | T1-01, T1-07 |
| T2-07 | Triển khai VoteSet: lưu votes theo `(height, round, phase, validator)` | `src/vote_set.{ext}` | T2-06 |
| T2-08 | Logic duplicate detection và equivocation detection trong VoteSet | Mở rộng vote_set | T2-07 |
| T2-09 | Quorum counting: chỉ đạt `2f+1` khi có đủ validators riêng biệt | Mở rộng vote_set | T2-07 |
| T2-10 | Unit test: vote trùng bị bỏ qua, non-member bị từ chối, equivocation bị log, quorum đúng | `tests/test_vote_set.*` | T2-07, T2-08, T2-09 |

### 2C. Block Store và Ledger

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T2-11 | Triển khai Block Store: lưu headers và bodies; header-first rule (F-30) | `src/block_store.{ext}` | T2-01, T2-04 |
| T2-12 | Triển khai Ledger/State Store: finalized chain append-only + state snapshot | `src/ledger.{ext}` | T1-10, T2-01 |
| T2-13 | Persist atomically: `finalized_height`, `finalized_hash`, state, nonces, block (F-52) | Mở rộng ledger | T2-12 |
| T2-14 | Crash recovery: load từ snapshot, discard unfinalized (F-53) | Mở rộng ledger | T2-13 |

**✅ Milestone 2 done khi:** Invalid data không thể mutate pending/finalized state; block validation test suite pass.

---

## GIAI ĐOẠN 3 — Mạng Xác Định

**Mục tiêu:** Simulated network với full fault injection và deterministic replay.

### 3A. Event Log

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T3-01 | Định nghĩa canonical event schema: tất cả 18+ event types với fixed field order | `src/event_log.{ext}` | T1-01 |
| T3-02 | Triển khai canonical JSON Lines writer (fixed key order, UTF-8, newline-terminated) | Mở rộng event_log | T3-01 |
| T3-03 | Đảm bảo `event_no` tăng monotonically và `logical_time` đúng trong mọi event | Mở rộng event_log | T3-02 |

### 3B. Simulated Network

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T3-04 | Triển khai Envelope type (bao gồm sender, receiver, payload, logical_time) | `src/network.{ext}` | T3-01 |
| T3-05 | Triển khai deterministic scheduler: priority queue `(logical_time, insertion_seq)` | `src/scheduler.{ext}` | T3-04 |
| T3-06 | Triển khai seeded PRNG cho fault injection; đảm bảo scenario runner sở hữu seed | Mở rộng scheduler | T3-05 |
| T3-07 | Triển khai drop, delay, duplicate, reorder injection từ scenario config | `src/fault_injector.{ext}` | T3-06 |
| T3-08 | Triển khai giới hạn băng thông và rate limiting | Mở rộng network | T3-05 |
| T3-09 | Triển khai peer blocking/unblocking (tạm thời) | Mở rộng network | T3-04 |
| T3-10 | Đảm bảo iteration order cho validators/peers/messages là canonical bytes order (không phải map order) | Audit toàn bộ code | T3-05 |

### 3C. Message Router

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T3-11 | Triển khai Message Router: kiểm tra envelope shape, chain_id, sender identity, signature | `src/router.{ext}` | T2-03, T2-06, T3-04 |
| T3-12 | Router log rejection với mã cụ thể cho từng guard thất bại | Mở rộng router | T3-11, T3-02 |
| T3-13 | Router không relay invalid object | Mở rộng router | T3-11 |

### 3D. Scenario Runner

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T3-14 | Triển khai Scenario Runner: load config, khởi tạo nodes, seed PRNG, chạy simulation | `src/scenario.{ext}` | T3-05, T3-07 |
| T3-15 | Ghi version spec và fingerprint cấu hình vào log | Mở rộng scenario | T3-14, T3-02 |
| T3-16 | Triển khai assertion engine: kiểm tra safety/liveness sau simulation | Mở rộng scenario | T3-14 |

**✅ Milestone 3 done khi:** Scripted delivery sequence (duplicate/reorder) replay byte-identical.

---

## GIAI ĐOẠN 4 — Consensus Engine

**Mục tiêu:** Triển khai đầy đủ giao thức đồng thuận và crash recovery.

### 4A. State Machine Đồng Thuận

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T4-01 | Triển khai ConsensusState per height: round, locked_block_hash, locked_round, valid_block_hash | `src/consensus.{ext}` | T2-07, T2-11 |
| T4-02 | Proposer selection: `(height + round) mod n` trong validator set đã sắp xếp | Mở rộng consensus | T4-01 |
| T4-03 | Proposal handler: broadcast header → body; timeout handling | Mở rộng consensus | T4-01, T3-04 |
| T4-04 | Prevote guard: kiểm tra unlock/lock condition, later-round quorum evidence | Mở rộng consensus | T4-01, T2-07 |
| T4-05 | Lock logic: update locked_block_hash và locked_round khi quorum prevote | Mở rộng consensus | T4-04 |
| T4-06 | Precommit logic: quorum prevote → precommit; NIL quorum hoặc timeout → precommit NIL | Mở rộng consensus | T4-05 |
| T4-07 | Finalization logic: quorum precommit → xác thực lại → append ledger → commit state → start next height | Mở rộng consensus | T4-06, T2-12 |
| T4-08 | Round change logic: precommit timeout → increment round → reset vote sets → giữ locks | Mở rộng consensus | T4-06 |
| T4-09 | "Gửi tối đa một vote" guard cho mỗi `(height, round, phase)` | Mở rộng consensus | T4-04 |

### 4B. Gossip và Recovery

| Task ID | Công việc | Đầu à | Phụ thuộc |
|---|---|---|---|
| T4-10 | Triển khai Gossip Service: relay finalized blocks và votes | `src/gossip.{ext}` | T3-04, T4-07 |
| T4-11 | Crash simulation: dừng node, xóa cache, giữ snapshot | Mở rộng scenario | T2-13, T3-14 |
| T4-12 | Restart simulation: load snapshot, rebuild từ network traffic | Mở rộng scenario | T4-11, T2-14 |

**✅ Milestone 4 done khi:** T1, T2, T5, T6, T7 pass với safety assertions bật.

---

## GIAI ĐOẠN 5 — Test Suite và Nộp Bài

**Mục tiêu:** Hoàn thiện toàn bộ test, báo cáo và đóng gói nộp bài.

### 5A. Hoàn Thiện End-to-End Tests

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T5-01 | Viết kịch bản T3: invalid signature + wrong domain | `config/scenario_t3.json` + assertion | T3-11 |
| T5-02 | Viết kịch bản T4: replay + duplicate transaction | `config/scenario_t4.json` + assertion | T1-12, T4-07 |
| T5-03 | Viết kịch bản T8: same seed × 2 runs, so sánh log byte + state hash | `tests/test_t8.*` | T3-14, T4-07 |
| T5-04 | Viết `--verify-determinism` script/flag: chạy 2 lần, diff log bytes + state hash | `tests/verify_determinism.sh` | T5-03 |
| T5-05 | Đảm bảo một lệnh duy nhất chạy toàn bộ T1–T8 và trả non-zero khi fail | `README.md` + entry point | T5-01 đến T5-04 |

### 5B. Tóm Tắt Kịch Bản và Báo Cáo

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T5-06 | Triển khai export compact summary: `(height, hash)` per node, state hash, rejection counts, log SHA-256 | `src/summary.{ext}` | T4-07, T3-02 |
| T5-07 | Chạy toàn bộ T1–T8, thu thập kết quả thực tế | Dữ liệu cho báo cáo | T5-05 |
| T5-08 | Viết `REPORT.pdf`: kết quả test, phân tích safety/liveness, ngắn gọn ≤ 10 trang | `REPORT.pdf` | T5-07 |

### 5C. Kiểm Tra và Đóng Gói

| Task ID | Công việc | Đầu ra | Phụ thuộc |
|---|---|---|---|
| T5-09 | Kiểm tra cấu trúc submission: `src/`, `tests/`, `logs/`, `config/`, `README.md`, `REPORT.pdf` | Checklist | T5-08 |
| T5-10 | Clean checkout: clone mới, chạy một lệnh, xác nhận toàn bộ T1–T8 pass | CI / manual verify | T5-09 |
| T5-11 | Đóng gói ZIP theo đúng tên nhóm | File ZIP nộp bài | T5-10 |

**✅ Milestone 5 done khi:** Clean checkout chạy mọi test từ một lệnh và tạo đủ artifacts.

---

## Biểu Đồ Phụ Thuộc Tóm Tắt

```
G0 (Scaffold)
  └── G1A (Encoding) → G1B (Crypto) → G1C (State/Exec)
        └── G2A (Block Header/Body)
        └── G2B (Vote/VoteSet)
        └── G2C (BlockStore/Ledger)
              └── G3A (Event Log) → G3B (Network) → G3C (Router) → G3D (Scenario)
                    └── G4A (Consensus State Machine)
                    └── G4B (Gossip/Recovery)
                          └── G5A (E2E Tests)
                          └── G5B (Summary/Report)
                          └── G5C (Package/Submit)
```

---

## Gợi Ý Phân Công Nhóm (4 người)

| Thành viên | Công đoạn chính | Song song |
|---|---|---|
| **Dev 1 - Primitive** | G1A, G1B, G1C | — |
| **Dev 2 - Data & Storage** | G2A, G2B, G2C | Sau Dev 1 |
| **Dev 3 - Network & Simulation** | G3A, G3B, G3C, G3D | Song song với Dev 2 |
| **Dev 4 - Consensus & QA** | G4A, G4B, G5A, G5B, G5C | Sau Dev 2 & Dev 3 |

> Nếu ít hơn 4 người: ghép G1+G2 cho một người, G3+G4 cho người khác, G5 chia đều.

---

## Danh Sách Checklist Nộp Bài

- [ ] `src/` — toàn bộ source code
- [ ] `tests/` — unit tests và e2e tests
- [ ] `logs/` — log kịch bản T1–T8
- [ ] `config/` — `default.json`, fixture keys, scenario configs
- [ ] `README.md` — hướng dẫn cài đặt và **một lệnh chạy tất cả test**
- [ ] `REPORT.pdf` — tối đa 10 trang
- [ ] T1–T8 tất cả pass từ một lệnh
- [ ] `--verify-determinism` (T8) pass
- [ ] Folder và ZIP đặt tên đúng theo tên nhóm
