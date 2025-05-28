Hệ thống Mã hóa/Giải mã File AES với Chia sẻ và Giám sát Server
Đây là một hệ thống ứng dụng web cho phép người dùng mã hóa, giải mã và quản lý các file cá nhân của họ. Hệ thống được xây dựng với kiến trúc Client-Server, bao gồm một ứng dụng web phía người dùng, một server socket chuyên dụng để xử lý việc lưu trữ và truyền file, và một giao diện web riêng biệt để quản lý server.

Tính năng chính
Quản lý người dùng: Đăng ký, đăng nhập, đăng xuất an toàn.

Mã hóa & Giải mã file: Sử dụng thuật toán AES với PBKDF2 để bảo vệ dữ liệu người dùng.

Quản lý file cá nhân: Tải lên file đã mã hóa, liệt kê, giải mã và xóa file.

Chia sẻ file giữa các người dùng: Người dùng có thể chia sẻ file đã mã hóa của họ với người dùng khác trong hệ thống.

Giám sát Server (Web Interface): Giao diện web riêng cho phép quản trị viên xem tổng quan về lưu trữ, danh sách người dùng và lịch sử chia sẻ file.

Kiến trúc hệ thống
Hệ thống bao gồm ba thành phần chính hoạt động độc lập:

Ứng dụng Client Web (app.py):

Được xây dựng bằng Flask.

Cung cấp giao diện người dùng (dashboard) cho phép đăng ký, đăng nhập, tải lên file để mã hóa, yêu cầu giải mã file và xóa file.

Giao tiếp với File Transfer Socket Server thông qua socket để thực hiện các thao tác file.

Chạy trên cổng 5000.

File Transfer Socket Server (file_transfer_server.py):

Một server socket độc lập, không có giao diện web.

Chịu trách nhiệm lưu trữ và quản lý các file đã mã hóa cho từng người dùng trong thư mục users_encrypted_files.

Xử lý các yêu cầu từ Ứng dụng Client Web và Ứng dụng Web Server (nếu cần) để lưu, liệt kê, tải xuống, xóa và quản lý chia sẻ file.

Duy trì ánh xạ user_id và username để hỗ trợ tính năng chia sẻ.

Lưu trữ thông tin chia sẻ file trong shared_files.json và ánh xạ người dùng trong user_id_map.json.

Chạy trên cổng 65432.

Ứng dụng Web Server (server_web_interface.py):

Một ứng dụng web Flask riêng biệt.

Cung cấp giao diện quản trị viên để giám sát trạng thái server, xem tổng quan về lưu trữ file của tất cả người dùng, và xem lịch sử chia sẻ file.

Cho phép quản trị viên tải xuống các file đã mã hóa và xóa toàn bộ dữ liệu của một người dùng.

Đọc trực tiếp các file cơ sở dữ liệu shared_files.json và user_id_map.json để hiển thị thông tin.

Chạy trên cổng 5001.

Cấu hình và Cài đặt
Yêu cầu
Python 3.x

pip

Cài đặt thư viện
Mở terminal và chạy lệnh sau để cài đặt các thư viện cần thiết:

pip install Flask Flask-SQLAlchemy Flask-Login Werkzeug pycryptodome

Cấu trúc thư mục
Đảm bảo các file của bạn được sắp xếp theo cấu trúc sau:

your_project/
├── app.py                      # Ứng dụng Client Web
├── file_transfer_server.py     # Socket Server
├── server_web_interface.py     # Ứng dụng Web Server
└── templates/
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    └── server_dashboard.html   # Template cho giao diện server

Cách chạy hệ thống
Bạn cần mở ba cửa sổ terminal riêng biệt và chạy từng thành phần theo thứ tự sau:

Bước 1: Khởi chạy File Transfer Socket Server
Đây là trái tim của hệ thống lưu trữ file. Nó phải chạy đầu tiên.

# Trong Terminal 1
python file_transfer_server.py

Bạn sẽ thấy thông báo: 🚀 [SERVER] Lắng nghe kết nối trên 0.0.0.0:65432...

Bước 2: Khởi chạy Ứng dụng Web Server (Giao diện quản lý)
Ứng dụng này cung cấp giao diện web cho quản trị viên.

