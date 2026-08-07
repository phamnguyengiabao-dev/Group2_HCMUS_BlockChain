# Lab 01 — Blockchain Layer-1 Simulator (Python)

Mô phỏng blockchain Layer-1 tối giản với đồng thuận Tendermint-inspired (PREVOTE/PRECOMMIT), mạng P2P mô phỏng có fault injection, thực thi trạng thái key-value xác định, và bộ kiểm thử có thể tái tạo.

---

## Yêu cầu hệ thống

- Python **3.10+**
- pip

Thư viện phụ thuộc (`requirements.txt`):

| Thư viện | Phiên bản tối thiểu | Mục đích |
|---|---|---|
| `cryptography` | 41.0.0 | Ed25519 signing/verification |
| `pytest` | 7.4.0 | Test runner |
| `pytest-cov` | 4.1.0 | Đo độ phủ kiểm thử |

---

## Cài đặt

```bash
pip install -r requirements.txt
```

---

## Chạy toàn bộ test suite (một lệnh)

```bash
python -m pytest tests/ -v
```

Lệnh này chạy **421 tests** bao gồm unit tests, integration tests, và tất cả 8 kịch bản end-to-end (T1–T8).

### Chạy theo kịch bản cụ thể

```bash
# T1 - Normal run, 8 nodes, no faults
python -m pytest tests/test_t1.py -v

# T2 - Duplicate + reorder messages
python -m pytest tests/test_t2.py -v

# T3 - Bad signature / wrong domain
python -m pytest tests/test_t3.py -v

# T4 - Replay / duplicate transactions
python -m pytest tests/test_t4.py -v

# T5 - Drop/delay before synchrony
python -m pytest tests/test_t5.py -v

# T6 - Proposer crash / round change
python -m pytest tests/test_t6.py -v

# T7 - Byzantine equivocation (f=2 validators)
python -m pytest tests/test_t7.py -v

# T8 - Determinism: same seed → byte-identical logs
python -m pytest tests/test_t8.py -v
```

### Kiểm tra tính tất định (determinism)

```bash
python tests/verify_determinism.py
```

Output mẫu:
```
PASS — both runs produced identical logs (SHA-256: 2b5ab69b8f37ce1d09e83fbfe127f3b03a87f9bc12f759778774f2550a5344ef)
```

### Đo độ phủ kiểm thử

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing
```

Độ phủ hiện tại: **~90%** trên toàn bộ `src/`.

---

## Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────────┐
│                          scenario.py                                │
│   ScenarioRunner: load → seed Scheduler → Network → FaultInjector  │
│   → run simulation → check_assertions (safety/liveness)            │
└────────┬───────────────────────────┬────────────────────────────────┘
         │                           │
┌────────▼───────────┐   ┌───────────▼──────────────────────┐
│    event_log.py    │   │    consensus.py                  │
│  Canonical JSONL   │   │  ConsensusState, proposer sel.   │
│  18 event types    │   │  prevote/precommit/lock/finalize │
└────────────────────┘   └───────────┬──────────────────────┘
                                     │
         ┌───────────────────────────┼─────────────────────────────────┐
         │                           │                                 │
┌────────▼───────┐   ┌───────────────▼──────┐   ┌────────────────────▼───┐
│  network.py    │   │    ledger.py         │   │   block.py / block_    │
│  Deterministic │   │  Append-only chain   │   │   validator.py         │
│  Network sim.  │   │  + atomic persist    │   │   Header, Body, valid. │
│  + bandwidth   │   └──────────────────────┘   └────────────────────────┘
└────────┬───────┘
         │
┌────────▼───────────────────────────────────────┐
│  TẦNG NỀN (không phụ thuộc gì phía trên)       │
│  crypto.py    encoding.py    state.py           │
│  SHA-256      Canonical      Key-value          │
│  Ed25519      byte encode    map + hash         │
└────────────────────────────────────────────────┘
```

---

## Mô tả các module

| Module | Trách nhiệm |
|---|---|
| `src/crypto.py` | SHA-256 hash, Ed25519 sign/verify với domain separation |
| `src/encoding.py` | Canonical byte encoding (uint64, bool, bytes, str, sorted map) |
| `src/state.py` | Key-value state map với canonical ordering và state commitment hash |
| `src/transaction.py` | Transaction model, canonical encoding, 9-bước validation |
| `src/identity.py` | Load và cross-validate 8 validator keypairs |
| `src/event_log.py` | Canonical JSONL event logger, 18 event types, monotonic event_no |
| `src/block.py` | BlockHeader, tx_root computation, block body validation |
| `src/block_validator.py` | Header validation guards (chain_id, height, round, proposer, sig) |
| `src/block_store.py` | Header-first block storage, pending candidate store |
| `src/vote.py` | Vote object, canonical encoding, acceptance guards (F-40) |
| `src/vote_set.py` | Vote aggregation, duplicate/equivocation detection, quorum counting |
| `src/executor.py` | Deterministic block execution (P1 atomicity, P2 determinism) |
| `src/ledger.py` | Append-only finalized chain, atomic snapshot persist, crash recovery |
| `src/scheduler.py` | Priority queue `(logical_time, insertion_seq)`, seeded PRNG |
| `src/network.py` | Deterministic network simulator, bandwidth limiting, event logging |
| `src/fault_injector.py` | Drop/delay/duplicate/reorder từ seeded PRNG |
| `src/router.py` | Message validation và dispatch, rejects với stable error codes |
| `src/gossip.py` | Gossip finalized blocks và votes tới peers sau finalization |
| `src/consensus.py` | Tendermint-inspired consensus: prevote, lock, precommit, finalize |
| `src/scenario.py` | ScenarioRunner: điều phối simulation, safety/liveness assertions |
| `src/scenario_runner.py` | Legacy entry point tương thích với no-op scenario |
| `src/summary.py` | Compact run summary: per-node hash, state hash, rejection counts |

