import socket
import json
import os
import shutil
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, send_file

app = Flask(__name__)
app.secret_key = 'your_server_web_secret_key_for_flask_session' # Đổi key này!

# Thư mục gốc nơi các file người dùng được lưu trữ bởi file_transfer_server.py
USERS_FILES_ROOT_DIR = 'users_encrypted_files'
os.makedirs(USERS_FILES_ROOT_DIR, exist_ok=True) # Đảm bảo thư mục tồn tại

# File để lưu trữ thông tin chia sẻ file (phải giống với file_transfer_server.py)
SHARED_FILES_DB = 'shared_files.json'
# File để lưu trữ ánh xạ username <-> user_id (phải giống với file_transfer_server.py)
USER_ID_MAP_DB = 'user_id_map.json'

# --- Hàm trợ giúp để tải/lưu cơ sở dữ liệu ---
def load_shared_files_db():
    """Tải cơ sở dữ liệu file chia sẻ từ file JSON."""
    if not os.path.exists(SHARED_FILES_DB):
        return {}
    try:
        with open(SHARED_FILES_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Lỗi đọc file {SHARED_FILES_DB}. Trả về dữ liệu rỗng.")
        return {}

def save_shared_files_db(data):
    """Lưu cơ sở dữ liệu file chia sẻ vào file JSON."""
    with open(SHARED_FILES_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_user_id_map():
    """Tải ánh xạ username <-> user_id từ file JSON."""
    if not os.path.exists(USER_ID_MAP_DB):
        return {}
    try:
        with open(USER_ID_MAP_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Lỗi đọc file {USER_ID_MAP_DB}. Trả về dữ liệu rỗng.")
        return {}

def save_user_id_map(data):
    """Lưu ánh xạ username <-> user_id vào file JSON."""
    with open(USER_ID_MAP_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Khởi tạo hoặc tải dữ liệu khi server khởi động
# Các biến này sẽ được truy cập và sửa đổi trong các hàm route
# (Mặc dù không cần 'global' ở đây vì chúng được truy cập thông qua hàm load/save)
SHARED_FILES_DATA = load_shared_files_db()
USER_ID_MAP_DATA = load_user_id_map()


@app.route('/')
def server_dashboard():
    """Hiển thị bảng điều khiển server với thông tin lưu trữ, người dùng và lịch sử chia sẻ."""
    server_status = "Không rõ" 
    connected_clients = "N/A" # Không thể lấy trực tiếp qua socket hiện tại
    total_files = 0
    total_size = 0
    user_folders = []
    share_history = []

    try:
        # Tải lại dữ liệu chia sẻ và ánh xạ người dùng để đảm bảo luôn mới nhất
        # (Trong môi trường đa luồng/đa tiến trình, cần cơ chế khóa để tránh race condition
        # nhưng với Flask đơn giản, việc load lại mỗi request là chấp nhận được cho DB file nhỏ)
        current_shared_files_data = load_shared_files_db()
        current_user_id_map_data = load_user_id_map()

        # Lấy danh sách các thư mục người dùng và số lượng file/kích thước
        for user_id_folder in os.listdir(USERS_FILES_ROOT_DIR):
            user_path = os.path.join(USERS_FILES_ROOT_DIR, user_id_folder)
            if os.path.isdir(user_path):
                files_in_folder = []
                folder_size = 0
                for root, _, files in os.walk(user_path):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        try:
                            size = os.path.getsize(file_path)
                            files_in_folder.append({'name': file_name, 'size': size})
                            folder_size += size
                        except OSError as e:
                            print(f"Error getting file info for {file_path}: {e}")
                
                user_folders.append({
                    'user_id': user_id_folder,
                    'file_count': len(files_in_folder),
                    'total_size': folder_size,
                    'files': files_in_folder
                })
                total_files += len(files_in_folder)
                total_size += folder_size
        server_status = "Đang hoạt động (Socket Server)" # Giả định nếu thư mục tồn tại và có thể truy cập

        # Xây dựng lịch sử chia sẻ
        for receiver_id, shared_files_list in current_shared_files_data.items():
            receiver_username = current_user_id_map_data.get(receiver_id, f"ID: {receiver_id}")
            for file_info in shared_files_list:
                sender_id = file_info['owner_id']
                sender_username = current_user_id_map_data.get(sender_id, f"ID: {sender_id}")
                filename = file_info['filename']
                share_history.append({
                    'sender_username': sender_username,
                    'receiver_username': receiver_username,
                    'filename': filename
                })
        
        # Sắp xếp lịch sử chia sẻ (ví dụ: theo tên file hoặc người gửi/nhận)
        share_history.sort(key=lambda x: x['filename']) # Sắp xếp theo tên file

    except FileNotFoundError:
        server_status = "Lỗi: Thư mục lưu trữ file hoặc file DB không tồn tại. Đảm bảo 'file_transfer_server.py' đã chạy ít nhất một lần."
        print(f"Error: {USERS_FILES_ROOT_DIR} or DB files not found.")
    except Exception as e:
        server_status = f"Lỗi truy cập dữ liệu: {e}"
        print(f"Error accessing file storage or DB: {e}")

    return render_template('server_dashboard.html',
                           server_status=server_status,
                           connected_clients=connected_clients,
                           total_files=total_files,
                           total_size=total_size,
                           user_folders=user_folders,
                           share_history=share_history) # Truyền lịch sử chia sẻ

@app.route('/delete_user_data', methods=['POST'])
def delete_user_data():
    """Xóa toàn bộ dữ liệu của một người dùng trên server."""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('ID người dùng không hợp lệ.', 'error')
        return redirect(url_for('server_dashboard'))

    user_folder_path = os.path.join(USERS_FILES_ROOT_DIR, user_id)
    if os.path.exists(user_folder_path):
        try:
            shutil.rmtree(user_folder_path)
            
            # Tải lại dữ liệu để đảm bảo cập nhật chính xác trước khi sửa đổi
            shared_files_data = load_shared_files_db()
            user_id_map_data = load_user_id_map()

            # Xóa các file mà người dùng này đã chia sẻ cho người khác
            for receiver_id in list(shared_files_data.keys()):
                shared_files_data[receiver_id] = [
                    sf for sf in shared_files_data[receiver_id] 
                    if sf['owner_id'] != user_id
                ]
                if not shared_files_data[receiver_id]:
                    del shared_files_data[receiver_id]
            
            # Xóa các bản ghi mà người dùng này được chia sẻ
            if user_id in shared_files_data:
                del shared_files_data[user_id]
            
            save_shared_files_db(shared_files_data) # Gọi hàm save_shared_files_db

            # Xóa người dùng khỏi ánh xạ user_id_map
            if user_id in user_id_map_data:
                del user_id_map_data[user_id]
                save_user_id_map(user_id_map_data) # Gọi hàm save_user_id_map

            flash(f'Đã xóa toàn bộ dữ liệu của người dùng ID: {user_id}', 'success')
        except Exception as e:
            flash(f'Lỗi khi xóa dữ liệu người dùng {user_id}: {e}', 'error')
    else:
        flash(f'Không tìm thấy thư mục của người dùng ID: {user_id}', 'error')
    
    return redirect(url_for('server_dashboard'))

@app.route('/download_encrypted/<user_id>/<filename>')
def download_encrypted_file(user_id, filename):
    """Cho phép quản trị viên tải xuống file đã mã hóa của người dùng."""
    user_folder_path = os.path.join(USERS_FILES_ROOT_DIR, user_id)
    file_path = os.path.join(user_folder_path, filename)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        if not os.path.abspath(file_path).startswith(os.path.abspath(user_folder_path)):
            return "Truy cập bị từ chối.", 403
        
        return send_file(file_path, as_attachment=True, download_name=filename)
    else:
        return "File không tồn tại.", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
