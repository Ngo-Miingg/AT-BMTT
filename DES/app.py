from flask import Flask, render_template, request, send_file
from pyDes import des, PAD_PKCS5
import os
from werkzeug.utils import secure_filename

# Khởi tạo ứng dụng Flask
app = Flask(__name__)

# Tạo thư mục để lưu file tải lên và kết quả
UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    # Trang chủ hiển thị giao diện người dùng
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_file():
    # Nhận file và khóa từ form
    file = request.files['file']
    key_input = request.form['key']
    mode = request.form['mode']

    if not key_input:
        return "⚠️ Vui lòng nhập khóa!"

    # Đảm bảo tên file an toàn và lưu vào thư mục upload
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Đọc dữ liệu từ file
    with open(filepath, 'rb') as f:
        data = f.read()

    # CHUẨN HÓA KHÓA:
    # DES yêu cầu khóa đúng 8 byte => nếu người dùng nhập ngắn hơn sẽ đệm thêm '0'
    key_bytes = key_input.encode()              # Chuyển sang byte
    des_key_raw = key_bytes.ljust(8, b'0')[:8]  # Đảm bảo đúng 8 byte
    print("Khóa sử dụng (sau chuẩn hóa):", des_key_raw)

    # Khởi tạo đối tượng DES với khóa trên
    cipher = des(des_key_raw, padmode=PAD_PKCS5)

    # Tiến hành mã hóa hoặc giải mã
    if mode == 'encrypt':
        processed_data = cipher.encrypt(data)
        result_filename = 'encrypted_' + filename
        print("📦 Đã mã hóa thành công.")
    else:
        try:
            processed_data = cipher.decrypt(data)
            print("🔓 Đã giải mã thành công.")
        except Exception as e:
            print("❌ Lỗi giải mã:", str(e))
            return "⚠️ Giải mã thất bại. Có thể do khóa sai hoặc dữ liệu không hợp lệ."
        result_filename = 'decrypted_' + filename

    # Ghi dữ liệu kết quả ra file
    result_path = os.path.join(RESULT_FOLDER, result_filename)
    with open(result_path, 'wb') as f:
        f.write(processed_data)

    # Gửi file kết quả cho người dùng tải về
    return send_file(result_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
