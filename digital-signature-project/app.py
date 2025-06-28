# file: app.py (Phiên bản cuối cùng, ghi log ra file)

import os
import shutil
import traceback
import math
import uuid
import logging # MỚI: Import thư viện logging
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import crypto_utils

# --- KHỞI TẠO ỨNG DỤNG ---
app = Flask(__name__)
app.secret_key = 'a-very-secret-and-random-key-for-sessions'
socketio = SocketIO(app)

# =======================================================
# MỚI: CẤU HÌNH HỆ THỐNG GHI LOG RA FILE
# =======================================================
logging.basicConfig(level=logging.INFO)
# Tạo một logger để ghi vào file
file_handler = logging.FileHandler('server_activity.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
# Định dạng của mỗi dòng log: [Thời gian] - [Cấp độ] - [Nội dung]
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
# Gắn bộ ghi file này vào logger của Flask
app.logger.addHandler(file_handler)
# =======================================================


# Cấu hình database và các thư mục
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DOWNLOAD_FOLDER = os.path.join(basedir, 'downloads')
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

db = SQLAlchemy(app)

# --- MODEL (Giữ nguyên) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    public_key_path = db.Column(db.String(120), nullable=False)
    private_key_path = db.Column(db.String(120), nullable=False)

# --- BIẾN TOÀN CỤC ---
pending_files = {} # Biến này vẫn giữ để xử lý file chờ real-time

# --- CÁC ROUTE XÁC THỰC (Cập nhật để ghi log) ---
@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('app_page'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('app_page'))
    if request.method == 'POST':
        username, password = request.form['username'].strip(), request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'], session['username'] = user.id, user.username
            app.logger.info(f"User '{username}' logged in successfully.") # Ghi log
            return redirect(url_for('app_page'))
        else:
            app.logger.warning(f"Failed login attempt for username '{username}'.") # Ghi log
            flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session: return redirect(url_for('app_page'))
    if request.method == 'POST':
        username, password = request.form['username'].strip(), request.form['password']
        if not username or not password:
            flash('Tên đăng nhập và mật khẩu không được để trống.', 'warning')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập này đã tồn tại.', 'warning')
            return redirect(url_for('register'))
        crypto_utils.generate_rsa_keys(username)
        new_user = User(username=username, password_hash=generate_password_hash(password),
                        public_key_path=f'{username}/public.pem', private_key_path=f'{username}/private.pem')
        db.session.add(new_user)
        db.session.commit()
        app.logger.info(f"New user '{username}' created.") # Ghi log
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    app.logger.info(f"User '{session.get('username')}' logged out.") # Ghi log
    session.clear()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('login'))

# --- TRANG ỨNG DỤNG VÀ ADMIN ---
@app.route('/app')
def app_page():
    if 'user_id' not in session: return redirect(url_for('login'))
    other_users = User.query.filter(User.id != session['user_id']).all()
    return render_template('index.html', username=session['username'], other_users=other_users)

