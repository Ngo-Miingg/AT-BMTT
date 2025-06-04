import os
import socket
import json
import hashlib # Added for SHA-256
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
# Removed Crypto imports as AES is no longer used

# --- Cấu hình Flask và SQLAlchemy ---
app = Flask(__name__)
app.secret_key = 'your_super_secret_key_for_flask_session_and_flash'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Cấu hình Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Cấu hình Socket cho File Transfer Server ---
FILE_TRANSFER_SERVER_HOST = '127.0.0.1'
FILE_TRANSFER_SERVER_PORT = 65432
BUFFER_SIZE = 4096 # Used for reading file for hashing and sending

# --- Cấu hình thư mục tạm thời cho Flask app ---
UPLOAD_FOLDER = 'temp_uploads_app' # For temporarily saving uploads before hashing/sending
RESULT_FOLDER = 'temp_results_app' # For temporarily saving downloaded files
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# --- Database Model (User) --- (No change)
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

# --- Hàm giao tiếp Socket (Client Side) --- (No change to these helpers)
def send_bytes_with_length_prefix(sock, data):
    sock.sendall(len(data).to_bytes(8, 'big'))
    sock.sendall(data)

def recv_bytes_with_length_prefix(sock):
    len_bytes = sock.recv(8)
    if not len_bytes: return b""
    data_len = int.from_bytes(len_bytes, 'big')
    data = b""
    while len(data) < data_len:
        packet = sock.recv(min(BUFFER_SIZE, data_len - len(data)))
        if not packet: return b""
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
            # response_msg = recv_bytes_with_length_prefix(s).decode('utf-8') # msg can be used if needed
            recv_bytes_with_length_prefix(s) # consume msg
            if status == b"USERNAME_MAP_SUCCESS":
                print(f"Registered/Verified username '{username}' for user_id '{user_id}' with file server.")
                return True
            else:
                # print(f"Failed to register username with file server: {response_msg}")
                return False
    except ConnectionRefusedError:
        print("Error: File transfer server is not running. Cannot register username.")
        flash("File server is offline. Some features might be unavailable.", "warning")
        return False
    except Exception as e:
        print(f"An error occurred while registering username: {e}")
        return False

# --- Routes của Flask ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
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
            
            register_username_with_server(new_user.id, new_user.username)
            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            register_username_with_server(current_user.id, current_user.username)
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Tên người dùng hoặc mật khẩu không đúng.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    owned_files = []
    shared_files_with_me = []
    all_usernames = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"LIST_USER_FILES")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8'))

            status = recv_bytes_with_length_prefix(s)
            if status == b"LIST_SUCCESS":
                files_json_bytes = recv_bytes_with_length_prefix(s)
                all_user_files_data = json.loads(files_json_bytes.decode('utf-8'))
                
                for file_info in all_user_files_data:
                    if file_info.get('is_shared'):
                        shared_files_with_me.append(file_info)
                    else:
                        owned_files.append(file_info)
            else:
                error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                flash(f"Không thể lấy danh sách file: {error_msg}", 'error')

        # Re-open socket for next command or use a persistent connection if server supports it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_users:
            s_users.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            send_bytes_with_length_prefix(s_users, b"LIST_ALL_USERNAMES")
            send_bytes_with_length_prefix(s_users, str(current_user.id).encode('utf-8')) # Requester ID

            status_usernames = recv_bytes_with_length_prefix(s_users)
            if status_usernames == b"USERNAME_LIST_SUCCESS":
                usernames_json_bytes = recv_bytes_with_length_prefix(s_users)
                all_usernames_server = json.loads(usernames_json_bytes.decode('utf-8'))
                all_usernames = [u for u in all_usernames_server if u != current_user.username]
            else:
                error_msg_usernames = recv_bytes_with_length_prefix(s_users).decode('utf-8')
                flash(f"Không thể lấy danh sách người dùng để chia sẻ: {error_msg_usernames}", 'error')

    except ConnectionRefusedError:
        flash(f"Lỗi kết nối: Server file không chạy hoặc đang bận. Vui lòng thử lại sau.", 'error')
    except Exception as e:
        flash(f"Lỗi khi tải dashboard: {e}", 'error')

    return render_template('dashboard.html', 
                           owned_files=owned_files, 
                           shared_files_with_me=shared_files_with_me,
                           all_usernames=all_usernames)


