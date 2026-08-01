# Lab 01 — Blockchain Layer-1 Simulator (Python)

Mô phỏng blockchain Layer-1 tối giản với đồng thuận Tendermint-inspired (PREVOTE/PRECOMMIT), mạng P2P mô phỏng có fault injection, thực thi trạng thái key-value xác định, và bộ kiểm thử có thể tái tạo.

---

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt](#cài-đặt)
3. [Kiến trúc tổng thể](#kiến-trúc-tổng-thể)
4. [Phân tích chi tiết từng tầng](#phân-tích-chi-tiết-từng-tầng)
5. [Mô tả chi tiết từng module](#mô-tả-chi-tiết-từng-module)
6. [Luồng validate một Transaction](#luồng-validate-một-transaction)
7. [Cấu hình](#cấu-hình)
8. [Chạy & Build](#chạy--build)
9. [Kiểm thử](#kiểm-thử)
10. [Tính chất được bảo vệ bởi tests](#tính-chất-được-bảo-vệ-bởi-tests)
11. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
12. [Tiến độ Milestone](#tiến-độ-milestone)
13. [Ma trận kiểm thử T1–T8](#ma-trận-kiểm-thử-t1t8)
14. [Nguyên tắc thiết kế](#nguyên-tắc-thiết-kế)
15. [Tài liệu tham khảo](#tài-liệu-tham-khảo)

---

## Yêu cầu hệ thống

- Python **3.11+**
- pip

Thư viện phụ thuộc (xem `requirements.txt`):

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

## Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────┐
│                      scenario_runner                    │
│   Nạp config → Khởi tạo validators → Chạy consensus    │
│   → Ghi EventLog → Trả về summary (sha256, path...)     │
└────────────┬──────────────────────┬─────────────────────┘
             │                      │
     ┌───────▼──────┐     ┌─────────▼──────────┐
     │   event_log  │     │       state         │
     │  Ghi JSONL   │     │  Key-value map có   │
     │  canonical   │     │  canonical ordering │
     └──────────────┘     └──────────┬──────────┘
                                     │ state_hash()
             ┌───────────────────────┼────────────────────┐
             │                       │                     │
     ┌───────▼──────┐     ┌──────────▼──────┐   ┌────────▼──────┐
     │   encoding   │     │     crypto      │   │  transaction  │
     │  Canonical   │     │  SHA-256 hash   │   │  TX model +   │
     │  byte encode │     │  Ed25519 sign/  │   │  validation   │
     │              │     │  verify         │   │               │
     └──────────────┘     └─────────────────┘   └───────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │      identity       │
                          │  Load & validate    │
                          │  8 validator keypairs│
                          └─────────────────────┘
```

**Luồng dữ liệu chính:**

1. `scenario_runner` đọc file config kịch bản và config mặc định.
2. Khởi tạo `EventLog` → ghi sự kiện `SCENARIO_START` và `NODE_INIT` cho từng validator.
3. (Khi `max_height > 0`) Thực thi vòng consensus: propose → prevote → precommit → finalize.
4. Mỗi block thực thi danh sách `Transaction`, cập nhật `State`.
5. `State.state_hash()` dùng `encoding.encode_sorted_map` + `crypto.hash_bytes` để tạo commitment có thể tái tạo.
6. Ghi sự kiện `SCENARIO_END`, đóng log, trả về SHA-256 của file log.

---

## Phân tích chi tiết từng tầng

Toàn bộ `src/` được tổ chức thành 3 tầng phụ thuộc rõ ràng — tầng dưới không biết gì về tầng trên.

```
TẦNG CAO — điều phối
    scenario_runner.py
         │
TẦNG GIỮA — dữ liệu & giao thức
    state.py    event_log.py    transaction.py    identity.py
         │                           │
TẦNG NỀN — mật mã & encoding (không phụ thuộc gì cả)
    crypto.py                  encoding.py
```

---

### Tầng nền: `crypto.py` và `encoding.py`

Đây là **nền móng không thể thiếu**. Không có hai file này, không có gì hoạt động đúng.

**`crypto.py`** làm 3 việc:

```
hash_bytes(data)
    → SHA-256 → luôn trả về đúng 32 bytes, reject non-bytes

sign(privkey, domain, payload)
    → xây message = utf8(domain) + 0x00 + payload
    → ký bằng Ed25519 → trả về 64-byte signature

verify(pubkey, domain, payload, signature)
    → xây lại message tương tự
    → kiểm tra signature → True/False, KHÔNG bao giờ raise exception
```

Tại sao cần **domain separation**? Nếu không có domain, một chữ ký trên giao dịch `TX` có thể bị tái sử dụng như một phiếu bầu `VOTE`. Domain string ngăn chặn hoàn toàn điều đó:

```
TX:lab01   → chỉ hợp lệ cho giao dịch
PREVOTE    → chỉ hợp lệ cho phiếu bầu prevote
PRECOMMIT  → chỉ hợp lệ cho phiếu bầu precommit
```

**`encoding.py`** giải quyết vấn đề cốt lõi: **hai node phải hash cùng giá trị → phải có cùng byte representation**.

Python dict không có thứ tự ổn định. JSON không đảm bảo thứ tự key. String Unicode có thể có nhiều cách biểu diễn khác nhau. Encoding này giải quyết tất cả:

```python
encode_uint64(42)
# → b'\x00\x00\x00\x00\x00\x00\x00\x2a'  (luôn 8 bytes, big-endian)

encode_bytes(b"hello")
# → b'\x00\x00\x00\x05hello'  (4-byte length prefix + data)

encode_str("é")          # dù là precomposed hay decomposed Unicode
# → b'\x00\x00\x00\x02\xc3\xa9'  (NFC normalize trước, rồi UTF-8)

encode_sorted_map({"z": b"Z", "a": b"A"})
# → count=2 || key="a" || val=b"A" || key="z" || val=b"Z"
#   LUÔN sort theo UTF-8 bytes của key, không theo thứ tự chèn
```

**Quy tắc vàng:** Không bao giờ hash/sign trực tiếp dict, string hay JSON thô. Phải qua encoder này.

---

### Tầng giữa: 4 module nghiệp vụ

**`state.py`** là "sổ cái" — nơi lưu trạng thái đã được đồng thuận:

```
State
 ├── insert("alice_pubkey_hash/balance", b"1000")
 ├── insert("bob_pubkey_hash/balance",   b"500")
 └── ...

state.state_hash()
 = SHA256(encode_sorted_map(tất cả entries)) = 32 bytes
```

Hai node khác nhau cùng thực thi cùng giao dịch theo cùng thứ tự → `state_hash()` **phải** cho cùng giá trị. Vì vậy iteration phải sort theo UTF-8 bytes của key, không theo thứ tự chèn. Method `copy()` dùng để thực thi thử một block — nếu có TX lỗi thì vứt bản sao đi, state gốc không bị ảnh hưởng.

**`transaction.py`** là một lệnh ghi vào state — yêu cầu: *"Tôi, người có public key X, muốn ghi giá trị V vào key K"*. Key phải có prefix là `hash(pubkey)/` để ngăn validator A ghi đè dữ liệu của validator B.

**`identity.py`** quản lý 8 validator cố định. Điểm quan trọng là **cross-validation**: khi load, mỗi private key được dùng để derive public key, sau đó so sánh với public key lưu trong file. Không thể load key hỏng mà không biết.

**`event_log.py`** ghi mọi sự kiện thành JSONL với thứ tự field cố định. Thứ tự field cố định là bắt buộc vì SHA-256 của file log được dùng để verify determinism — nếu `json.dumps()` sinh key theo thứ tự khác nhau giữa hai lần chạy thì SHA-256 khác nhau dù nội dung logic như nhau.

---

### Tầng cao: `scenario_runner.py`

Entry point của toàn bộ simulation. Với `max_height=0` (kịch bản noop), tổng cộng có **10 events**: 1 `SCENARIO_START` + 8 `NODE_INIT` + 1 `SCENARIO_END`. Phần consensus (`max_height > 0`) hiện là placeholder, sẽ được triển khai ở M3–M4.

---

## Mô tả chi tiết từng module

### `src/crypto.py` — Nguyên thủy mật mã

Cung cấp các hàm mật mã nền tảng cho toàn bộ giao thức.

| Hàm | Mô tả |
|---|---|
| `hash_bytes(data: bytes) -> bytes` | SHA-256 hash, luôn trả về đúng 32 bytes. Từ chối non-bytes. |
| `sign(privkey, domain, payload) -> bytes` | Ký `payload` với Ed25519, dùng domain separation: `utf8(domain) \|\| 0x00 \|\| payload`. Trả về 64-byte signature. |
| `verify(pubkey, domain, payload, signature) -> bool` | Xác thực chữ ký. Trả về `False` cho mọi đầu vào không hợp lệ hoặc không khớp, không raise exception. |

**Domain separation** đảm bảo signature dùng trong context `TX:lab01` không thể bị replay sang context `PREVOTE` hay `PRECOMMIT`.

---

### `src/encoding.py` — Canonical byte encoding

Tất cả giá trị được hash hoặc ký đều đi qua bộ mã hóa canonical này (PROTOCOL_SPEC.md §2). Đảm bảo hai node chạy cùng dữ liệu luôn sinh ra byte giống hệt nhau.

| Hàm | Định dạng output |
|---|---|
| `encode_uint64(value)` | 8 bytes big-endian |
| `encode_bool(value)` | 1 byte: `0x01` (True) hoặc `0x00` (False) |
| `encode_bytes(data)` | u32 big-endian length prefix (4 bytes) + raw data |
| `encode_str(text)` | NFC-normalize → UTF-8 → `encode_bytes` |
| `encode_optional_hash(hash_bytes)` | `0x00` nếu None; `0x01` + 32 bytes nếu có |
| `encode_sorted_map(values)` | u64 entry_count + các cặp (key, value) sắp xếp theo UTF-8 bytes của key |

Hàm `encode_sorted_map` đặc biệt quan trọng: nó đảm bảo map luôn encode theo thứ tự xác định bất kể thứ tự chèn vào Python dict.

---

### `src/state.py` — Trạng thái key-value

Lưu trạng thái được đồng thuận: ánh xạ từ string key sang byte value.

**Tính chất quan trọng:**
- Keys được NFC-normalize khi đọc/ghi, đồng nhất với `encode_str`.
- Iteration luôn theo thứ tự canonical (sorted by raw UTF-8 bytes), không bao giờ theo thứ tự chèn.
- `state_hash()` = `SHA256(encode_sorted_map(entries))` — commitment hash có thể tái tạo trên bất kỳ node nào đã thực thi cùng giao dịch.

| Phương thức | Mô tả |
|---|---|
| `insert(key, value)` | Upsert — ghi đè nếu key đã tồn tại |
| `delete(key)` | Xóa key, trả về `True` nếu tồn tại |
| `get(key, default)` | Đọc giá trị, trả về default nếu không có |
| `has(key)` | Kiểm tra sự tồn tại |
| `keys() / values() / items()` | Trả về theo canonical order |
| `copy()` | Tạo bản sao độc lập (executor dùng để discard khi TX thất bại) |
| `canonical_bytes()` | Byte encoding của toàn bộ state |
| `state_hash()` | 32-byte SHA-256 commitment |
| `state_hash_hex()` | Hex string của commitment (dùng cho log/UI) |

---

### `src/transaction.py` — Mô hình và validation giao dịch

Định nghĩa `Transaction` dataclass và logic validation đầy đủ.

**Cấu trúc một transaction:**

| Field | Kiểu | Mô tả |
|---|---|---|
| `chain_id` | `str` | ID chuỗi (phải khớp với config) |
| `nonce` | `int` | Số thứ tự, tăng dần per sender, chống replay |
| `sender_pubkey` | `bytes` | Ed25519 public key 32 bytes |
| `key` | `str` | State key phải có prefix `hex(SHA256(pubkey))/` |
| `value_bytes` | `bytes` | Giá trị muốn ghi vào state |
| `signature` | `bytes` | Ed25519 signature 64 bytes |

**Phương thức:**

| Phương thức | Mô tả |
|---|---|
| `unsigned_bytes()` | Canonical bytes của TX không có signature (dùng làm payload khi ký) |
| `signed_bytes()` | Canonical bytes của TX đầy đủ |
| `tx_id()` | `SHA256(unsigned_bytes + signature)` — 32 bytes, dùng để dedup |
| `expected_namespace()` | `hex(SHA256(sender_pubkey)) + "/"` |
| `validate(...)` | Kiểm tra chain_id, nonce, key size, value size, namespace, signature |

**Trình tự validate:** type checks → chain_id → nonce → pubkey length → signature length → key size → value size → namespace prefix → Ed25519 signature verify.

---

### `src/identity.py` — Quản lý validator identity

Nạp và kiểm tra chéo 8 cặp khóa validator từ `config/validator_keys.json`.

| Hàm / Class | Mô tả |
|---|---|
| `ValidatorIdentity` | Dataclass frozen: `index`, `public_key` (32 bytes), `private_key` (32 bytes) |
| `load_validator_keys(config_path)` | Đọc JSON, kiểm tra hex length, kiểm tra cross-validate (derive pubkey từ privkey), sắp xếp theo index |
| `get_validator(index)` | Trả về `ValidatorIdentity` theo index; cache kết quả load lần đầu |

Hàm `load_validator_keys` từ chối load nếu public key lưu trong JSON không khớp với public key được derive từ private key — đảm bảo file config không bị hỏng.

---

### `src/event_log.py` — Canonical JSONL event logger

Ghi log sự kiện theo định dạng JSONL (JSON Lines) có thứ tự key cố định.

**Cấu trúc một dòng log:**

```json
{"event_no":1,"logical_time":0,"node_id":"system","event_type":"SCENARIO_START","height":0,"round":0,"details":{...}}
```

Thứ tự field cố định: `event_no`, `logical_time`, `node_id`, `event_type`, `height`, `round`, `details`. Keys trong `details` luôn sorted alphabetically.

| Phương thức | Mô tả |
|---|---|
| `write_event(...)` | Ghi một dòng JSON canonical vào file |
| `close()` | Flush và đóng file |
| `get_sha256()` | SHA-256 hex của toàn bộ file log (dùng để verify determinism) |

Log được lưu tại `logs/<scenario_id>/<run_id>.jsonl`.

---

### `src/scenario_runner.py` — Điều phối kịch bản

Hàm `run_scenario(scenario_config, default_config, run_id)` là entry point chạy một kịch bản.

**Trình tự thực thi:**

1. Đọc `scenario_id`, `seed`, `num_validators`, `max_height` từ config.
2. Ghi sự kiện `SCENARIO_START` với config fingerprint (SHA-256 của JSON canonical).
3. Ghi sự kiện `NODE_INIT` cho từng validator (index 0 → N-1).
4. Nếu `max_height > 0`: thực thi consensus (placeholder cho các phase sau).
5. Ghi sự kiện `SCENARIO_END`.
6. Trả về dict gồm: `scenario_id`, `run_id`, `log_path`, `log_sha256`, `total_events`.

---

## Luồng validate một Transaction

Đây là luồng quan trọng nhất để hiểu cách hệ thống bảo vệ tính toàn vẹn:

```
Người dùng có private_key và public_key
    │
    ▼
Xây key hợp lệ:
    namespace = SHA256(public_key).hex() + "/"
    key       = namespace + "balance"          ← chỉ được ghi vào "vùng" của mình

    ▼
Tạo unsigned transaction:
    chain_id     = "lab01-testnet"
    nonce        = 1                           ← tăng dần, chống replay
    sender_pubkey = public_key
    key          = namespace + "balance"
    value_bytes  = b"1000"

    ▼
unsigned_bytes() = encode_str(chain_id)
                 + encode_uint64(nonce)
                 + encode_bytes(sender_pubkey)
                 + encode_str(key)
                 + encode_bytes(value_bytes)

    ▼
signature = sign(private_key, "TX:lab01-testnet", unsigned_bytes())
                                ↑
                        domain separation ngăn reuse sang PREVOTE/PRECOMMIT

    ▼
Transaction hoàn chỉnh (6 fields bao gồm signature)

    ▼
tx.validate(expected_chain_id, expected_nonce, max_key, max_value)

    Pipeline 9 bước (theo đúng thứ tự):
    1. Type check  (chain_id str? nonce int? pubkey bytes? ...)
    2. chain_id    khớp với mạng đang chạy?
    3. nonce       đúng bằng nonce hiện tại của sender?
    4. pubkey      đúng 32 bytes?
    5. signature   đúng 64 bytes?
    6. key UTF-8   có vượt max_key_size_bytes không?
    7. value       có vượt max_value_size_bytes không?
    8. namespace   key có bắt đầu bằng hash(pubkey)/ không?
    9. Ed25519     chữ ký có hợp lệ không?

    ▼
Nếu OK → ghi vào state[key] = value_bytes
Nếu fail → raise ValueError với error code rõ ràng
           (INVALID_CHAIN_ID, INVALID_NONCE, INVALID_NAMESPACE, ...)
```

---

## Cấu hình

### `config/default.json` — Thông số mạng mặc định

```json
{
  "chain_id": "lab01-testnet",
  "spec_version": "0.1",
  "block_capacity": 10,
  "network": {
    "max_block_size_bytes": 65536,
    "max_key_size_bytes": 256,
    "max_value_size_bytes": 4096
  }
}
```

### `config/scenario_noop.json` — Kịch bản no-op (baseline)

```json
{
  "scenario_id": "noop",
  "seed": 42,
  "num_validators": 8,
  "f": 2,
  "max_height": 0
}
```

`max_height: 0` có nghĩa chỉ khởi tạo node, không chạy vòng consensus — dùng để test scaffolding và determinism.

### `config/validator_keys.json` — 8 cặp khóa Ed25519

8 validator với index 0–7, mỗi entry gồm `index`, `public_key_hex`, `private_key_hex`. File này được `identity.py` nạp và cross-validate.

---

## Chạy & Build

Dự án là pure Python, không có bước build/compile. Cài đặt dependencies là đủ:

```bash
pip install -r requirements.txt
```

### Chạy kịch bản no-op

```python
import json
from src.scenario_runner import run_scenario

scenario = json.load(open("config/scenario_noop.json"))
default  = json.load(open("config/default.json"))

summary = run_scenario(scenario, default, run_id="my_run")
print(summary)
# {'scenario_id': 'noop', 'run_id': 'my_run', 'log_path': 'logs/noop/my_run.jsonl',
#  'log_sha256': '...', 'total_events': 10}
```

### Kiểm tra tính tất định (determinism)

```bash
python tests/verify_determinism.py
```

Script chạy kịch bản noop **hai lần** với cùng seed, so sánh từng byte và SHA-256. Output mẫu:

```
PASS — both runs produced identical logs (SHA-256: a3f2...)
```

---

## Kiểm thử

### Chạy toàn bộ test suite

```bash
python -m pytest tests/ -v
```

### Chạy theo nhóm (marker)

```bash
# Chỉ test SHA-256 hash
python -m pytest tests/ -v -m hash

# Chỉ test sign/verify
python -m pytest tests/ -v -m sign_verify
```

### Chạy một file test cụ thể

```bash
python -m pytest tests/test_crypto.py -v
python -m pytest tests/test_encoding.py -v
python -m pytest tests/test_identity.py -v
python -m pytest tests/test_transaction.py -v
python -m pytest tests/test_noop.py -v
```

### Đo độ phủ kiểm thử (coverage)

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

### Mô tả các file kiểm thử

| File | Module được test | Những gì được kiểm tra |
|---|---|---|
| `tests/test_crypto.py` | `src/crypto.py` | SHA-256 vectors, sign/verify domain separation, malformed key/sig rejection |
| `tests/test_encoding.py` | `src/encoding.py` | Known vectors, NFC normalization, collision resistance, determinism |
| `tests/test_identity.py` | `src/identity.py` | Load 8 validators, key lengths, sign/verify round-trip, cross-validator rejection |
| `tests/test_transaction.py` | `src/transaction.py` | Valid TX, TX ID, rejects wrong chain_id/nonce/namespace/signature/size |
| `tests/test_noop.py` | `src/scenario_runner.py` + `src/event_log.py` | Log tồn tại, valid JSONL, event_no monotonic |
| `tests/verify_determinism.py` | Toàn bộ pipeline | Hai lần chạy cùng seed → byte-identical log + SHA-256 khớp |

---

## Tính chất được bảo vệ bởi tests

Mỗi file test bảo vệ một nhóm tính chất cụ thể. Bảng này hữu ích khi vấn đáp:

| Tính chất | File test | Câu hỏi điển hình |
|---|---|---|
| SHA-256 đúng vector chuẩn | `test_crypto.py` | "SHA256(b'abc') bằng bao nhiêu hex?" |
| Domain separation hoạt động | `test_crypto.py` | "Sig ký dưới TX: có verify được dưới PREVOTE không?" |
| Collision resistance của encoding | `test_encoding.py` | "Tại sao cần length prefix?" |
| NFC normalization | `test_encoding.py` | "é precomposed và é decomposed phải cho cùng bytes" |
| 8 validator load đúng thứ tự | `test_identity.py` | "index của validators có được sort không?" |
| Cross-validation keypair | `test_identity.py` | "Điều gì xảy ra nếu public key trong file không khớp?" |
| Sign/verify round-trip | `test_identity.py` | "Validator 0 ký, validator 1 verify → kết quả gì?" |
| Namespace ownership | `test_transaction.py` | "Validator A có ghi được vào namespace của B không?" |
| Replay protection (nonce) | `test_transaction.py` | "Gửi lại TX với nonce cũ → xảy ra gì?" |
| TX ID deterministic | `test_transaction.py` | "tx_id() gọi hai lần có cho cùng kết quả không?" |
| Log tồn tại và hợp lệ JSONL | `test_noop.py` | "event_no phải bắt đầu từ mấy và tăng như thế nào?" |
| Determinism toàn pipeline | `verify_determinism.py` | "Hai lần chạy cùng seed → SHA-256 log có giống nhau không?" |

---

## Cấu trúc thư mục

```
blockchain/
├── src/
│   ├── __init__.py
│   ├── crypto.py           # SHA-256 hash, Ed25519 sign/verify với domain separation
│   ├── encoding.py         # Canonical byte encoding (uint64, bool, bytes, str, map)
│   ├── event_log.py        # JSONL event logger tất định
│   ├── identity.py         # Load & validate 8 validator keypairs
│   ├── scenario_runner.py  # Điều phối kịch bản, tạo event log
│   ├── state.py            # Key-value state map với canonical ordering và state hash
│   └── transaction.py      # Transaction model, encoding, validation
│
├── tests/
│   ├── __init__.py
│   ├── test_crypto.py          # Unit tests: hash & sign/verify
│   ├── test_encoding.py        # Unit tests: canonical encoding
│   ├── test_identity.py        # Unit tests: validator identity
│   ├── test_noop.py            # Integration test: noop scenario
│   ├── test_transaction.py     # Unit tests: transaction validation
│   └── verify_determinism.py   # Script kiểm tra tính tất định
│
├── config/
│   ├── default.json            # Thông số mạng và giao thức mặc định
│   ├── scenario_noop.json      # Kịch bản no-op (max_height=0)
│   ├── scenario_t1.json        # Kịch bản T1: chạy bình thường
│   ├── scenario_t8.json        # Kịch bản T8: kiểm tra tính tất định
│   └── validator_keys.json     # 8 cặp khóa Ed25519 (index 0–7)
│
├── logs/
│   └── noop/                   # Log output của kịch bản noop
│       ├── determinism_run_a.jsonl
│       ├── determinism_run_b.jsonl
│       └── test_run_noop.jsonl
│
├── docs/
│   ├── ARCHITECTURE.md         # Ranh giới module, luồng thông điệp
│   ├── PROTOCOL_SPEC.md        # Dữ liệu chuẩn, mật mã, quy tắc đồng thuận
│   ├── REQUIREMENTS.md         # Yêu cầu và tiêu chí chấp nhận
│   ├── TEST_SPEC.md            # Schema log, bằng chứng kiểm thử
│   ├── IMPLEMENTATION_PLAN.md  # Các mốc tiến độ
│   └── requirement/            # Tài liệu yêu cầu tiếng Việt
│
├── .kiro/specs/                # Kiro spec (requirements, design, tasks)
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Cấu hình pytest và markers
└── README.md
```

---

## Tiến độ Milestone

Dự án theo kế hoạch 6 milestone (M0–M5). Đây là trạng thái hiện tại:

| Milestone | Tên | Trạng thái | Ghi chú |
|---|---|---|---|
| **M0** | Repository Scaffold | ✅ Hoàn thành | Cấu trúc thư mục, fixtures, kịch bản noop chạy được |
| **M1** | Các Primitive Xác Định | 🟡 ~90% | Còn thiếu Deterministic Executor |
| **M2** | Xác Thực Dữ Liệu và Lưu Trữ | 🔲 Chưa bắt đầu | Block header, body, vote objects, block store |
| **M3** | Mạng Xác Định | 🔲 Chưa bắt đầu | Scheduler, fault injection, envelope routing |
| **M4** | Đồng Thuận và Khôi Phục | 🔲 Chưa bắt đầu | Consensus engine, proposer selection, finalization |
| **M5** | Bằng Chứng và Nộp Bài | 🔲 Chưa bắt đầu | T3, T4, T8 hoàn thành, REPORT.pdf |

---

### Chi tiết M1 — Các Primitive Xác Định

Định nghĩa hoàn thành của M1: *"Unit test crypto/state pass và cùng một block thực thi hai lần cho byte/hash giống nhau."*

| Hạng mục M1 | File | Trạng thái |
|---|---|---|
| Canonical encoding | `src/encoding.py` | ✅ Đầy đủ — 6 hàm encode, có test |
| SHA-256 helpers | `src/crypto.py` → `hash_bytes()` | ✅ Đầy đủ — known-vector tests pass |
| Ed25519 signing/verification | `src/crypto.py` → `sign()`, `verify()` | ✅ Đầy đủ — domain separation, có test |
| Identity fixtures | `src/identity.py` + `config/validator_keys.json` | ✅ Đầy đủ — 8 validator, cross-validate |
| Transaction object và validation | `src/transaction.py` | ✅ Đầy đủ — 9-bước validate, có test |
| Sorted-state hashing | `src/state.py` | ✅ Đầy đủ — `state_hash()`, canonical ordering |
| **Deterministic Executor** | ❌ **Chưa có** | 🔲 **Còn thiếu** |

**Deterministic Executor** là module còn thiếu. Nó sẽ chịu trách nhiệm:
- Nhận danh sách Transaction trong một block
- Thực thi từng TX theo thứ tự: validate → ghi vào State
- Quản lý **nonce map** per-sender (State chỉ lưu data, không lưu nonce)
- Đảm bảo: cùng danh sách TX + cùng state ban đầu → luôn ra cùng `state_hash()`

Hiện tại trong `scenario_runner.py`:

```python
if max_height > 0:
    # Placeholder for future consensus simulation phases.
    pass
```

Các building block (`State`, `Transaction.validate()`) đã sẵn sàng — chỉ cần viết thêm executor để nối chúng lại.

---

## Ma trận kiểm thử T1–T8

| ID | Kịch bản | Điều kiện kiểm tra |
|---|---|---|
| **T1** | Chạy bình thường, không có lỗi | Mọi node đúng đắn finalize các height, hash và state hash cuối giống nhau |
| **T2** | Thông điệp trùng lặp và sắp xếp lại | Mỗi tuple vote đếm tối đa một validator; không có finalization xung đột |
| **T3** | Chữ ký không hợp lệ và domain sai | Router từ chối thông điệp, ghi lý do, không có chuyển đổi state/vote tiếp theo |
| **T4** | Replay hoặc giao dịch trùng lặp | Một `tx_id` được áp dụng không quá một lần trong lịch sử đã finalize |
| **T5** | Drop/delay trước synchrony | Bất biến safety duy trì suốt; không có hai hash finalize tại một height |
| **T6** | Proposer im lặng / crash | Proposal timeout/round transition xảy ra và proposer đúng đắn sau đó finalize |
| **T7** | Tối đa `f` validator equivocating | Equivocation được ghi log; các node đúng đắn không finalize block xung đột |
| **T8** | Cùng seed, hai lần chạy | Log chuẩn thô và state hash cuối byte-identical |

---

## Nguyên tắc thiết kế

**Tất định (Determinism)**
Mọi quyết định giả ngẫu nhiên xuất phát từ một seed duy nhất của kịch bản. Thời gian thực không tham gia vào dữ liệu giao thức hay log. Cùng seed và cấu hình luôn tạo ra kết quả byte-identical. Không có map nào được iterate theo thứ tự Python dict — luôn dùng sorted order.

**An toàn (Safety)**
Không có hai block finalize khác nhau tại cùng một chiều cao giữa các node đúng đắn, kể cả trước khi có synchrony. Quorum yêu cầu `2f + 1` trong tổng số `n = 3f + 1` validator.

**Hoạt động (Liveness)**
Sau điểm ổn định mạng và khi chọn được proposer đúng đắn, chuỗi tiếp tục tiến triển. Round transition và timeout đảm bảo hệ thống không bị kẹt vĩnh viễn.

**Canonical encoding**
Mọi giá trị được hash hoặc ký đều đi qua bộ encoder canonical. Không bao giờ dùng `str()`, `repr()`, hay JSON với key order không xác định làm pre-image.

**Domain separation**
Mỗi loại thông điệp được ký có domain string riêng (ví dụ `TX:lab01`, `PREVOTE`, `PRECOMMIT`). Signature ở một context không thể bị reuse ở context khác.

---

## Tài liệu tham khảo

| File | Nội dung |
|---|---|
| `docs/REQUIREMENTS.md` | Yêu cầu và phạm vi, tiêu chí chấp nhận |
| `docs/PROTOCOL_SPEC.md` | Dữ liệu chuẩn, mật mã, xác thực, quy tắc đồng thuận |
| `docs/ARCHITECTURE.md` | Ranh giới module, luồng thông điệp, trạng thái lưu trữ |
| `docs/TEST_SPEC.md` | Bằng chứng kiểm thử có thể tái tạo, schema log |
| `docs/IMPLEMENTATION_PLAN.md` | Các mốc tiến độ và định nghĩa hoàn thành |
