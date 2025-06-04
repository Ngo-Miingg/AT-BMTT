import socket
import json
import os
import shutil
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, send_file

app = Flask(__name__)
app.secret_key = 'your_server_web_secret_key_for_flask_session'

# Thư mục gốc nơi các file người dùng được lưu trữ bởi file_transfer_server.py
USERS_FILES_ROOT_DIR = 'users_encrypted_files' # Name kept, but files are not encrypted
os.makedirs(USERS_FILES_ROOT_DIR, exist_ok=True)

# File để lưu trữ thông tin chia sẻ file
SHARED_FILES_DB = 'shared_files.json'
# File để lưu trữ ánh xạ username <-> user_id
USER_ID_MAP_DB = 'user_id_map.json'

# --- Hàm trợ giúp để tải/lưu cơ sở dữ liệu (Copied from file_transfer_server.py for consistency, or use a shared lib) ---
# For simplicity, directly define here. In a larger app, this would be in a shared utility module.
def load_json_db_admin(filepath, default_data_type=dict):
    if not os.path.exists(filepath):
        return default_data_type() if callable(default_data_type) else default_data_type
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Lỗi đọc file JSON (admin): {filepath}. Trả về dữ liệu rỗng.")
        return default_data_type() if callable(default_data_type) else default_data_type