@app.route('/admin')
def admin_page():
    if session.get('username') != 'admin':
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('app_page'))
    
    all_users = User.query.all()
    
    # MỚI: Đọc 100 dòng cuối từ file log để hiển thị
    try:
        with open('server_activity.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()
        recent_logs = logs[-100:] # Lấy 100 dòng cuối
        recent_logs.reverse() # Đảo ngược để dòng mới nhất lên trên
    except FileNotFoundError:
        recent_logs = ["Chưa có file log. Hãy thực hiện một vài hành động."]

    return render_template('admin.html', username='admin', users=all_users, logs=recent_logs)

# --- API ---
@app.route('/api/admin/delete_user', methods=['POST'])
def delete_user():
    # ... (Giữ nguyên logic, nhưng thêm log)
    if session.get('username') != 'admin': return jsonify({"success": False, "error": "Không có quyền"}), 403
    user_id = request.json.get('user_id')
    user_to_delete = User.query.get(user_id)
    if user_to_delete:
        if user_to_delete.username == 'admin': return jsonify({"success": False, "error": "Không thể xóa tài khoản admin."})
        try:
            app.logger.warning(f"Admin '{session.get('username')}' is deleting user '{user_to_delete.username}'.") # Ghi log
            if os.path.exists(user_to_delete.username): shutil.rmtree(user_to_delete.username)
            db.session.delete(user_to_delete)
            db.session.commit()
            app.logger.info(f"Admin successfully deleted user '{user_to_delete.username}'.") # Ghi log
            return jsonify({"success": True})
        except Exception as e: return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": False, "error": "Không tìm thấy người dùng."})

@app.route('/api/send', methods=['POST'])
def send_file():
    # ... (Giữ nguyên logic, nhưng thêm log)
    if 'username' not in session: return jsonify({"error": "Chưa đăng nhập"}), 401
    sender_name, recipient_name = session['username'], request.form.get('recipient')
    file = request.files.get('file')
    if not all([recipient_name, file]): return jsonify({"error": "Thiếu thông tin"}), 400
    sender = User.query.filter_by(username=sender_name).first()
    recipient = User.query.filter_by(username=recipient_name).first()
    if not recipient: return jsonify({"error": "Người nhận không tồn tại"}), 404
    try:
        # ... (logic mã hóa giữ nguyên)
        file_content = file.read()
        session_key = crypto_utils.get_random_bytes(24)
        encrypted_session_key_bytes = crypto_utils.rsa_encrypt(session_key, recipient.public_key_path)
        if encrypted_session_key_bytes is None: return jsonify({"error": f"Không thể tải khóa của '{recipient_name}'."}), 500
        file_size = len(file_content)
        if file_size < 3: parts = [file_content[i:i+1] for i in range(file_size)]
        else:
            part_size = math.ceil(file_size / 3)
            parts = [file_content[i:i+part_size] for i in range(0, file_size, part_size)]
        packages = []
        for part_data in parts:
            if not part_data: continue
            iv_b64, cipher_b64 = crypto_utils.encrypt_3des(part_data, session_key)
            data_to_process = crypto_utils.base64.b64decode(iv_b64) + crypto_utils.base64.b64decode(cipher_b64)
            hash_val = crypto_utils.hash_sha512(data_to_process)
            signature_bytes = crypto_utils.sign_data(data_to_process, sender.private_key_path)
            if signature_bytes is None: return jsonify({"error": f"Không thể tải khóa của '{sender_name}'."}), 500
            packages.append({"iv": iv_b64.decode(), "cipher": cipher_b64.decode(), "hash": hash_val, "sig": signature_bytes.decode()})
        file_data = {"sender": sender_name, "original_filename": file.filename, "encrypted_session_key": encrypted_session_key_bytes.decode(), "packages": packages}
        if recipient_name not in pending_files: pending_files[recipient_name] = []
        pending_files[recipient_name].append(file_data)
        app.logger.info(f"User '{sender_name}' sent file '{file.filename}' to '{recipient_name}'.") # Ghi log
        socketio.emit('new_file', {'sender': sender_name}, room=recipient_name)
        return jsonify({"success": True, "message": f"Đã gửi file tới {recipient_name}!"})
    except Exception as e: return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# Các API và SocketIO khác giữ nguyên
# ...
@app.route('/api/verify/signature', methods=['POST'])
def verify_signature_route():
    if 'username' not in session: return jsonify({"error": "Phiên đăng nhập hết hạn"}), 401
    data = request.json; sender = User.query.filter_by(username=data.get('sender')).first()
    if not sender: return jsonify({"valid": False, "error": "Sender not found"})
    data_to_verify = crypto_utils.base64.b64decode(data['package']['iv']) + crypto_utils.base64.b64decode(data['package']['cipher'])
    is_valid = crypto_utils.verify_signature(data_to_verify, data['package']['sig'].encode(), sender.public_key_path)
    return jsonify({"valid": is_valid})

@app.route('/api/verify/hash', methods=['POST'])
def verify_hash_route():
    if 'username' not in session: return jsonify({"error": "Phiên đăng nhập hết hạn"}), 401
    data = request.json
    data_to_hash = crypto_utils.base64.b64decode(data['package']['iv']) + crypto_utils.base64.b64decode(data['package']['cipher'])
    is_valid = (crypto_utils.hash_sha512(data_to_hash) == data['package']['hash'])
    return jsonify({"valid": is_valid})

@app.route('/api/assemble', methods=['POST'])
def assemble_file():
    if 'username' not in session: return jsonify({"success": False, "error": "Phiên đăng nhập hết hạn"}), 401
    data = request.json
    recipient = User.query.filter_by(username=session['username']).first()
    try:
        session_key = crypto_utils.rsa_decrypt(data['encrypted_session_key'].encode(), recipient.private_key_path)
        if session_key is None: return jsonify({"success": False, "error": "Giải mã session key thất bại."})
        decrypted_parts = []
        for package in data['packages']:
            plaintext_bytes = crypto_utils.decrypt_3des(package['iv'].encode(), package['cipher'].encode(), session_key)
            if plaintext_bytes is None: return jsonify({"success": False, "error": "Giải mã một phần của file thất bại."})
            decrypted_parts.append(plaintext_bytes)
        full_file_content = b"".join(decrypted_parts)
        temp_filename = str(uuid.uuid4())
        temp_filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], temp_filename)
        with open(temp_filepath, "wb") as f:
            f.write(full_file_content)
        app.logger.info(f"User '{session['username']}' successfully assembled file '{data['original_filename']}'.") # Ghi log
        return jsonify({"success": True, "download_token": temp_filename, "original_filename": data['original_filename']})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

@app.route('/download/<token>')
def download_file(token):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        return send_from_directory(app.config['DOWNLOAD_FOLDER'], token, as_attachment=True)
    except FileNotFoundError: return "File not found", 404

@socketio.on('connect')
def handle_connect():
    if 'username' not in session: return False
    join_room(session['username'])
    if session['username'] in pending_files and pending_files[session['username']]:
        emit('receive_file', pending_files[session['username']].pop(0))

@socketio.on('disconnect')
def handle_disconnect():
    if 'username' in session: leave_room(session['username'])

@socketio.on('chat_message')
def handle_chat_message(data):
    if 'username' not in session: return
    recipient, message = data.get('recipient'), data.get('message')
    if not all([recipient, message]): return
    emit('new_chat_message', {'sender': session['username'], 'message': message}, room=recipient)
    
@socketio.on('send_nack')
def handle_nack(data):
    if 'username' not in session: return
    recipient, reason = data.get('recipient'), data.get('reason')
    if not all([recipient, reason]): return
    app.logger.warning(f"User '{session['username']}' sent a NACK to '{recipient}'. Reason: {reason}") # Ghi log
    emit('nack_received', {'from': session['username'], 'reason': reason}, room=recipient)

# --- RUN APP ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)