---

## Cấu hình

### `config/default.json`

```json
{
  "chain_id": "lab01-testnet",
  "spec_version": "0.1",
  "block_capacity": 10,
  "timeout_schedule": {
    "proposal_timeout": 10,
    "prevote_timeout": 5,
    "precommit_timeout": 5,
    "round_timeout_delta": 2
  },
  "network": {
    "max_block_size_bytes": 65536,
    "max_key_size_bytes": 256,
    "max_value_size_bytes": 4096,
    "bandwidth_limit_bytes_per_tick": 1048576
  }
}
```

### Các kịch bản (T1–T8)

| File | Kịch bản | Mô tả |
|---|---|---|
| `scenario_noop.json` | No-op baseline | max_height=0, dùng để verify determinism |
| `scenario_t1.json` | T1 — Normal run | 8 nodes, no faults, max_height=3 |
| `scenario_t2.json` | T2 — Dup + reorder | duplicate_probability=0.2, reorder_probability=0.2 |
| `scenario_t3.json` | T3 — Bad signature | inject bad signatures và wrong domains |
| `scenario_t4.json` | T4 — Replay TX | replay transaction đã finalized |
| `scenario_t5.json` | T5 — Drop/delay | drop_probability=0.1, delay_probability=0.4 |
| `scenario_t6.json` | T6 — Proposer crash | validator_1 (round-0 proposer) crashes |
| `scenario_t7.json` | T7 — Equivocation | 2 Byzantine validators equivocate |
| `scenario_t8.json` | T8 — Determinism | cùng seed → byte-identical logs |

---

## Ma trận kiểm thử T1–T8

| ID | Kịch bản | Tính chất kiểm tra | Trạng thái |
|---|---|---|---|
| **T1** | Chạy bình thường, không lỗi | Safety + Liveness: mọi node finalize cùng height/hash/state_hash | ✅ PASS |
| **T2** | Thông điệp trùng lặp và sắp xếp lại | Vote count đúng dù duplicate; không finalize xung đột | ✅ PASS |
| **T3** | Chữ ký không hợp lệ / domain sai | Router từ chối và ghi log; không state transition | ✅ PASS |
| **T4** | Replay / giao dịch trùng lặp | tx_id chỉ được apply tối đa một lần trong toàn bộ history | ✅ PASS |
| **T5** | Drop/delay trước synchrony | Safety bất biến xuyên suốt; liveness sau GST | ✅ PASS |
| **T6** | Proposer im lặng / crash | Proposal timeout → round change → proposer đúng finalize | ✅ PASS |
| **T7** | f=2 validators equivocating | Equivocation logged; honest nodes không finalize xung đột | ✅ PASS |
| **T8** | Cùng seed, hai lần chạy | Log chuẩn thô và state hash cuối byte-identical | ✅ PASS |

---

## Nguyên tắc thiết kế

**Tất định (Determinism)**
Mọi quyết định giả ngẫu nhiên xuất phát từ một seed duy nhất của kịch bản. Thời gian thực không tham gia vào dữ liệu giao thức hay log. Cùng seed và cấu hình luôn tạo ra kết quả byte-identical.

**An toàn (Safety)**
Không có hai block finalize khác nhau tại cùng một chiều cao giữa các node đúng đắn. Quorum yêu cầu `2f+1` trong tổng số `n = 3f+1` validator.

**Hoạt động (Liveness)**
Sau điểm ổn định mạng và khi chọn được proposer đúng đắn, chuỗi tiếp tục tiến triển. Round transition và timeout đảm bảo hệ thống không bị kẹt vĩnh viễn.

**Domain separation**
Mỗi loại thông điệp được ký có domain string riêng (`TX:<chain_id>`, `HEADER:<chain_id>`, `VOTE:<chain_id>`). Signature ở một context không thể bị reuse ở context khác.

---

## Cấu trúc thư mục

