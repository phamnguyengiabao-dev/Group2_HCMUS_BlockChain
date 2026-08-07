# Báo Cáo Lab 01 — Blockchain Layer-1 Simulator

**Nhóm:** Blockchain Lab01  
**Ngày:** 2026-08-07  
**Phiên bản đặc tả:** 0.1

---

## 1. Tổng Quan Dự Án

Dự án xây dựng một blockchain Layer-1 tối giản dưới dạng simulator, trong đó các validator đúng đắn hội tụ về một chuỗi block đã finalize dù thông điệp bị trễ, trùng lặp, sắp xếp lại hoặc bị rớt tạm thời.

### Thông số kỹ thuật

| Tham số | Giá trị |
|---|---|
| Ngôn ngữ | Python 3.10+ |
| Số validator | 8 (`n = 3f+1`, `f = 2`) |
| Quorum | 5 (`2f+1 = 5`) |
| Đồng thuận | Tendermint-inspired PREVOTE/PRECOMMIT |
| Mật mã | Ed25519 + SHA-256 với domain separation |
| Trạng thái | Key-value map xác định |
| Mạng | Simulated P2P với fault injection |

---

## 2. Kiến Trúc Hệ Thống

Hệ thống được tổ chức thành 3 tầng phụ thuộc rõ ràng:

```
TẦNG CAO (điều phối)
  scenario.py — ScenarioRunner
  consensus.py — Consensus engine

TẦNG GIỮA (giao thức & dữ liệu)
  block.py / block_store.py / ledger.py
  vote.py / vote_set.py
  network.py / router.py / gossip.py

TẦNG NỀN (không phụ thuộc gì phía trên)
  crypto.py / encoding.py / state.py
```

### Các quyết định thiết kế quan trọng

1. **Canonical encoding**: Mọi giá trị được hash hoặc ký đều qua bộ encoder xác định. Không dùng JSON thô hoặc Python dict iteration.
2. **Domain separation**: `TX:<chain_id>`, `HEADER:<chain_id>`, `VOTE:<chain_id>` — signature của loại thông điệp này không thể dùng cho loại khác.
3. **Deterministic scheduler**: Priority queue `(logical_time, insertion_seq)` với seeded PRNG. Thời gian thực không tham gia vào bất kỳ quyết định nào.
4. **Header-first rule**: Body chỉ được xử lý sau khi header hợp lệ đã được nhận và lưu.
5. **Atomic persistence**: Ledger snapshot được ghi nguyên tử với `os.replace()` để đảm bảo crash safety.

---

## 3. Kết Quả Kiểm Thử T1–T8

### T1 — Chạy Bình Thường (Normal Run)

**Cấu hình:** 8 validators, no faults, max_height=3  
**Kết quả:** ✅ PASS

- Tất cả 8 node finalize cùng height/hash/state_hash tại mỗi chiều cao.
- Safety: không có xung đột.
- Liveness: đạt max_height=3.

```
test_t1_normal_run_safety_and_liveness              PASS
test_t1_normal_run_all_nodes_finalize_same_*        PASS
```

### T2 — Thông Điệp Trùng Lặp và Sắp Xếp Lại

**Cấu hình:** duplicate_probability=0.2, reorder_probability=0.2, max_height=2  
**Kết quả:** ✅ PASS

- Vote trùng lặp bị bỏ qua (DUPLICATE_IGNORED); không tăng quorum count.
- Tổng distinct voters = đúng 8 mọi node mọi height.
- Safety không bị phá vỡ.

```
test_t2_faults_actually_injected_duplicates_and_reorders  PASS
test_t2_vote_count_correct_despite_duplicates             PASS
test_t2_no_conflicting_finalization                       PASS
```

### T3 — Chữ Ký Không Hợp Lệ / Domain Sai

**Cấu hình:** inject bad signatures và wrong domains  
**Kết quả:** ✅ PASS

- Router từ chối tất cả thông điệp có signature sai với mã lỗi `INVALID_SIGNATURE`.
- Router từ chối thông điệp dùng domain sai với mã lỗi `INVALID_SIGNATURE`.
- Không có state transition sau khi reject.
- Tất cả rejects được ghi vào canonical event log với `event_type: REJECT`.

