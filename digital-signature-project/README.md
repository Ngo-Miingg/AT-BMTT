# Hệ thống truyền file hợp đồng an toàn với chữ ký số

## Mô tả
- Truyền file hợp đồng chia thành 3 phần, mã hóa Triple DES, ký số từng phần bằng RSA/SHA-512.
- Xác thực toàn vẹn, trạng thái realtime, log đầy đủ, giao diện rõ ràng.
- Dùng Flask + Flask-SocketIO + SQLAlchemy, code dễ mở rộng và kiểm thử.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy server

```bash
python app.py
```

## Sử dụng

1. Mở 2 trình duyệt/tab:
   - Đăng ký 2 tài khoản user (A và B).
2. A đăng nhập, tạo phiên gửi file cho B.
3. B đăng nhập, xác nhận nhận file.
4. A upload file (bất kỳ), hệ thống sẽ chia nhỏ, gửi từng phần.
5. B xác nhận từng phần, nếu đủ 3 phần sẽ ghép file hoàn chỉnh.
6. Cả hai bên xem log, trạng thái, tải file khi hoàn tất.

## Kiểm thử nâng cao

- Sửa file JS/backend để kiểm tra các trường hợp lỗi hash/chữ ký.
- Kiểm thử nhiều phiên, nhiều user đồng thời.

## Mở rộng

- Đưa sinh/gán public-key/private-key cho từng user để ký số/mã hóa thật.
- Truyền nhiều loại file, file lớn, nhiều phần hơn.
- Cải thiện UI/UX, responsive.

---

**Mọi thắc mắc, lỗi hoặc cần mở rộng, hãy liên hệ hoặc tạo issue.**
