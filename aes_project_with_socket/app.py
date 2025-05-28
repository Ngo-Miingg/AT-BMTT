import os
import socket
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes # For IV and Salt
from Crypto.Hash import SHA256 # For PBKDF2

# --- Cấu hình Flask và SQLAlchemy ---
app = Flask(__name__)
app.secret_key = 'your_super_secret_key_for_flask_session_and_flash' # Rất quan trọng!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db' # Sử dụng SQLite
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Cấu hình Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Trang chuyển hướng nếu người dùng chưa đăng nhập

# --- Cấu hình Socket cho File Transfer Server ---
FILE_TRANSFER_SERVER_HOST = '127.0.0.1' # Thay đổi thành IP của máy chủ file nếu chạy trên máy khác
FILE_TRANSFER_SERVER_PORT = 65432
BUFFER_SIZE = 4096

# --- Cấu hình thư mục tạm thời cho Flask app ---
UPLOAD_FOLDER = 'temp_uploads_app' # File upload tạm thời trước khi gửi đi
RESULT_FOLDER = 'temp_results_app' # File giải mã tạm thời trước khi gửi về client
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# --- Database Model (User) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Hàm giao tiếp Socket (Client Side) ---
def send_bytes_with_length_prefix(sock, data):
    """Gửi dữ liệu qua socket với tiền tố độ dài."""
    sock.sendall(len(data).to_bytes(8, 'big'))
    sock.sendall(data)

def recv_bytes_with_length_prefix(sock):
    """Nhận dữ liệu từ socket với tiền tố độ dài."""
    len_bytes = sock.recv(8)
    if not len_bytes:
        return b""
    data_len = int.from_bytes(len_bytes, 'big')

    data = b""
    while len(data) < data_len:
        packet = sock.recv(min(BUFFER_SIZE, data_len - len(data)))
        if not packet:
            return b""
        data += packet
    return data

def register_username_with_server(user_id, username):
    """Gửi user_id và username đến file_transfer_server để ánh xạ."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            send_bytes_with_length_prefix(s, b"REGISTER_USERNAME")
            send_bytes_with_length_prefix(s, str(user_id).encode('utf-8'))
            send_bytes_with_length_prefix(s, username.encode('utf-8'))
            
            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
            if status == b"USERNAME_MAP_SUCCESS":
                print(f"Registered username '{username}' for user_id '{user_id}' with file server.")
                return True
            else:
                print(f"Failed to register username with file server: {response_msg}")
                return False
    except ConnectionRefusedError:
        print("Error: File transfer server is not running. Cannot register username.")
        return False
    except Exception as e:
        print(f"An error occurred while registering username: {e}")
        return False

# --- Routes của Flask ---

@app.route('/')
def index():
    """Trang chủ, chuyển hướng đến dashboard nếu đã đăng nhập."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Xử lý đăng ký người dùng mới."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            flash('Vui lòng điền đầy đủ tên người dùng và mật khẩu.', 'error')
            return render_template('register.html')

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Tên người dùng đã tồn tại!', 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            # Gửi thông tin username/id đến file server sau khi đăng ký thành công
            register_username_with_server(new_user.id, new_user.username)

            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Xử lý đăng nhập người dùng."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            # Gửi thông tin username/id đến file server sau khi đăng nhập thành công
            register_username_with_server(current_user.id, current_user.username)
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Tên người dùng hoặc mật khẩu không đúng.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Đăng xuất người dùng."""
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Hiển thị dashboard người dùng với danh sách file."""
    owned_files = []
    shared_files_with_me = []
    all_usernames = [] # Để hiển thị trong danh sách chọn người nhận

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            # Lấy danh sách file của người dùng (bao gồm cả file chia sẻ)
            send_bytes_with_length_prefix(s, b"LIST_USER_FILES")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8'))

            status = recv_bytes_with_length_prefix(s)
            if status == b"LIST_SUCCESS":
                files_json_bytes = recv_bytes_with_length_prefix(s)
                all_files = json.loads(files_json_bytes.decode('utf-8'))
                
                # Phân loại file
                for file_info in all_files:
                    if file_info.get('is_shared'):
                        shared_files_with_me.append(file_info)
                    else:
                        owned_files.append(file_info)
            else:
                error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                flash(f"Không thể lấy danh sách file: {error_msg}", 'error')

            # Lấy danh sách tất cả usernames để chia sẻ
            s.close() # Đóng kết nối cũ
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # Mở kết nối mới
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            send_bytes_with_length_prefix(s, b"LIST_ALL_USERNAMES")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Gửi user_id (có thể là dummy cho lệnh này)

            status_usernames = recv_bytes_with_length_prefix(s)
            if status_usernames == b"USERNAME_LIST_SUCCESS":
                usernames_json_bytes = recv_bytes_with_length_prefix(s)
                all_usernames = json.loads(usernames_json_bytes.decode('utf-8'))
                # Lọc bỏ username của chính người dùng hiện tại
                all_usernames = [u for u in all_usernames if u != current_user.username]
            else:
                error_msg_usernames = recv_bytes_with_length_prefix(s).decode('utf-8')
                flash(f"Không thể lấy danh sách người dùng để chia sẻ: {error_msg_usernames}", 'error')

    except ConnectionRefusedError:
        flash(f"Lỗi kết nối: Server file không chạy. Vui lòng đảm bảo \"file_transfer_server.py\" đang chạy.", 'error')
    except Exception as e:
        flash(f"Lỗi khi lấy danh sách file hoặc người dùng: {e}", 'error')

    return render_template('dashboard.html', 
                           owned_files=owned_files, 
                           shared_files_with_me=shared_files_with_me,
                           all_usernames=all_usernames)