```
test_router_rejects_header_bad_signature    PASS
test_router_rejects_header_wrong_domain     PASS
test_router_rejects_vote_bad_signature      PASS
test_router_rejects_vote_wrong_domain       PASS
test_t3_rejected_messages_never_mutate_*    PASS
test_t3_scenario_run_rejects_every_*        PASS
```

### T4 — Replay / Giao Dịch Trùng Lặp

**Cấu hình:** 1 transaction, replay_transactions=true  
**Kết quả:** ✅ PASS

**Case 1 — Cùng tx_id trong cùng block:**
- Executor phát hiện DUPLICATE_TX_ID, từ chối toàn bộ block.
- Ledger không thay đổi.

**Case 2 — Replay ở height sau:**
- Sender nonce đã tăng từ height trước → replay bị từ chối với INVALID_NONCE.
- State chỉ phản ánh đúng một lần apply.

```
test_t4_duplicate_tx_in_same_block_rejected_*    PASS
test_t4_replay_at_later_height_rejected_*        PASS
test_t4_state_reflects_exactly_one_application  PASS
test_t4_scenario_assertions_hold_*               PASS
```

### T5 — Drop/Delay Trước Synchrony

**Cấu hình:** drop_probability=0.1, delay_probability=0.4, stabilization_time=20  
**Kết quả:** ✅ PASS

- Pre-synchrony: mọi node nhận < 5 vote (dưới quorum), không node nào finalize.
- Round change xảy ra sau khi quorum timeout tại round 0.
- Post-synchrony (round 1): proposer mới, fault-free → tất cả node finalize cùng block.
- Safety bất biến xuyên suốt cả hai giai đoạn.

```
test_t5_drop_delay_preserves_safety_then_*    PASS
```

Bằng chứng event log:
```json
{"event_type": "DROP", ...}
{"event_type": "DELAY", ...}
{"event_type": "ROUND_CHANGE", "details": {"from_round": 0, "to_round": 1}}
{"event_type": "FINALIZE", "round": 1, ...}
```

### T6 — Proposer Im Lặng / Crash

**Cấu hình:** validator_1 crash tại height=1, round=0, proposal_timeout=10  
**Kết quả:** ✅ PASS

- validator_1 là round-0 proposer của height 1.
- 7 honest validators schedule proposal timeout và prevote NIL khi timeout fires.
- Round change từ 0 → 1, validator mới (validator_2) được chọn làm proposer.
- validator_2 propose thành công, 7 honest validators đạt quorum và finalize.
- validator_1 (crashed) không có entry trong ledger.

```
test_t6_silent_proposer_times_out_round_changes_*    PASS
```

Bằng chứng:
- 1 sự kiện CRASH
- 7 sự kiện TIMEOUT
- 7 sự kiện ROUND_CHANGE

### T7 — Tối Đa f=2 Validators Equivocating

**Cấu hình:** byzantine_nodes=[validator_0, validator_1], f=2  
**Kết quả:** ✅ PASS

- 2 Byzantine validators gửi conflicting votes cho cả PREVOTE và PRECOMMIT.
- VoteSet giữ lại vote đầu tiên, vote thứ hai gây equivocation evidence.
- Candidate A (empty block) đạt quorum với 8 phiếu.
- Candidate B (block có transaction) không đạt quorum (chỉ 2 phiếu).
- Tất cả honest nodes finalize candidate A.
- Tổng equivocation events: `2 phases × 2 byzantine × 6 honest receivers = 24`.

```
test_t7_f_equivocators_are_logged_and_*    PASS
```

### T8 — Tính Tất Định (Determinism)

**Cấu hình:** seed=8888, delay_probability=0.35, duplicate_probability=0.25, reorder_probability=0.25  
**Kết quả:** ✅ PASS

- Cùng seed → cùng thứ tự PRNG → cùng fault decisions.
- Hai lần chạy độc lập tạo ra log JSONL byte-identical.
- SHA-256 của log file giống nhau.
- Final state_hash tại mỗi node giống nhau trên cả hai lần chạy.
- Fault trace xác nhận: delayed > 0, duplicated > 0, reordered > 0.