def save_json_db_admin(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@app.route('/')
def server_dashboard():
    server_status = "Không rõ" 
    connected_clients = "N/A" # Cannot get this easily without direct socket server integration
    total_files = 0
    total_size_bytes = 0 # Changed to total_size_bytes for clarity with formatting
    user_folders_data = [] # Renamed for clarity
    share_history_data = [] # Renamed for clarity

    try:
        current_shared_files_data = load_json_db_admin(SHARED_FILES_DB)
        current_user_id_map_data = load_json_db_admin(USER_ID_MAP_DB)

        for user_id_folder_name in os.listdir(USERS_FILES_ROOT_DIR):
            user_path = os.path.join(USERS_FILES_ROOT_DIR, user_id_folder_name)
            if os.path.isdir(user_path):
                files_in_folder_details = []
                folder_total_size_bytes = 0
                
                for item_name in os.listdir(user_path):
                    if item_name.endswith(".meta"): # Skip meta files in direct listing
                        continue
                    
                    item_path = os.path.join(user_path, item_name)
                    if os.path.isfile(item_path):
                        try:
                            size = os.path.getsize(item_path)
                            integrity_status = "unknown"
                            meta_file_path = item_path + ".meta"
                            if os.path.exists(meta_file_path):
                                try:
                                    with open(meta_file_path, 'r', encoding='utf-8') as mf:
                                        meta_content = json.load(mf)
                                        integrity_status = meta_content.get("status", "unknown")
                                except Exception as e_meta:
                                    print(f"Admin Dashboard: Error reading meta file {meta_file_path}: {e_meta}")

                            files_in_folder_details.append({
                                'name': item_name, 
                                'size': size, # Raw bytes
                                'integrity_status': integrity_status
                            })
                            folder_total_size_bytes += size
                        except OSError as e_file:
                            print(f"Admin Dashboard: Error getting file info for {item_path}: {e_file}")
                
                user_folders_data.append({
                    'user_id': user_id_folder_name,
                    'file_count': len(files_in_folder_details),
                    'total_size_bytes': folder_total_size_bytes, # Raw bytes
                    'files': files_in_folder_details
                })
                total_files += len(files_in_folder_details)
                total_size_bytes += folder_total_size_bytes
        
        server_status = "Đang hoạt động (File Storage)"

        for receiver_id, shared_files_list in current_shared_files_data.items():
            receiver_username = current_user_id_map_data.get(receiver_id, f"ID: {receiver_id}")
            for file_info_shared in shared_files_list:
                sender_id_shared = file_info_shared['owner_id']
                sender_username_shared = current_user_id_map_data.get(sender_id_shared, f"ID: {sender_id_shared}")
                filename_shared = file_info_shared['filename']
                share_history_data.append({
                    'sender_username': sender_username_shared,
                    'receiver_username': receiver_username,
                    'filename': filename_shared
                })
        
        share_history_data.sort(key=lambda x: (x['sender_username'], x['filename']))

    except FileNotFoundError:
        server_status = "Lỗi: Thư mục lưu trữ file hoặc file DB không tồn tại."
    except Exception as e:
        server_status = f"Lỗi truy cập dữ liệu: {e}"

    return render_template('server_dashboard.html',
                           server_status=server_status,
                           connected_clients=connected_clients,
                           total_files=total_files,
                           total_size_bytes=total_size_bytes, # Pass raw bytes
                           user_folders=user_folders_data, # Pass new var name
                           share_history=share_history_data) # Pass new var name

@app.route('/delete_user_data', methods=['POST'])
def delete_user_data():
    user_id_to_delete = request.form.get('user_id')
    if not user_id_to_delete:
        flash('ID người dùng không hợp lệ.', 'error')
        return redirect(url_for('server_dashboard'))

    user_folder_to_delete_path = os.path.join(USERS_FILES_ROOT_DIR, user_id_to_delete)
    if os.path.exists(user_folder_to_delete_path) and os.path.isdir(user_folder_to_delete_path):
        try:
            shutil.rmtree(user_folder_to_delete_path) # This will also delete .meta files inside
            
            shared_files_data_current = load_json_db_admin(SHARED_FILES_DB)
            user_id_map_data_current = load_json_db_admin(USER_ID_MAP_DB)
            db_changed = False

            # Remove shares given by this user and shares received by this user
            for receiver_id_key in list(shared_files_data_current.keys()):
                original_len = len(shared_files_data_current[receiver_id_key])
                shared_files_data_current[receiver_id_key] = [
                    sf for sf in shared_files_data_current[receiver_id_key] 
                    if sf['owner_id'] != user_id_to_delete # Remove shares given by this user
                ]
                if not shared_files_data_current[receiver_id_key]:
                    del shared_files_data_current[receiver_id_key]
                    db_changed = True
                elif len(shared_files_data_current[receiver_id_key]) != original_len:
                     db_changed = True
            
            if user_id_to_delete in shared_files_data_current: # Remove shares received by this user
                del shared_files_data_current[user_id_to_delete]
                db_changed = True
            
            if db_changed:
                save_json_db_admin(SHARED_FILES_DB, shared_files_data_current)

            if user_id_to_delete in user_id_map_data_current:
                del user_id_map_data_current[user_id_to_delete]
                save_json_db_admin(USER_ID_MAP_DB, user_id_map_data_current)

            flash(f'Đã xóa toàn bộ dữ liệu của người dùng ID: {user_id_to_delete}', 'success')
        except Exception as e_delete:
            flash(f'Lỗi khi xóa dữ liệu người dùng {user_id_to_delete}: {e_delete}', 'error')
    else:
        flash(f'Không tìm thấy thư mục của người dùng ID: {user_id_to_delete}', 'warning') # Changed to warning
    
    return redirect(url_for('server_dashboard'))

@app.route('/download_original_file/<user_id>/<filename>') # Renamed
def download_original_file(user_id, filename): # Renamed
    """Cho phép quản trị viên tải xuống file gốc của người dùng."""
    user_folder_path = os.path.join(USERS_FILES_ROOT_DIR, user_id)
    file_path_to_download = os.path.join(user_folder_path, filename)

    # Security check: Ensure the path is within the USERS_FILES_ROOT_DIR
    if not os.path.abspath(file_path_to_download).startswith(os.path.abspath(USERS_FILES_ROOT_DIR)):
        flash("Truy cập bị từ chối: Đường dẫn file không hợp lệ.", "error")
        return redirect(url_for('server_dashboard')) # Or return 403

    if os.path.exists(file_path_to_download) and os.path.isfile(file_path_to_download):
        # Ensure it's not a .meta file being requested directly via this route
        if filename.endswith(".meta"):
            flash("Không thể tải xuống file metadata trực tiếp.", "error")
            return redirect(url_for('server_dashboard'))
            
        return send_file(file_path_to_download, as_attachment=True, download_name=filename)
    else:
        flash(f"File '{filename}' không tồn tại cho người dùng ID {user_id}.", "error")
        return redirect(url_for('server_dashboard')) # Or return 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)