@app.route('/encrypt_file', methods=['POST'])
@login_required
def encrypt_file():
    """Mã hóa file và gửi đến server file."""
    file = request.files['file']
    password_input = request.form['password']
    
    if not file or file.filename == '':
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn một file!'}), 400
    if not password_input:
        return jsonify({'status': 'error', 'message': 'Vui lòng nhập mật khẩu mã hóa!'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    with open(filepath, 'rb') as f:
        data = f.read()

    try:
        salt = get_random_bytes(16) # Salt cho PBKDF2
        iv = get_random_bytes(AES.block_size) # IV cho AES CBC mode

        aes_key = PBKDF2(password_input.encode('utf-8'), salt, dkLen=32, count=100000, hmac_hash_module=SHA256) # AES-256
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)

        padded_data = pad(data, AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)

        final_encrypted_content = salt + iv + encrypted_data
        
        encrypted_filename = f'encrypted_AES_{filename}.enc'
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"UPLOAD_USER_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Gửi User ID
            send_bytes_with_length_prefix(s, encrypted_filename.encode('utf-8'))
            send_bytes_with_length_prefix(s, final_encrypted_content)

            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')

            if status == b"UPLOAD_SUCCESS":
                os.remove(filepath)
                return jsonify({'status': 'success', 'message': f"Mã hóa và gửi '{encrypted_filename}' thành công: {response_msg}"})
            else:
                os.remove(filepath)
                return jsonify({'status': 'error', 'message': f"Mã hóa thành công nhưng không thể gửi file: {response_msg}"}), 500

    except ConnectionRefusedError:
        if os.path.exists(filepath): os.remove(filepath)
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy. Vui lòng đảm bảo "file_transfer_server.py" đang chạy.'}), 503
    except Exception as e:
        if os.path.exists(filepath): os.remove(filepath)
        return jsonify({'status': 'error', 'message': f"Lỗi trong quá trình mã hóa: {str(e)}"}), 500

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@app.route('/decrypt_file', methods=['POST'])
@login_required
def decrypt_file():
    """Giải mã file từ server và cung cấp link tải về."""
    password_input = request.form['password']
    filename_to_decrypt = request.form['filename']
    owner_id = request.form.get('owner_id', str(current_user.id)) # Lấy owner_id, mặc định là current_user.id
    
    if not password_input:
        return jsonify({'status': 'error', 'message': 'Vui lòng nhập mật khẩu giải mã!'}), 400
    if not filename_to_decrypt:
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn file cần giải mã!'}), 400

    encrypted_data_from_server = b""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"DOWNLOAD_USER_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Gửi ID của người dùng hiện tại
            send_bytes_with_length_prefix(s, filename_to_decrypt.encode('utf-8'))
            send_bytes_with_length_prefix(s, owner_id.encode('utf-8')) # Gửi ID của chủ sở hữu thực sự

            status = recv_bytes_with_length_prefix(s)
            if status == b"DOWNLOAD_SUCCESS":
                encrypted_data_from_server = recv_bytes_with_length_prefix(s)
            else:
                error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                return jsonify({'status': 'error', 'message': f"Không thể tải file '{filename_to_decrypt}' từ server: {error_msg}"}), 500

        if len(encrypted_data_from_server) < 32: # 16 bytes salt + 16 bytes IV
            return jsonify({'status': 'error', 'message': 'Dữ liệu mã hóa không hợp lệ (quá ngắn để chứa salt và IV).'}), 400
        
        salt = encrypted_data_from_server[:16]
        iv = encrypted_data_from_server[16:32]
        encrypted_data = encrypted_data_from_server[32:]

        aes_key = PBKDF2(password_input.encode('utf-8'), salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)

        decrypted_padded_data = cipher.decrypt(encrypted_data)
        decrypted_data = unpad(decrypted_padded_data, AES.block_size)
        
        original_filename = filename_to_decrypt.replace('encrypted_AES_', '').replace('.enc', '')
        result_path = os.path.join(RESULT_FOLDER, f'decrypted_{original_filename}')

        with open(result_path, 'wb') as f:
            f.write(decrypted_data)

        return jsonify({
            'status': 'success',
            'message': 'Giải mã thành công!',
            'download_link': url_for('download_file', filename=f'decrypted_{original_filename}')
        })

    except ValueError as e: # Lỗi unpad hoặc khóa sai
        return jsonify({'status': 'error', 'message': f"Giải mã thất bại: Có thể do mật khẩu sai hoặc file đã hỏng. ({str(e)})"}), 400
    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy. Vui lòng đảm bảo "file_transfer_server.py" đang chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi trong quá trình giải mã: {str(e)}"}), 500

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Cung cấp file đã giải mã cho người dùng tải về."""
    filepath = os.path.join(RESULT_FOLDER, secure_filename(filename))
    if os.path.exists(filepath):
        # os.remove(filepath) # uncomment để xóa file sau khi tải
        return send_file(filepath, as_attachment=True)
    return "File not found or unauthorized", 404

@app.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    """Xóa file đã mã hóa trên server file."""
    filename_to_delete = request.form.get('filename')
    # Khi xóa file, luôn là file của chính người dùng, nên owner_id là current_user.id
    owner_id_for_delete = str(current_user.id) 

    if not filename_to_delete:
        return jsonify({'status': 'error', 'message': 'Tên file không hợp lệ.'}), 400

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"DELETE_USER_FILE")
            send_bytes_with_length_prefix(s, owner_id_for_delete.encode('utf-8')) # Gửi ID của chủ sở hữu (người dùng hiện tại)
            send_bytes_with_length_prefix(s, filename_to_delete.encode('utf-8'))

            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')

            if status == b"DELETE_SUCCESS":
                return jsonify({'status': 'success', 'message': response_msg})
            else:
                return jsonify({'status': 'error', 'message': response_msg}), 500

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy. Vui lòng đảm bảo "file_transfer_server.py" đang chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi khi xóa file: {str(e)}"}), 500

@app.route('/share_file', methods=['POST'])
@login_required
def share_file():
    """Chia sẻ file của người dùng hiện tại với người dùng khác."""
    filename_to_share = request.form.get('filename')
    receiver_username = request.form.get('receiver_username')

    if not filename_to_share or not receiver_username:
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn file và nhập tên người dùng nhận.'}), 400

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"SHARE_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Người gửi
            send_bytes_with_length_prefix(s, receiver_username.encode('utf-8')) # Người nhận (username)
            send_bytes_with_length_prefix(s, filename_to_share.encode('utf-8')) # Tên file

            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')

            if status == b"SHARE_SUCCESS":
                return jsonify({'status': 'success', 'message': response_msg})
            else:
                return jsonify({'status': 'error', 'message': response_msg}), 500

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy. Vui lòng đảm bảo "file_transfer_server.py" đang chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi khi chia sẻ file: {str(e)}"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Tạo bảng nếu chưa có
    app.run(host='0.0.0.0', debug=True, port=5000) # Đảm bảo chạy trên cổng 5000
