"""
update_xlsx.py — Rebuild Gantt Chart rows 21+ cho Blockchain Lab01
Timeline: 21/07/2026 - 07/08/2026

Công thức đúng theo spec:
    Trọng số (P) = Độ ưu tiên (I) × Độ khó (J) × Số ngày (M)
    Điểm đóng góp (Q) = P × Mức độ hoàn thành (O)
"""
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from datetime import date

XLSX_PATH = r'd:\Coding\blockchain\docs\BlockChain Team Management.xlsx'

# ── Timeline ─────────────────────────────────────────────────────────────────
# G0 đã hoàn thành (trước ngày bắt đầu chính thức)
# G1: 22/07 – 25/07 (4 ngày)
# G2: 25/07 – 29/07 (4 ngày)
# G3: 29/07 – 02/08 (4 ngày)
# G4: 02/08 – 05/08 (3 ngày)
# G5: 05/08 – 07/08 (2 ngày)
PHASE_DATES = {
    'G0': (date(2026, 7, 21), date(2026, 7, 21)),
    'G1': (date(2026, 7, 22), date(2026, 7, 25)),
    'G2': (date(2026, 7, 25), date(2026, 7, 29)),
    'G3': (date(2026, 7, 29), date(2026, 8,  2)),
    'G4': (date(2026, 8,  2), date(2026, 8,  5)),
    'G5': (date(2026, 8,  5), date(2026, 8,  7)),
}

# ── Màu nền ───────────────────────────────────────────────────────────────────
FILL = {
    'G0_section': 'BDD7EE', 'G0': 'DEEAF1',
    'G1_section': 'E2EFDA', 'G1': 'EBF5E1',
    'G2_section': 'FFF2CC', 'G2': 'FFFAE6',
    'G3_section': 'FCE4D6', 'G3': 'FDEEDE',
    'G4_section': 'EDEDED', 'G4': 'F5F5F5',
    'G5_section': 'D9D2E9', 'G5': 'EDE8F4',
    'done':    'C6EFCE',
    'partial': 'FFEB9C',
}

def cell_fill(hex_color):
    return PatternFill(fill_type='solid', start_color=hex_color, end_color=hex_color)

def thin_border():
    s = Side(style='thin', color='BFBFBF')
    return Border(left=s, right=s, top=s, bottom=s)

def style_row(ws, r, fill_hex, bold=False, color='000000'):
    b = thin_border()
    for col in range(2, 18):
        c = ws.cell(r, col)
        c.fill = cell_fill(fill_hex)
        c.border = b
        c.font = Font(bold=bold, color=color, size=10)
        c.alignment = Alignment(wrap_text=True, vertical='top')

# ── Task data ─────────────────────────────────────────────────────────────────
# (id, title, detail, checklist, note, person, priority, difficulty, days, result, completion, phase)
# days = số ngày thực hiện theo spec (lưu trực tiếp vào cột M)
# completion: 0.0–1.0