```
blockchain/
├── src/
│   ├── block.py             # BlockHeader, tx_root, body validation
│   ├── block_store.py       # Header-first block storage
│   ├── block_validator.py   # Header validation guards
│   ├── consensus.py         # Tendermint consensus engine
│   ├── crypto.py            # SHA-256, Ed25519 với domain separation
│   ├── encoding.py          # Canonical byte encoding
│   ├── event_log.py         # JSONL event logger, 18 event types
│   ├── executor.py          # Deterministic state executor
│   ├── fault_injector.py    # Drop/delay/duplicate/reorder injection
│   ├── gossip.py            # Gossip service sau finalization
│   ├── identity.py          # 8 validator keypairs
│   ├── ledger.py            # Finalized chain + atomic persistence
│   ├── network.py           # Deterministic network simulator
│   ├── router.py            # Message validation + dispatch
│   ├── scenario.py          # ScenarioRunner: safety/liveness assertions
│   ├── scenario_runner.py   # Legacy entry point (no-op compatible)
│   ├── scheduler.py         # Priority queue + seeded PRNG
│   ├── state.py             # Key-value state với canonical ordering
│   ├── summary.py           # Compact run summary export
│   ├── transaction.py       # Transaction model + validation
│   ├── vote.py              # Vote object + acceptance guards
│   └── vote_set.py          # Vote aggregation + quorum counting
│
├── tests/
│   ├── test_block.py            # Unit: block header, tx_root, body
│   ├── test_block_store.py      # Unit: header-first storage rule
│   ├── test_consensus.py        # Unit: consensus state machine
│   ├── test_crash_restart.py    # Unit: crash/restart simulation
│   ├── test_crypto.py           # Unit: SHA-256, Ed25519
│   ├── test_encoding.py         # Unit: canonical encoding
│   ├── test_event_log.py        # Unit: JSONL logger
│   ├── test_executor.py         # Unit: deterministic executor
│   ├── test_fault_injector.py   # Unit: fault injection
│   ├── test_gossip.py           # Unit: gossip service
│   ├── test_identity.py         # Unit: validator key loading
│   ├── test_ledger.py           # Unit: append-only ledger
│   ├── test_network.py          # Unit: network simulator
│   ├── test_noop.py             # Integration: no-op scenario
│   ├── test_router.py           # Unit: message router
│   ├── test_scenario.py         # Unit: scenario runner
│   ├── test_scheduler.py        # Unit: priority queue
│   ├── test_summary.py          # Unit: summary export
│   ├── test_t1.py               # E2E: T1 normal run
│   ├── test_t2.py               # E2E: T2 duplicate + reorder
│   ├── test_t3.py               # E2E: T3 bad signature
│   ├── test_t4.py               # E2E: T4 replay tx
│   ├── test_t5.py               # E2E: T5 drop/delay
│   ├── test_t6.py               # E2E: T6 proposer crash
│   ├── test_t7.py               # E2E: T7 equivocation
│   ├── test_t8.py               # E2E: T8 determinism
│   ├── test_transaction.py      # Unit: transaction validation
│   ├── test_vote.py             # Unit: vote object
│   ├── test_vote_set.py         # Unit: vote aggregation
│   └── verify_determinism.py    # Script: verify byte-identical replay
│
├── config/
│   ├── default.json         # Protocol parameters (chain_id, timeouts, limits)
│   ├── validator_keys.json  # 8 cặp khóa Ed25519 deterministic
│   ├── scenario_noop.json   # Baseline no-op scenario
│   ├── scenario_t1.json     # T1: normal run
│   ├── scenario_t2.json     # T2: duplicate + reorder
│   ├── scenario_t3.json     # T3: bad signature
│   ├── scenario_t4.json     # T4: replay tx
│   ├── scenario_t5.json     # T5: drop/delay
│   ├── scenario_t6.json     # T6: proposer crash
│   ├── scenario_t7.json     # T7: equivocation
│   └── scenario_t8.json     # T8: determinism
│
├── docs/
│   ├── ARCHITECTURE.md          # Module boundaries, message flow
│   ├── PROTOCOL_SPEC.md         # Canonical encoding, consensus rules
│   ├── REQUIREMENTS.md          # Acceptance criteria
│   ├── TEST_SPEC.md             # Log schema, test evidence spec
│   ├── IMPLEMENTATION_PLAN.md   # Milestones and DoD
│   └── requirement/             # Vietnamese requirement documents
│
├── requirements.txt         # Python dependencies
├── pytest.ini               # pytest configuration and markers
└── README.md                # This file
```

---

## Tài liệu tham khảo

| File | Nội dung |
|---|---|
| `docs/REQUIREMENTS.md` | Yêu cầu và phạm vi, tiêu chí chấp nhận |
| `docs/PROTOCOL_SPEC.md` | Dữ liệu chuẩn, mật mã, quy tắc đồng thuận |
| `docs/ARCHITECTURE.md` | Ranh giới module, luồng thông điệp |
| `docs/TEST_SPEC.md` | Schema log, bằng chứng kiểm thử |
| `docs/IMPLEMENTATION_PLAN.md` | Các mốc tiến độ |