```
test_t8_same_seed_has_byte_identical_log_and_state_hash    PASS
```

---

## 4. Tóm Tắt Test Suite

| Loại | Số tests | Kết quả |
|---|---|---|
| Unit tests (crypto, encoding, state, ...) | ~220 | ✅ All PASS |
| Integration tests (noop, scenario, ...) | ~50 | ✅ All PASS |
| End-to-end T1–T8 | ~50 | ✅ All PASS |
| **Tổng** | **421** | **✅ 421 PASS** |

**Code coverage:** ~90% trên toàn bộ `src/`

---

## 5. Phân Tích Safety và Liveness

### Safety

**Bất biến:** Không có hai block finalize khác nhau tại cùng một chiều cao giữa các node đúng đắn.

Được đảm bảo bởi:
1. **Quorum yêu cầu `2f+1`**: Với `f=2`, cần ít nhất 5/8 validators. Hai quorum chồng nhau phải có ít nhất `2(2f+1) - n = 2×5 - 8 = 2` validators chung → không thể tồn tại hai quorum precommit cho hai block khác nhau cùng lúc.
2. **Locking**: Validator locked vào block `B` ở round `r` chỉ prevote block khác nếu có bằng chứng quorum prevote ở round sau — đảm bảo không "vote ngược lại" lock hiện tại.
3. **VoteSet deduplication**: Vote trùng không tăng quorum; equivocation bị detect và không thay thế vote đầu.

### Liveness

**Bất biến:** Sau điểm ổn định mạng và khi chọn được proposer đúng đắn, một chiều cao sau đó phải được finalize.

Được đảm bảo bởi:
1. **Round timeout và round change**: Khi proposer im lặng hoặc quorum không đạt được, timeout triggers round change.
2. **Proposer rotation**: `proposer = validator_set[(height + round) % n]` — mỗi round chọn proposer khác, đảm bảo cuối cùng một proposer đúng đắn được chọn.
3. **Lock carryover**: Lock được giữ nguyên qua round change → nếu block `B` đã đạt quorum prevote ở round `r`, nó vẫn sẽ được finalize ở round sau.

---

## 6. Tính Tất Định (Determinism)

Toàn bộ simulation là deterministic dựa trên:

1. **Seeded PRNG**: `random.Random(seed)` được tạo một lần và tất cả fault decisions đều dùng instance này.
2. **Canonical iteration**: Mọi vòng lặp qua validators, peers, messages đều dùng `sorted()` — không bao giờ theo thứ tự Python dict/set.
3. **Logical time**: Không có wall-clock time trong bất kỳ decision nào.
4. **Priority queue**: Thứ tự giao packet là `(logical_time, insertion_seq)` — tie-breaking hoàn toàn xác định.
5. **Canonical encoding**: Tất cả serialization qua encoder xác định, không dùng `json.dumps()` với thứ tự key không đảm bảo.

**Bằng chứng**: `tests/verify_determinism.py` chạy noop scenario hai lần với cùng seed và xác nhận SHA-256 log file byte-identical. `test_t8.py` xác nhận với scenario phức tạp có delay/duplicate/reorder.

---

## 7. Kết Luận

Dự án đã hoàn thành đầy đủ các yêu cầu của Lab 01:

- ✅ **421 tests** tất cả pass, bao gồm T1–T8 end-to-end
- ✅ **Safety**: Không có conflicting finalization trong bất kỳ kịch bản nào
- ✅ **Liveness**: Chuỗi tiến triển sau synchrony, ngay cả với proposer crash
- ✅ **Validity**: Invalid messages bị reject với stable error codes
- ✅ **Vote counting**: Duplicate/equivocation được handle đúng
- ✅ **Determinism**: Cùng seed → byte-identical logs và state hashes
- ✅ **Code coverage**: ~90% trên `src/`
- ✅ **Canonical event log**: 18 event types, JSONL, monotonic event_no

---

*Tài liệu này được tổng hợp từ kết quả chạy thực tế của test suite. Log files được lưu tại `logs/<scenario_id>/`.*