@app.route('/upload_file', methods=['POST']) # Renamed from /encrypt_file
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Không có file nào được chọn!'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn một file hợp lệ!'}), 400

    filename = secure_filename(file.filename)
    temp_filepath = os.path.join(UPLOAD_FOLDER, filename + "_" + str(current_user.id) + "_temp") # Ensure unique temp file
    
    try:
        file.save(temp_filepath)

        sha256_hash = hashlib.sha256()
        with open(temp_filepath, 'rb') as f:
            while True:
                data_chunk = f.read(BUFFER_SIZE)
                if not data_chunk:
                    break
                sha256_hash.update(data_chunk)
        file_hex_hash = sha256_hash.hexdigest()

        with open(temp_filepath, 'rb') as f_read:
            file_data_content = f_read.read() # Read content to send

    except Exception as e_file_proc:
        if os.path.exists(temp_filepath): os.remove(temp_filepath)
        return jsonify({'status': 'error', 'message': f'Lỗi xử lý file cục bộ: {str(e_file_proc)}'}), 500
    finally:
        if os.path.exists(temp_filepath): os.remove(temp_filepath)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"UPLOAD_USER_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8'))
            send_bytes_with_length_prefix(s, filename.encode('utf-8'))
            send_bytes_with_length_prefix(s, file_data_content) # Send actual file data
            send_bytes_with_length_prefix(s, file_hex_hash.encode('utf-8')) # Send hash

            status_code = recv_bytes_with_length_prefix(s)
            response_msg_bytes = recv_bytes_with_length_prefix(s)
            response_msg = response_msg_bytes.decode('utf-8') if response_msg_bytes else "Không có phản hồi."


            if status_code == b"UPLOAD_SUCCESS_VERIFIED":
                return jsonify({'status': 'success', 'message': f"'{filename}': {response_msg}"})
            elif status_code == b"UPLOAD_FAILED_INTEGRITY_CHECK":
                 return jsonify({'status': 'error', 'message': f"'{filename}': {response_msg}"}), 422 # Unprocessable Entity
            else: # UPLOAD_FAILED_SERVER_ERROR or other
                return jsonify({'status': 'error', 'message': f"Lỗi tải lên '{filename}': {response_msg}"}), 500

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi trong quá trình tải lên: {str(e)}"}), 500


@app.route('/download_transmitted_file', methods=['POST']) # Renamed from /decrypt_file
@login_required
def download_transmitted_file():
    filename_to_download = request.form.get('filename')
    # owner_id is the actual owner of the file (can be current_user or another user if shared)
    owner_id = request.form.get('owner_id', str(current_user.id)) 
    
    if not filename_to_download:
        return jsonify({'status': 'error', 'message': 'Tên file không hợp lệ!'}), 400

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"DOWNLOAD_USER_FILE")
            # current_user.id is the ID of the user requesting the download
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) 
            send_bytes_with_length_prefix(s, filename_to_download.encode('utf-8'))
            send_bytes_with_length_prefix(s, owner_id.encode('utf-8')) # ID of the file's actual owner

            status = recv_bytes_with_length_prefix(s)
            if status == b"DOWNLOAD_SUCCESS":
                file_data_content = recv_bytes_with_length_prefix(s)
                
                # Sanitize filename for saving locally
                safe_original_filename = secure_filename(filename_to_download)
                result_filename = f'downloaded_{safe_original_filename}'
                result_path = os.path.join(RESULT_FOLDER, result_filename)

                with open(result_path, 'wb') as f:
                    f.write(file_data_content)

                # Calculate SHA-256 hash of the downloaded file
                sha256_hash = hashlib.sha256()
                with open(result_path, 'rb') as f:
                    while True:
                        data_chunk = f.read(BUFFER_SIZE)
                        if not data_chunk:
                            break
                        sha256_hash.update(data_chunk)
                downloaded_hex = sha256_hash.hexdigest()

                return jsonify({
                'status': 'success',
                'message': 'File sẵn sàng để tải xuống!',
                'download_link': url_for('download_file_from_temp', filename=result_filename),
                'sha256': downloaded_hex
            })

            elif status == b"DOWNLOAD_FAILED_NOT_FOUND":
                 error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                 return jsonify({'status': 'error', 'message': f"Không thể tải '{filename_to_download}': {error_msg}"}), 404
            elif status == b"DOWNLOAD_FAILED_PERMISSION":
                 error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                 return jsonify({'status': 'error', 'message': f"Không thể tải '{filename_to_download}': {error_msg}"}), 403
            else: # Other errors
                error_msg = recv_bytes_with_length_prefix(s).decode('utf-8')
                return jsonify({'status': 'error', 'message': f"Lỗi tải file '{filename_to_download}': {error_msg}"}), 500

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi khi tải file: {str(e)}"}), 500

