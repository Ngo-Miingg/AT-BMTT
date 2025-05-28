Terminal 1: Khởi chạy Socket Server
python file_transfer_server.py
Bạn sẽ thấy thông báo: 🚀 [SERVER] Lắng nghe kết nối trên 0.0.0.0:65432...

Terminal 2: Khởi chạy Ứng dụng Web của Server (Giao diện quản lý)
python server_web_interface.py
Mở trình duyệt và truy cập: http://127.0.0.1:5001/ để xem bảng điều khiển của server.

Terminal 3: Khởi chạy Ứng dụng Web Client (Giao diện người dùng)
python app.py
Mở trình duyệt và truy cập: http://127.0.0.1:5000/ để sử dụng ứng dụng mã hóa/giải mã file của người dùng.
