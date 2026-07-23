# Lab 01 — Blockchain Layer-1 Simulator (Python)

Mô phỏng blockchain Layer-1 tối giản với đồng thuận Tendermint-inspired (PREVOTE/PRECOMMIT), mạng P2P mô phỏng có fault injection, thực thi trạng thái key-value xác định, và bộ kiểm thử T1–T8 có thể tái tạo.

---

## Yêu cầu hệ thống

- Python 3.11+
- pip

---

## Cài đặt

```bash
pip install -r requirements.txt
```

---

## Chạy tất cả kiểm thử

```bash
python -m pytest tests/ -v
```

---

## Kiểm tra tính tất định

```bash
python tests/verify_determinism.py
```

Script này chạy một kịch bản **hai lần** với cùng seed và cấu hình, sau đó so sánh byte log thô cùng state hash cuối. Nếu hai kết quả byte-identical thì tính tất định được xác nhận.

---

## Cấu trúc thư mục

```
blockchain/
├── src/                  # Source code
├── tests/                # Unit tests và end-to-end tests
├── logs/                 # Log output từng kịch bản
├── config/               # Cấu hình mặc định và kịch bản
├── docs/                 # Tài liệu đặc tả
├── requirement/          # Tổng hợp yêu cầu
├── requirements.txt      # Python dependencies
└── README.md
```

---

## Tài liệu

Tham khảo thư mục `docs/` để đọc đặc tả đầy đủ:

| File | Nội dung |
|---|---|
| `docs/REQUIREMENTS.md` | Yêu cầu và phạm vi, tiêu chí chấp nhận |
| `docs/PROTOCOL_SPEC.md` | Dữ liệu chuẩn, mật mã, xác thực, quy tắc đồng thuận |
| `docs/ARCHITECTURE.md` | Ranh giới module, luồng thông điệp, trạng thái lưu trữ |
| `docs/TEST_SPEC.md` | Bằng chứng kiểm thử có thể tái tạo, schema log |
| `docs/IMPLEMENTATION_PLAN.md` | Các mốc tiến độ và định nghĩa hoàn thành |

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
Mọi quyết định giả ngẫu nhiên xuất phát từ một seed duy nhất của kịch bản. Thời gian thực không tham gia vào dữ liệu giao thức hay log. Cùng seed và cấu hình luôn tạo ra kết quả byte-identical.

**An toàn (Safety)**
Không có hai block finalize khác nhau tại cùng một chiều cao giữa các node đúng đắn, kể cả trước khi có synchrony. Quorum yêu cầu `2f + 1` trong tổng số `n = 3f + 1` validator.

**Hoạt động (Liveness)**
Sau điểm ổn định mạng và khi chọn được proposer đúng đắn, chuỗi tiếp tục tiến triển. Round transition và timeout đảm bảo hệ thống không bị kẹt vĩnh viễn.
