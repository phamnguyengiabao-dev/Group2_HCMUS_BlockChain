# Lab 01 - Chỉ Mục Tài Liệu

Tài liệu này chuyển đổi nội dung `Lab01.pdf` thành baseline sẵn sàng triển khai cho một blockchain Layer-1 tối giản dạng simulator. Tài liệu được thiết kế trung lập về ngôn ngữ lập trình — nhóm có thể chọn ngôn ngữ mà không làm thay đổi hành vi giao thức.

## Thứ tự đọc

1. [Yêu cầu và phạm vi](REQUIREMENTS.md) — những gì cần được thực hiện và tiêu chí chấp nhận.
2. [Đặc tả giao thức](PROTOCOL_SPEC.md) — dữ liệu chuẩn, mật mã, xác thực, và quy tắc đồng thuận.
3. [Kiến trúc hệ thống](ARCHITECTURE.md) — ranh giới module, luồng thông điệp, và trạng thái lưu trữ.
4. [Đặc tả kiểm thử](TEST_SPEC.md) — bằng chứng kiểm thử có thể tái tạo theo yêu cầu bài tập.
5. [Kế hoạch triển khai](IMPLEMENTATION_PLAN.md) — các mốc tiến độ và định nghĩa hoàn thành.

## Các quyết định nền tảng

- **Đồng thuận:** Round-based, lấy cảm hứng từ Tendermint với `PREVOTE` / `PRECOMMIT`; quorum là `2f + 1` cho `n = 3f + 1`.
- **Số node:** Có thể cấu hình, mạng kiểm thử mặc định dùng 8 validator (`f = 2`).
- **Trạng thái:** Bản đồ key-value xác định. Một giao dịch chỉ được ghi vào namespace của người gửi.
- **Mật mã:** Chữ ký Ed25519 và hash SHA-256, với domain separation rõ ràng.
- **Tái tạo:** Mọi quyết định giả ngẫu nhiên đều xuất phát từ một seed duy nhất của kịch bản; thời gian thực không tham gia vào dữ liệu giao thức hay log.

> Đây là các quyết định khởi điểm, không phải yêu cầu bắt buộc. Thay đổi bất kỳ quyết định nào đòi hỏi cập nhật đặc tả giao thức và tái tạo các test tương thích.
