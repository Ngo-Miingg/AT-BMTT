from flask import Flask, render_template, request, send_file
from Crypto.Cipher import AES # Thay thế pyDes bằng AES từ pycryptodome
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

    if not file:
        return "⚠️ Vui lòng chọn một file!"
    if not key_input:
        return "⚠️ Vui lòng nhập khóa!"

    # Đảm bảo tên file an toàn và lưu vào thư mục upload
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Đọc dữ liệu từ file
    with open(filepath, 'rb') as f:
        data = f.read()

    # CHUẨN HÓA KHÓA CHO AES-128:
    # AES-128 yêu cầu khóa đúng 16 byte.
    # Mã hóa chuỗi khóa sang bytes (UTF-8), sau đó đệm bằng byte 0 hoặc cắt bớt.
    key_bytes = key_input.encode('utf-8')
    aes_key = (key_bytes + b'\0' * AES.block_size)[:AES.block_size] # AES.block_size thường là 16
    print("Khóa AES sử dụng (sau chuẩn hóa, 16 bytes):", aes_key)

    # Khởi tạo đối tượng AES với khóa trên, chế độ ECB
    # CHÚ Ý: Chế độ ECB không an toàn cho hầu hết các ứng dụng.
    # Cân nhắc sử dụng AES.MODE_CBC hoặc AES.MODE_CTR với IV ngẫu nhiên cho bảo mật tốt hơn.
    cipher = AES.new(aes_key, AES.MODE_ECB)

    # Tiến hành mã hóa hoặc giải mã
    if mode == 'encrypt':
        # Zero-padding dữ liệu để là bội số của kích thước khối AES (16 bytes)
        # Logic padding này mô phỏng cách AES-encrypt.cpp xử lý
        original_len = len(data)
        padded_message_len = original_len
        if original_len == 0: # Nếu file rỗng, C++ code đệm thành 1 khối
            padded_message_len = AES.block_size
        elif (padded_message_len % AES.block_size) != 0:
            padded_message_len = (padded_message_len // AES.block_size + 1) * AES.block_size

        # Tạo buffer với byte 0 và chép dữ liệu gốc vào
        # bytearray tự động khởi tạo bằng byte 0 nếu không có đối số khởi tạo giá trị
        padded_data_arr = bytearray(padded_message_len)
        padded_data_arr[:original_len] = data
        padded_data = bytes(padded_data_arr)

        processed_data = cipher.encrypt(padded_data)
        result_filename = 'encrypted_AES_' + filename
        print("📦 Đã mã hóa AES thành công.")
    else: # mode == 'decrypt'
        # Dữ liệu cần giải mã phải là bội số của kích thước khối
        if len(data) % AES.block_size != 0:
            print(f"❌ Lỗi giải mã: Độ dài dữ liệu ({len(data)}) không phải là bội số của kích thước khối ({AES.block_size}).")
            return "⚠️ Giải mã thất bại. Dữ liệu không hợp lệ (kích thước không đúng)."
        try:
            processed_data = cipher.decrypt(data)
            # Lưu ý: Với zero-padding, không thể loại bỏ padding một cách đáng tin cậy
            # nếu dữ liệu gốc có thể chứa byte 0 ở cuối.
            # File giải mã sẽ chứa các byte 0 đệm thêm (nếu có).
            # Bạn có thể thử: processed_data = processed_data.rstrip(b'\0')
            # nhưng điều này sẽ xóa cả các byte 0 hợp lệ ở cuối dữ liệu gốc.
            print("🔓 Đã giải mã AES thành công.")
        except Exception as e:
            print("❌ Lỗi giải mã AES:", str(e))
            return "⚠️ Giải mã thất bại. Có thể do khóa sai hoặc dữ liệu không hợp lệ."
        result_filename = 'decrypted_AES_' + filename

    # Ghi dữ liệu kết quả ra file
    result_path = os.path.join(RESULT_FOLDER, result_filename)
    with open(result_path, 'wb') as f:
        f.write(processed_data)

    # Gửi file kết quả cho người dùng tải về
    return send_file(result_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)