# Blockchain Visualizer

Dashboard web tương tác để visualize dữ liệu từ blockchain simulator, xây dựng bằng **Dash + Dash-Cytoscape + Plotly**.

---

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt](#cài-đặt)
3. [Khởi động](#khởi-động)
4. [Giao diện và tính năng](#giao-diện-và-tính-năng)
5. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
6. [Cách thêm log mới](#cách-thêm-log-mới)
7. [Tuỳ chỉnh](#tuỳ-chỉnh)

---

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu |
|---|---|
| Python | 3.10+ |
| dash | 2.18+ |
| dash-cytoscape | 1.0+ |
| plotly | 5.24+ |
| pandas | 2.0+ |

---

## Cài đặt

### Bước 1 — Clone / mở project

```bash
# Đảm bảo bạn đang ở thư mục gốc của project
cd d:\Coding\blockchain
```

### Bước 2 — Cài dependencies dashboard

```bash
pip install "dash==2.18.2" "dash-cytoscape==1.0.2" "plotly==5.24.1"
```

> `pandas` đã có sẵn trong môi trường này. Nếu chưa: `pip install pandas`

Hoặc cài tất cả một lần:

```bash
pip install -r requirements-dashboard.txt
```

### Bước 3 — Kiểm tra

```bash
python -c "import dash, dash_cytoscape, plotly; print('OK')"
```

---

## Khởi động

Chạy từ thư mục gốc của project (không phải từ trong `dashboard/`):

```bash
# Cách 1 — chạy như module (khuyến nghị)
python -m dashboard.app

# Cách 2 — chạy trực tiếp file
python dashboard/app.py

# Cách 3 — bật debug mode (hot-reload khi sửa code)
python dashboard/app.py --debug

# Cách 4 — đổi port
python dashboard/app.py --port 8080

# Cách 5 — cho phép truy cập từ máy khác trong LAN
python dashboard/app.py --host 0.0.0.0 --port 8050
```

Sau khi chạy, mở trình duyệt và truy cập:

```
http://127.0.0.1:8050
```

---

## Giao diện và tính năng

### Header — Chọn log file

Góc trên phải có dropdown để chọn bất kỳ file `.jsonl` nào trong thư mục `logs/`.  
Nhấn **↻ Refresh** để reload log hiện tại (hữu ích khi scenario đang chạy).

---

### Thanh KPI (stat cards)

Hiển thị ngay dưới header, tự động cập nhật khi đổi log:

| Card | Ý nghĩa |
|---|---|
| Scenario | ID của scenario đang xem |
| Validators | Số validator trong mạng |
| Total Events | Tổng số events trong log |
| Max Height | Block height cao nhất |
| Finalised | Số block đã được finalize |
| Equivocations | Số lần phát hiện Byzantine |
| Crashes | Số lần node crash |
| Timeouts | Số timeout xảy ra |

---

### Tab 1 — 📊 Overview

- **Scenario Config**: Hiển thị toàn bộ cấu hình scenario (seed, topology, network delay, v.v.)
- **Event Distribution**: Biểu đồ cột ngang thống kê số lượng từng loại event

---

### Tab 2 — 🔗 Chain View

- **Finalised Chain**: Biểu đồ chain từ Genesis → block cuối. Hover vào từng block để xem hash, round, số transaction.
- **Rounds per Height**: Line chart cho thấy consensus tốn bao nhiêu round ở mỗi height (cao → nhiều lần retry → có vấn đề).

---

### Tab 3 — 🌐 Validator Network

- **Cytoscape graph** hiển thị toàn bộ validator nodes và topology kết nối.
- Màu node:
  - 🔵 Xanh dương — Validator bình thường
  - 🟠 Cam — Proposer
  - 🔴 Đỏ — Byzantine node
  - ⚫ Xám — Node đã crash
  - 🟢 Xanh lá — System node
- **Click vào node** → panel bên phải hiện thống kê events của node đó.
- **Layout buttons**: Cose / Circle / Grid / Breadthfirst để đổi cách sắp xếp đồ thị.
- Scroll để zoom, kéo để pan, kéo node để di chuyển.

---

### Tab 4 — 📈 Event Timeline

- **Filter** theo node và/hoặc loại event (multi-select).
- **Scatter Timeline**: Trục X = logical time, trục Y = node. Mỗi chấm = 1 event, màu theo loại. Hover để xem chi tiết.
- **Event Log Table**: Bảng đầy đủ với sort, filter, phân trang. Các event quan trọng được tô màu nền:
  - 🟢 Xanh — FINALIZE
  - 🔴 Đỏ — EQUIVOCATION, CRASH

---

### Tab 5 — 🗳 Vote Matrix

- Nhập **Height** và **Round** muốn xem.
- **Heatmap**: 2 hàng (PREVOTE / PRECOMMIT) × N cột (validators).
  - 🟢 Xanh → đã vote với một block hash
  - 🔴 Đỏ → vote NIL
  - ⚫ Xám → không có vote

---

## Cấu trúc thư mục

```
dashboard/
├── app.py            # Entry point — khởi động Dash app
├── layout.py         # Toàn bộ layout HTML/Dash (tabs, panels, dropdowns)
├── callbacks.py      # Tất cả Dash callbacks (reactive logic)
├── charts.py         # Plotly figure builders (timeline, chain, heatmap, ...)
├── components.py     # UI components tái sử dụng (stat card, badge, legend)
├── data_loader.py    # Parse JSONL logs + config, build data structures
├── assets/
│   └── style.css     # CSS toàn cục (Catppuccin Mocha dark theme)
└── README.md         # Tài liệu này
```

---

## Cách thêm log mới

Dashboard tự động phát hiện mọi file `.jsonl` trong cây thư mục `logs/`.

1. Chạy scenario simulator và để nó ghi log vào `logs/<scenario_id>/<run_id>.jsonl`
2. Nhấn **↻ Refresh** hoặc **reload trang**
3. File mới xuất hiện trong dropdown

Không cần restart server.

---

## Tuỳ chỉnh

### Đổi màu event

Sửa dict `EVENT_COLOURS` trong `dashboard/data_loader.py`:

```python
EVENT_COLOURS: dict[str, str] = {
    "FINALIZE": "#00AA44",   # đổi màu ở đây
    ...
}
```

### Đổi màu node

Sửa dict `NODE_COLOURS` trong `dashboard/data_loader.py`:

```python
NODE_COLOURS: dict[str, str] = {
    "byzantine": "#D0021B",  # đổi màu Byzantine node
    ...
}
```

### Đổi theme CSS

Sửa `dashboard/assets/style.css`. Dash tự động reload CSS khi lưu file (trong debug mode).

### Thêm chart mới

1. Thêm function trả về `go.Figure` trong `dashboard/charts.py`
2. Thêm `dcc.Graph(id="chart-xyz")` vào layout phù hợp trong `dashboard/layout.py`
3. Thêm `@app.callback(Output("chart-xyz", "figure"), ...)` trong `dashboard/callbacks.py`

---

## Troubleshooting

| Vấn đề | Giải pháp |
|---|---|
| `ModuleNotFoundError: No module named 'dashboard'` | Chạy từ thư mục gốc project, không phải từ trong `dashboard/` |
| `ModuleNotFoundError: No module named 'dash'` | `pip install dash dash-cytoscape plotly` |
| Trang trắng / không load | Mở DevTools (F12) kiểm tra console errors; thử `--debug` flag |
| Dropdown không có log file nào | Kiểm tra `logs/` có file `.jsonl` không; kiểm tra đường dẫn |
| Cytoscape graph không hiện | Đảm bảo `dash-cytoscape >= 1.0.2`; thử đổi layout sang Circle |