@app.route('/download_from_temp/<filename>') # Renamed for clarity
@login_required
def download_file_from_temp(filename):
    """Cung cấp file đã tải về (từ server) cho người dùng."""
    filepath = os.path.join(RESULT_FOLDER, secure_filename(filename))
    if os.path.exists(filepath):
        # Consider deleting the file after download for security/cleanup
        # response = send_file(filepath, as_attachment=True)
        # try:
        #     os.remove(filepath)
        # except OSError as e_remove:
        #     print(f"Error removing temp file {filepath}: {e_remove}")
        # return response
        return send_file(filepath, as_attachment=True)

    flash("File không tìm thấy hoặc đã bị xóa.", "error")
    return redirect(url_for('dashboard'))


@app.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    filename_to_delete = request.form.get('filename')
    # Users can only delete their own files. current_user.id is the owner.
    if not filename_to_delete:
        return jsonify({'status': 'error', 'message': 'Tên file không hợp lệ.'}), 400

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"DELETE_USER_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Owner ID
            send_bytes_with_length_prefix(s, filename_to_delete.encode('utf-8'))

            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')

            if status == b"DELETE_SUCCESS":
                return jsonify({'status': 'success', 'message': response_msg})
            else: # DELETE_FAILED or DELETE_FAILED_NOT_FOUND
                return jsonify({'status': 'error', 'message': response_msg}), 500

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi khi xóa file: {str(e)}"}), 500

@app.route('/share_file', methods=['POST'])
@login_required
def share_file():
    filename_to_share = request.form.get('filename')
    receiver_username = request.form.get('receiver_username')

    if not filename_to_share or not receiver_username:
        return jsonify({'status': 'error', 'message': 'Vui lòng chọn file và người dùng nhận.'}), 400

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((FILE_TRANSFER_SERVER_HOST, FILE_TRANSFER_SERVER_PORT))
            
            send_bytes_with_length_prefix(s, b"SHARE_FILE")
            send_bytes_with_length_prefix(s, str(current_user.id).encode('utf-8')) # Sender ID
            send_bytes_with_length_prefix(s, receiver_username.encode('utf-8'))
            send_bytes_with_length_prefix(s, filename_to_share.encode('utf-8'))

            status = recv_bytes_with_length_prefix(s)
            response_msg = recv_bytes_with_length_prefix(s).decode('utf-8')

            if status == b"SHARE_SUCCESS":
                return jsonify({'status': 'success', 'message': response_msg})
            else: # SHARE_FAILED_NO_RECEIVER, SHARE_FAILED_SELF_SHARE, SHARE_FAILED_FILE_NOT_FOUND, SHARE_FAILED_ALREADY_SHARED
                return jsonify({'status': 'error', 'message': response_msg}), 500 # Or specific codes like 404, 400

    except ConnectionRefusedError:
        return jsonify({'status': 'error', 'message': 'Lỗi kết nối: Server file không chạy.'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Lỗi khi chia sẻ file: {str(e)}"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', debug=True, port=5000)