# Trong Terminal 2
python server_web_interface.py

Bạn sẽ thấy thông báo: * Running on http://0.0.0.0:5001/
Mở trình duyệt web của bạn và truy cập: http://127.0.0.1:5001/

Bước 3: Khởi chạy Ứng dụng Client Web (Giao diện người dùng)
Đây là ứng dụng mà người dùng cuối sẽ tương tác để mã hóa/giải mã và chia sẻ file.

# Trong Terminal 3
python app.py

Bạn sẽ thấy thông báo: * Running on http://0.0.0.0:5000/
Mở trình duyệt web của bạn và truy cập: http://127.0.0.1:5000/

Hướng dẫn sử dụng
Ứng dụng Client Web (http://127.0.0.1:5000/)
Đăng ký & Đăng nhập:

Truy cập trang chủ, nhấp vào "Đăng ký" để tạo tài khoản mới.

Sử dụng thông tin đăng ký để "Đăng nhập".

Lưu ý: Đăng ký và đăng nhập bằng ít nhất hai tài khoản khác nhau (ví dụ: user1, user2) để kiểm tra tính năng chia sẻ.

Mã hóa File:

Trên Dashboard, chọn một file từ máy tính của bạn.

Nhập mật khẩu mã hóa (mật khẩu này sẽ được dùng để giải mã).

Nhấp "Mã hóa và Tải lên". File đã mã hóa sẽ được gửi đến file_transfer_server.py.

Giải mã File:

Trong phần "File của bạn" hoặc "File được chia sẻ với bạn", nhấp vào "Giải mã" bên cạnh file bạn muốn.

Nhập mật khẩu đã dùng để mã hóa file đó.

Nếu mật khẩu đúng, bạn sẽ nhận được liên kết để tải xuống file đã giải mã.

Xóa File:

Trong phần "File của bạn", nhấp vào "Xóa" bên cạnh file bạn muốn xóa.

Lưu ý: Chỉ có chủ sở hữu file mới có thể xóa file.

Chia sẻ File:

Trong phần "File của bạn", nhấp vào "Chia sẻ" bên cạnh file bạn muốn chia sẻ.

Trong cửa sổ bật lên, chọn tên người dùng bạn muốn chia sẻ file đó.

Nhấp "Xác nhận Chia sẻ". File sẽ xuất hiện trong phần "File được chia sẻ với bạn" của người nhận.

Ứng dụng Web Server (http://127.0.0.1:5001/)
Tổng quan Server:

Xem trạng thái của File Transfer Socket Server.

Kiểm tra tổng số file đã mã hóa và tổng kích thước lưu trữ.

Dữ liệu người dùng:

Xem danh sách các thư mục người dùng (được tạo tự động bằng user ID).

Xem số lượng và kích thước file trong mỗi thư mục người dùng.

Tải xuống các file đã mã hóa của từng người dùng (dành cho mục đích quản lý/kiểm tra).

Xóa toàn bộ dữ liệu của một người dùng.

Lịch sử chia sẻ File:

Xem danh sách các giao dịch chia sẻ file, bao gồm ai đã chia sẻ file nào cho ai.

Lưu ý về bảo mật
Hệ thống này được thiết kế như một ví dụ minh họa và có thể không đáp ứng tất cả các yêu cầu bảo mật của một ứng dụng thực tế. Một số điểm cần cân nhắc:

Quản lý mật khẩu: Mật khẩu mã hóa/giải mã được người dùng nhập trực tiếp. Trong môi trường thực tế, cần có thêm các biện pháp bảo vệ khóa.

Xác thực & Ủy quyền: Flask-Login cung cấp xác thực cơ bản, nhưng các hệ thống lớn hơn cần cơ chế ủy quyền mạnh mẽ hơn.

Bảo mật Socket: Giao tiếp socket giữa client web và server file không được mã hóa. Trong môi trường sản phẩm, nên sử dụng SSL/TLS cho kênh truyền thông này.

Lưu trữ file: File được lưu trữ trên server. Cần có các biện pháp sao lưu và bảo vệ vật lý cho dữ liệu.

Xử lý lỗi: Xử lý lỗi cơ bản đã được triển khai, nhưng cần mở rộng để bao quát mọi trường hợp có thể xảy ra.