TASKS = [
  # ═══ GIAI ĐOẠN 0 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 0 — Repository Scaffold ✅','','','','',0,0,0,'','','G0'),

  ('T0-01','Tạo cấu trúc thư mục',
   'Tạo src/, tests/, logs/, config/ + __init__.py',
   'src/ tồn tại: 20%\ntests/ tồn tại: 20%\nlogs/ tồn tại: 20%\nconfig/ tồn tại: 20%\n__init__.py đúng vị trí: 20%',
   '','Bảo',9,3,1,'Cấu trúc thư mục hoàn chỉnh',1.0,'G0'),

  ('T0-02','Viết README.md',
   'README.md với hướng dẫn cài đặt và lệnh test',
   'Hướng dẫn cài đặt: 34%\nLệnh chạy test: 33%\nMô tả dự án: 33%',
   '','Bảo',8,2,1,'README.md hoàn chỉnh',1.0,'G0'),

  ('T0-03','Tạo config/default.json',
   'block_capacity, timeouts, retention, limits',
   'block_capacity: 25%\ntimeout_schedule: 25%\nretention_policy: 25%\nnetwork limits: 25%',
   '','Bảo',8,2,1,'config/default.json đầy đủ',1.0,'G0'),

  ('T0-04','Tạo validator_keys.json',
   '8 cặp khóa Ed25519 cố định (seed-based HKDF)',
   '8 cặp key: 50%\nSeed cố định: 50%',
   '','Bảo',8,4,1,'8 cặp key đã tạo',1.0,'G0'),

  ('T0-05','Tạo scenario files',
   'scenario_noop.json, scenario_t1.json, scenario_t8.json',
   'scenario_noop.json: 34%\nscenario_t1.json: 33%\nscenario_t8.json: 33%',
   '','Bảo',7,2,1,'3 scenario files hoàn chỉnh',1.0,'G0'),

  ('T0-06','Entry point test + no-op scenario',
   'tests/test_noop.py + verify_determinism.py + src/event_log.py + src/scenario_runner.py',
   'test_creates_log pass: 25%\ntest_valid_jsonl pass: 25%\ntest_monotonic pass: 25%\nverify_determinism PASS: 25%',
   'event_log.py và scenario_runner.py implement đầy đủ trong G0',
   'Bảo',9,6,1,'Tất cả tests pass, determinism xác nhận',1.0,'G0'),

  # ═══ GIAI ĐOẠN 1 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 1 — Primitive Xác Định','','','','',0,0,0,'','','G1'),

  ('T1-01','encode_uint64 / encode_bool / encode_bytes / encode_str',
   'src/encoding.py — uint64 big-endian 8 bytes, bool 1 byte, bytes với u32 prefix, str NFC+UTF-8',
   'encode_uint64 big-endian: 25%\nencode_bool 0x01/0x00: 25%\nencode_bytes u32 prefix: 25%\nencode_str NFC+UTF-8: 25%',
   'Done — commit 8d5f3e3','Khánh',9,5,1,
   'Implemented & merged (commit 8d5f3e3)',1.0,'G1'),

  ('T1-02','encode_optional_hash',
   'src/encoding.py — presence byte + 32-byte hash; ValueError nếu sai size',
   'b"\\x00" khi None: 34%\nb"\\x01"+32 bytes: 33%\nValueError nếu != 32 bytes: 33%',
   'Done — commit 8d5f3e3','Khánh',8,4,1,
   'Implemented & merged (commit 8d5f3e3)',1.0,'G1'),

  ('T1-03','encode_sorted_map — sorted map encoder',
   'src/encoding.py — sort theo UTF-8 key bytes; format: u64 count || encode_bytes(key) || encode_bytes(value)',
   'Sort UTF-8 key bytes: 34%\nPrefix u64 count: 33%\nNFC-normalize key: 33%',
   'Gốc phân cho Huy; Khánh thực hiện gộp trong commit T1-01/02',
   'Khánh',8,5,1,'Implemented & merged (commit 8d5f3e3, Khánh thực hiện)',1.0,'G1'),

  ('T1-04','Unit test encoding — 5 hàm',
   'tests/test_encoding.py — test encode_uint64, encode_bool, encode_bytes, encode_str, encode_optional_hash, encode_sorted_map',
   'Test encode_sorted_map (3 cases): 40%\nTest encode_uint64: 15%\nTest encode_bool: 15%\nTest encode_bytes: 15%\nTest encode_optional_hash: 15%',
   '47 tests pass — tất cả 5 hàm + encode_sorted_map',
   'Huy',9,4,1,'47 tests pass',1.0,'G1'),

  ('T1-05','hash_bytes — SHA-256 wrapper',
   'src/crypto.py — hash_bytes(data) -> bytes, 32 bytes',
   'Import SHA-256: 50%\nTrả đúng 32 bytes: 50%',
   '8 tests pass','Khánh',9,3,1,'Implemented — 8 tests pass',1.0,'G1'),

  ('T1-06','Ed25519 sign() với domain separation',
   'src/crypto.py — sign(privkey, domain, payload): ký utf8(domain) || 0x00 || payload',
   'Concat domain+0x00+payload: 50%\nEd25519 sign đúng: 50%',
   'Tests pass','Khôi',9,6,1,'Implemented — tests pass',1.0,'G1'),

  ('T1-07','Ed25519 verify() với domain separation',
   'src/crypto.py — verify(domain, pubkey, payload, sig): rebuild message rồi verify',
   'Rebuild message đúng: 50%\nVerify signature đúng: 50%',
   'Tests pass','Khôi',9,6,1,'Implemented — tests pass',1.0,'G1'),

  ('T1-08','Unit test crypto',
   'tests/test_crypto.py — sai domain/key/payload → fail; đúng → pass',
   'Sai domain fail: 25%\nSai key fail: 25%\nSai payload fail: 25%\nĐúng pass: 25%',
   '14 tests pass','Hiếu',9,5,1,'14 tests pass',1.0,'G1'),

  ('T1-09','Load và validate identity fixtures',
   'src/identity.py — load validator_keys.json, trả về sorted validator list',
   'Load file: 34%\nValidate format: 33%\nSorted list: 33%',
   '10 tests pass','Bảo',7,3,1,'10 tests pass',1.0,'G1'),

  ('T1-10','Sorted key-value state map',
   'src/state.py — insert/get/delete; dùng sorted dict đảm bảo thứ tự',
   'insert() sorted order: 34%\nget() đúng: 33%\ndelete() đúng: 33%',
   'src/state.py đầy đủ','Huy',8,5,2,'src/state.py đầy đủ — Done',1.0,'G1'),

  ('T1-11','State commitment hash',
   'src/state.py — SHA256(encode(entry_count) || sorted key-value pairs)',
   'encode entry_count: 34%\nIterate sorted keys: 33%\nSHA256 32 bytes: 33%',
   'state_hash() implemented','Huy',8,6,1,'state_hash() implemented — Done',1.0,'G1'),

  ('T1-12','Transaction object + validation',
   'src/transaction.py — chain_id, nonce, namespace prefix, size limits, signature',
   'chain_id: 20%\nnonce: 20%\nnamespace prefix: 20%\nsize limits: 20%\nsignature: 20%',
   '8 tests pass','Khánh',9,7,2,'8 tests pass',1.0,'G1'),

  ('T1-13','Deterministic executor',
   'src/executor.py — apply tx list → post-state + nonces; invalid tx → invalidate block',
   'Apply ordered: 34%\nUpdate nonces: 33%\nInvalid tx → invalidate block: 33%',
   '22 tests pass (P1 atomicity, P2 determinism, P3 no-double-apply, P4 order)',
   'Khôi',9,8,2,'22 tests pass',1.0,'G1'),

  ('T1-14','Unit test determinism executor',
   'tests/test_executor.py — cùng block 2 lần → byte/hash giống nhau',
   'Same post-state hash: 50%\nSame nonces: 50%',
   '22 tests pass','Hiếu',9,5,1,'22 tests pass',1.0,'G1'),

  ('T1-15','Unit test transaction rejection',
   'tests/test_transaction.py — namespace/nonce/dup/size sai → reject',
   'Namespace sai reject: 25%\nNonce sai reject: 25%\nDup tx reject: 25%\nSize vượt reject: 25%',
   '8 tests pass','Bảo',9,5,1,'8 tests pass',1.0,'G1'),

  # ═══ GIAI ĐOẠN 2 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 2 — Data Model và Xác Thực','','','','',0,0,0,'','','G2'),

  ('T2-01','Block Header object',
   'src/block.py — fields đúng thứ tự spec; block_hash = SHA256(canonical signed header)',
   'Fields đúng thứ tự: 50%\nblock_hash = SHA256: 50%',
   '','Khánh',9,7,2,'',0.0,'G2'),

  ('T2-02','tx_root computation',
   'src/block.py — SHA256(encode(count) || tx_id[0] || ...); rỗng = hash(count=0)',
   'Tính đúng khi có txs: 50%\nBlock rỗng hash(count=0): 50%',
   '','Huy',8,5,1,'',0.0,'G2'),

  ('T2-03','Header validation guards (F-26)',
   'src/block_validator.py — chain_id, height, round, parent_hash, proposer, HEADER domain sig',
   'chain_id: 17%\nheight: 17%\nround: 16%\nparent_hash: 17%\nproposer: 17%\nHEADER sig: 16%',
   '','Khôi',9,7,2,'',0.0,'G2'),

  ('T2-04','Block Body + candidate validation (F-27–F-29)',
   'src/block.py — tx_root khớp, all txs valid, post-state hash khớp',
   'tx_root khớp: 34%\nAll txs valid: 33%\npost-state hash: 33%',
   '','Khôi',9,7,2,'',0.0,'G2'),

  ('T2-05','Unit test block validation',
   'tests/test_block.py — parent/proposer/height/tx_root/state_hash/sig sai → bắt được',
   'parent_hash sai: 17%\nproposer sai: 17%\nheight sai: 17%\ntx_root sai: 17%\nstate_hash sai: 16%\nsig sai: 16%',
   '','Hiếu',9,6,1,'',0.0,'G2'),

  ('T2-06','Vote object + validation guards (F-40)',
   'src/vote.py — chain_id, member check, VOTE domain sig, height/round/phase',
   'chain_id: 25%\nmember check: 25%\nVOTE domain sig: 25%\nheight/round/phase: 25%',
   '','Huy',8,6,1,'',0.0,'G2'),

  ('T2-07','VoteSet storage',
   'src/vote_set.py — key (height, round, phase, validator_pubkey)',
   'Key 4 thành phần: 50%\nStore/retrieve đúng: 50%',
   '','Khánh',8,6,1,'',0.0,'G2'),

  ('T2-08','Duplicate + equivocation detection',
   'src/vote_set.py — duplicate bỏ qua; equivocation log + giữ vote đầu',
   'Duplicate bỏ qua: 50%\nEquivocation log + giữ vote đầu: 50%',
   '','Khôi',8,7,1,'',0.0,'G2'),

  ('T2-09','Quorum counting has_quorum()',
   'src/vote_set.py — True khi >= 2f+1 validators riêng biệt',
   'Đếm distinct validators: 50%\nNgưỡng 2f+1: 50%',
   '','Bảo',9,6,1,'',0.0,'G2'),

  ('T2-10','Unit test vote_set',
   'tests/test_vote_set.py — duplicate/non-member/equivocation/quorum',
   'Duplicate bỏ qua: 25%\nNon-member từ chối: 25%\nEquivocation log: 25%\nQuorum đúng: 25%',
   '','Hiếu',9,6,1,'',0.0,'G2'),

  ('T2-11','Block Store + header-first rule (F-30)',
   'src/block_store.py — store_header(), store_body(); body chỉ sau valid header',
   'store_header(): 34%\nstore_body(): 33%\nBody reject nếu chưa có header: 33%',
   '','Khôi',8,6,1,'',0.0,'G2'),

  ('T2-12','Ledger append-only + snapshot',
   'src/ledger.py — append-only finalized chain + state snapshot; không rollback',
   'Chỉ append: 50%\nState snapshot: 50%',
   '','Huy',8,7,1,'',0.0,'G2'),

  ('T2-13','Atomic persist (F-52)',
   'src/ledger.py — ghi nguyên tử height, hash, state, nonces, block',
   'All-or-nothing: 50%\nĐủ 5 trường: 50%',
   '','Hiếu',9,8,1,'',0.0,'G2'),

  ('T2-14','Crash recovery (F-53)',
   'src/ledger.py — load snapshot, discard unfinalized proposals/votes',
   'Load snapshot: 50%\nDiscard unfinalized: 50%',
   '','Khánh',9,8,1,'',0.0,'G2'),

  # ═══ GIAI ĐOẠN 3 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 3 — Mạng Xác Định','','','','',0,0,0,'','','G3'),

  ('T3-01','Canonical event schema (18 types)',
   'src/event_log.py — 18 event types với fixed field order',
   '18 types đủ: 50%\nField order cố định: 50%',
   '','Khánh',8,5,1,'',0.0,'G3'),

  ('T3-02','JSON Lines writer canonical',
   'src/event_log.py — fixed key order, no whitespace, UTF-8, newline mỗi event',
   'Fixed key order: 25%\nNo whitespace: 25%\nUTF-8: 25%\nNewline: 25%',
   '','Huy',8,5,1,'',0.0,'G3'),

  ('T3-03','event_no monotonic + logical_time',
   'src/event_log.py — event_no +1 mỗi event; logical_time chính xác',
   'event_no +1: 50%\nlogical_time chính xác: 50%',
   '','Huy',8,4,1,'',0.0,'G3'),

  ('T3-04','Envelope type',
   'src/network.py — (sender, receiver, payload, logical_time, insertion_seq)',
   'Đủ 5 trường: 50%\nSerialize đúng: 50%',
   '','Khánh',7,4,1,'',0.0,'G3'),

  ('T3-05','Deterministic scheduler',
   'src/scheduler.py — priority queue (logical_time, insertion_seq); tie-break insertion_seq',
   'Priority queue đúng: 50%\nTie-break insertion_seq: 50%',
   '','Hiếu',9,7,2,'',0.0,'G3'),

  ('T3-06','Seeded PRNG',
   'src/scheduler.py — Random(seed) riêng; không dùng random.random() global',
   'Random(seed) riêng: 50%\nKhông global random: 50%',
   '','Khôi',9,6,1,'',0.0,'G3'),

  ('T3-07','Fault injector',
   'src/fault_injector.py — drop/delay/duplicate/reorder từ config; dùng PRNG T3-06',
   'drop: 25%\ndelay: 25%\nduplicate: 25%\nreorder: 25%',
   '','Khánh',8,7,2,'',0.0,'G3'),

  ('T3-08','Bandwidth + rate limiting',
   'src/network.py — bytes/tick không vượt bandwidth_limit_bytes_per_tick',
   'Đo bytes/tick: 50%\nDrop/queue nếu vượt: 50%',
   '','Hiếu',6,6,1,'',0.0,'G3'),

  ('T3-09','Peer blocking/unblocking',
   'src/network.py — block_peer() / unblock_peer(); log PEER_BLOCK/PEER_UNBLOCK',
   'block_peer + log: 50%\nunblock_peer + log: 50%',
   '','Bảo',6,5,1,'',0.0,'G3'),

  ('T3-10','Canonical iteration order audit',
   'Toàn bộ src/ — sửa mọi dict/set iteration → dùng sorted()',
   'No dict iteration: 50%\nNo set iteration: 50%',
   '','Huy',9,6,1,'',0.0,'G3'),

  ('T3-11','Message Router',
   'src/router.py — envelope shape, chain_id, sender identity, signature; chỉ tin sig',
   'Envelope shape: 25%\nchain_id: 25%\nSender identity: 25%\nSignature: 25%',
   '','Khôi',8,7,2,'',0.0,'G3'),

  ('T3-12','Router rejection logging',
   'src/router.py — REJECT event với rejection code cho từng guard',
   'REJECT event: 50%\nCode chính xác theo guard: 50%',
   '','Hiếu',7,5,1,'',0.0,'G3'),

  ('T3-13','Router drop invalid objects',
   'src/router.py — drop hoàn toàn sau log; không relay invalid',
   'Không relay invalid: 50%\nLog trước drop: 50%',
   '','Khôi',8,4,1,'',0.0,'G3'),

  ('T3-14','Scenario Runner chính',
   'src/scenario.py — load config → init nodes → seed PRNG → sim loop → shutdown',
   'Load config: 20%\nInit nodes: 20%\nSeed PRNG: 20%\nSim loop: 20%\nShutdown: 20%',
   '','Khánh',9,8,3,'',0.0,'G3'),

  ('T3-15','Ghi spec_version + config_fingerprint',
   'src/scenario.py — spec_version và SHA256(sorted JSON config) vào đầu log',
   'spec_version: 50%\nconfig_fingerprint SHA256: 50%',
   '','Hiếu',7,4,1,'',0.0,'G3'),

  ('T3-16','Assertion engine safety + liveness',
   'src/scenario.py — safety: không 2 hash cùng height; liveness: height tăng',
   'Safety assert: 50%\nLiveness assert: 50%',
   '','Khôi',9,7,2,'',0.0,'G3'),

  # ═══ GIAI ĐOẠN 4 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 4 — Consensus Engine','','','','',0,0,0,'','','G4'),

  ('T4-01','ConsensusState per height',
   'src/consensus.py — round, locked_block_hash, locked_round, valid_block_hash, prevotes, precommits',
   'Đủ 6 trường: 50%\nReset đúng khi height mới: 50%',
   '','Hiếu',9,8,2,'',0.0,'G4'),

  ('T4-02','Proposer selection',
   'src/consensus.py — validator_set[sorted][(height+round) % n]',
   'Công thức (h+r)%n: 50%\nSorted validator set: 50%',
   '','Khánh',9,5,1,'',0.0,'G4'),

  ('T4-03','Proposal handler',
   'src/consensus.py — proposer: HEADER trước BODY; non-proposer: timeout → prevote NIL',
   'HEADER trước BODY: 50%\nTimeout → prevote NIL: 50%',
   '','Khôi',9,8,2,'',0.0,'G4'),

  ('T4-04','Prevote guard (F-35)',
   'src/consensus.py — unlocked/lock-match → prevote block; quorum later-round → prevote other; else NIL',
   'Unlocked prevote block: 34%\nLock-match prevote block: 33%\nQuorum later-round: 33%',
   'Logic phức tạp nhất','Hiếu',9,9,2,'',0.0,'G4'),

  ('T4-05','Lock logic (F-36)',
   'src/consensus.py — quorum prevote non-NIL → locked_block_hash, locked_round, valid_block_hash',
   'Detect quorum non-NIL: 34%\nlocked_block_hash: 33%\nlocked_round+valid_block: 33%',
   '','Khánh',9,8,1,'',0.0,'G4'),

  ('T4-06','Precommit logic (F-37)',
   'src/consensus.py — quorum prevote non-NIL → precommit block; NIL/timeout → precommit NIL',
   'Quorum non-NIL → precommit: 50%\nNIL/timeout → precommit NIL: 50%',
   '','Khôi',9,8,1,'',0.0,'G4'),

  ('T4-07','Finalization pipeline (F-38)',
   'src/consensus.py — quorum precommit → revalidate → append ledger → commit state → reset → height+1',
   'Detect quorum: 20%\nRevalidate: 20%\nAppend ledger: 20%\nCommit state: 20%\nReset+height+1: 20%',
   'Task quan trọng nhất G4','Huy',10,9,2,'',0.0,'G4'),

  ('T4-08','Round change (F-39)',
   'src/consensus.py — precommit timeout → round++ → reset vote sets → giữ locks',
   'Timeout trigger: 34%\nReset vote sets: 33%\nGiữ locks: 33%',
   '','Bảo',9,7,1,'',0.0,'G4'),

  ('T4-09','"Tối đa 1 vote" guard (F-33)',
   'src/consensus.py — enforce per (height, round, phase) — không ký 2 votes cùng phase',
   'Track (h,r,phase): 50%\nTừ chối lần 2: 50%',
   '','Khánh',9,5,1,'',0.0,'G4'),

  ('T4-10','Gossip Service',
   'src/gossip.py — sau finalize relay block+votes tới peers; log SEND',
   'Relay block: 50%\nLog SEND: 50%',
   '','Huy',8,7,2,'',0.0,'G4'),

  ('T4-11','Crash simulation',
   'src/scenario.py — dừng node tại logical_time, xóa cache, giữ snapshot; log CRASH',
   'Dừng đúng time: 34%\nXóa cache: 33%\nLog CRASH: 33%',
   '','Hiếu',8,6,1,'',0.0,'G4'),

  ('T4-12','Restart simulation',
   'src/scenario.py — load snapshot, rebuild từ gossip; log RESTART',
   'Load snapshot: 50%\nLog RESTART: 50%',
   '','Khôi',8,7,1,'',0.0,'G4'),

  # ═══ GIAI ĐOẠN 5 ════════════════════════════════════════════════════════════
  ('SECTION','GIAI ĐOẠN 5 — Test Suite & Nộp Bài','','','','',0,0,0,'','','G5'),

  ('T5-01','Scenario T1 — Normal run',
   'config/scenario_t1.json + tests/test_t1.py — 8 nodes, no fault, max_height=3',
   'scenario_t1.json: 34%\nAll nodes same height: 33%\nSame hash+state_hash: 33%',
   '','Khánh',9,5,1,'',0.0,'G5'),

  ('T5-02','Scenario T2 — Duplicate + reorder',
   'config/scenario_t2.json + tests/test_t2.py — inject dup+reorder; vote count đúng',
   'Inject dup: 34%\nVote count đúng: 33%\nKhông conflict: 33%',
   '','Khánh',9,6,1,'',0.0,'G5'),

  ('T5-03','Scenario T3 — Bad signature + wrong domain',
   'config/scenario_t3.json + tests/test_t3.py — router từ chối + log; không state transition',
   'Router từ chối sai sig: 34%\nLog REJECT: 33%\nKhông state transition: 33%',
   '','Hiếu',9,6,1,'',0.0,'G5'),

  ('T5-04','Scenario T4 — Replay + duplicate tx',
   'config/scenario_t4.json + tests/test_t4.py — tx_id trùng apply tối đa 1 lần',
   'Tx_id trùng reject: 50%\nState reflect 1 lần: 50%',
   '','Khôi',9,6,1,'',0.0,'G5'),

  ('T5-05','Scenario T5 — Drop + delay',
   'config/scenario_t5.json + tests/test_t5.py — safety bất biến; không 2 hash cùng height',
   'Drop msgs: 34%\nDelay msgs: 33%\nSafety: không 2 hash: 33%',
   '','Huy',9,7,2,'',0.0,'G5'),

  ('T5-06','Scenario T6 — Proposer crash',
   'config/scenario_t6.json + tests/test_t6.py — round change, proposer khác finalize',
   'Proposer crash height 1: 34%\nRound change: 33%\nProposer khác finalize: 33%',
   '','Huy',9,7,1,'',0.0,'G5'),

  ('T5-07','Scenario T7 — Equivocation',
   'config/scenario_t7.json + tests/test_t7.py — f=2 conflicting votes; honest không conflict',
   'f=2 equivocate: 34%\nLogged: 33%\nHonest no conflict: 33%',
   '','Khôi',9,8,2,'',0.0,'G5'),

  ('T5-08','Scenario T8 — Determinism',
   'config/scenario_t8.json + tests/test_t8.py — same seed 2 lần → byte-identical log',
   'Log byte-identical: 50%\nState hash same: 50%',
   '','Khánh',10,5,1,'',0.0,'G5'),

  ('T5-09','Export compact summary',
   'src/summary.py — (height,hash) per node, state hash, rejection counts, SHA256 log',
   '(height,hash) per node: 25%\nState hash: 25%\nRejection counts: 25%\nSHA256 log: 25%',
   '','Hiếu',7,5,1,'',0.0,'G5'),

  ('T5-10','--verify-determinism script',
   'tests/verify_determinism.py — 2 lần T8, diff log + state hash, exit 0 nếu identical',
   '2 lần cùng seed: 34%\nDiff log bytes: 33%\nExit 0 identical: 33%',
   '','Bảo',9,4,1,'',0.0,'G5'),

  ('T5-11','Viết REPORT.pdf',
   'REPORT.pdf — kết quả T1–T8, phân tích safety/liveness, <= 10 trang',
   'Kết quả T1–T8: 34%\nSafety analysis: 33%\nLiveness analysis: 33%',
   '','Huy',10,5,2,'',0.0,'G5'),
]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb['Gantt Chart']

    # 1. Unmerge + clear rows 21+
    for m in list(ws.merged_cells.ranges):
        if m.min_row >= 21:
            ws.unmerge_cells(str(m))
    for row in ws.iter_rows(min_row=21, max_row=ws.max_row, min_col=2, max_col=ws.max_column):
        for cell in row:
            cell.value = None
            cell.fill = PatternFill(fill_type=None)

    current_row = 21
    for task in TASKS:
        tid, title, detail, checklist, note, person, priority, diff, days, result, completion, phase = task

        phase_start, phase_end = PHASE_DATES[phase]

        if tid == 'SECTION':
            # Header dòng giai đoạn
            fill_hex = FILL[phase + '_section']
            ws.cell(current_row, 2).value = phase
            ws.cell(current_row, 3).value = title
            style_row(ws, current_row, fill_hex, bold=True, color='1F3864')
            current_row += 2   # section header + 1 dòng trống
            continue

        # Chọn màu theo completion
        if completion >= 1.0:
            fill_hex = FILL['done']
        elif completion > 0.0:
            fill_hex = FILL['partial']
        else:
            fill_hex = FILL[phase]

        r = current_row

        # Ghi dữ liệu
        ws.cell(r, 2).value  = tid
        ws.cell(r, 3).value  = title
        ws.cell(r, 4).value  = detail
        ws.cell(r, 6).value  = checklist
        ws.cell(r, 7).value  = note
        ws.cell(r, 8).value  = person
        ws.cell(r, 9).value  = priority
        ws.cell(r, 10).value = diff
        ws.cell(r, 11).value = phase_start   # Ngày bắt đầu phase
        ws.cell(r, 12).value = phase_end     # Ngày kết thúc phase
        ws.cell(r, 13).value = days          # Số ngày thực hiện (trực tiếp)
        ws.cell(r, 14).value = result
        ws.cell(r, 15).value = completion
        # Công thức đúng: P = I * J * M (không SQRT, không DAYS360)
        ws.cell(r, 16).value = f'=ROUND(I{r}*J{r}*M{r},1)'
        ws.cell(r, 17).value = f'=ROUND(P{r}*O{r},1)'

        # Format ngày
        for col in [11, 12]:
            ws.cell(r, col).number_format = 'DD/MM/YYYY'

        style_row(ws, r, fill_hex)
        current_row += 1

    wb.save(XLSX_PATH)
    print(f'Done. Written up to row {current_row - 1}. Saved: {XLSX_PATH}')

    # Kiểm tra nhanh tổng trọng số theo từng người (tính trong Python)
    people = {'Bảo':0,'Hiếu':0,'Khôi':0,'Khánh':0,'Huy':0}
    wb2 = openpyxl.load_workbook(XLSX_PATH)
    ws2 = wb2['Gantt Chart']
    for row in ws2.iter_rows(min_row=21, max_row=current_row, min_col=2, max_col=17):
        tid_v  = row[0].value   # col B
        person_v = row[6].value  # col H
        i_v   = row[7].value    # col I
        j_v   = row[8].value    # col J
        m_v   = row[11].value   # col M
        if tid_v and str(tid_v).startswith('T') and person_v in people:
            if i_v and j_v and m_v and isinstance(m_v, (int,float)):
                people[person_v] += round(i_v * j_v * m_v, 1)
    print('\nTong trong so (tinh trong Python — khong tinh G0):')
    for p, total in people.items():
        print(f'  {p}: {total}')

if __name__ == '__main__':
    main()
