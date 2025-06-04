import socket
import os
import json
import threading
import hashlib # Added for SHA-256

# --- Cấu hình Socket Server ---
HOST = '0.0.0.0'
PORT = 65432
BUFFER_SIZE = 4096 # Ensure this is used for chunked hashing

# Thư mục gốc để lưu file của các người dùng (Tên thư mục vẫn giữ nguyên)
USERS_FILES_ROOT_DIR = 'users_encrypted_files' # Files are no longer encrypted but dir name is kept
os.makedirs(USERS_FILES_ROOT_DIR, exist_ok=True)

# File để lưu trữ thông tin chia sẻ file
SHARED_FILES_DB = 'shared_files.json'
# File để lưu trữ ánh xạ username <-> user_id
USER_ID_MAP_DB = 'user_id_map.json'

# --- DB Lock ---
# For simplicity in this example, we'll use a single lock for DB operations.
# In a high-concurrency production environment, more granular locking or a proper DB system would be better.
db_lock = threading.Lock()

def load_json_db(filepath, default_data_type=dict):
    """Tải dữ liệu từ file JSON một cách an toàn."""
    with db_lock:
        if not os.path.exists(filepath):
            return default_data_type() if callable(default_data_type) else default_data_type
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Lỗi đọc file JSON: {filepath}. Trả về dữ liệu mặc định.")
            return default_data_type() if callable(default_data_type) else default_data_type

def save_json_db(filepath, data):
    """Lưu dữ liệu vào file JSON một cách an toàn."""
    with db_lock:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# Khởi tạo hoặc tải dữ liệu khi server khởi động
SHARED_FILES_DATA = load_json_db(SHARED_FILES_DB, default_data_type=dict)
USER_ID_MAP_DATA = load_json_db(USER_ID_MAP_DB, default_data_type=dict)

# Hàm trợ giúp để gửi/nhận dữ liệu ( giữ nguyên)
def send_bytes_with_length_prefix(conn, data):
    conn.sendall(len(data).to_bytes(8, 'big'))
    conn.sendall(data)

def recv_bytes_with_length_prefix(conn):
    len_bytes = conn.recv(8)
    if not len_bytes: return b""
    data_len = int.from_bytes(len_bytes, 'big')
    data = b""
    while len(data) < data_len:
        packet = conn.recv(min(BUFFER_SIZE, data_len - len(data)))
        if not packet:
            print("[SERVER] Client closed connection unexpectedly while receiving data.")
            return b""
        data += packet
    return data

def calculate_sha256(filepath):
    """Tính toán SHA-256 hash của một file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(BUFFER_SIZE), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Hàm xử lý client
def handle_client(conn, addr):
    global SHARED_FILES_DATA, USER_ID_MAP_DATA # Re-load within function if multi-threading issues arise without proper locking
    print(f"✅ [SERVER] Connected by {addr}")
    try:
        command_bytes = recv_bytes_with_length_prefix(conn)
        if not command_bytes:
            print(f"🔌 [SERVER] Client {addr} did not send a command.")
            return
        command = command_bytes.decode('utf-8')

        user_id_bytes = recv_bytes_with_length_prefix(conn)
        if not user_id_bytes:
            print(f"🔌 [SERVER] Client {addr} did not send user_id for command {command}.")
            return
        user_id = user_id_bytes.decode('utf-8')


        if command == "UPLOAD_USER_FILE":
            file_name_bytes = recv_bytes_with_length_prefix(conn)
            file_data = recv_bytes_with_length_prefix(conn)
            client_file_hash_bytes = recv_bytes_with_length_prefix(conn)

            if not (file_name_bytes and file_data and client_file_hash_bytes):
                print(f"❌ [SERVER] Incomplete UPLOAD_USER_FILE data from {addr}.")
                # Optionally send an error back to client if protocol allows for it here
                return

            file_name = file_name_bytes.decode('utf-8')
            client_file_hash = client_file_hash_bytes.decode('utf-8')
            
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            os.makedirs(user_dir, exist_ok=True)
            file_path = os.path.join(user_dir, file_name)
            meta_file_path = file_path + ".meta"

            try:
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                server_calculated_hash = calculate_sha256(file_path)
                
                meta_data = {"client_hash": client_file_hash, "filename": file_name}
                if server_calculated_hash == client_file_hash:
                    meta_data["status"] = "verified"
                    print(f"📦 [SERVER] Received file '{file_name}' from user {user_id}. Integrity: VERIFIED.")
                    send_bytes_with_length_prefix(conn, b"UPLOAD_SUCCESS_VERIFIED")
                    send_bytes_with_length_prefix(conn, b"File uploaded and integrity verified.")
                else:
                    meta_data["status"] = "failed_integrity_check"
                    print(f"❌ [SERVER] Received file '{file_name}' from user {user_id}. Integrity: FAILED.")
                    send_bytes_with_length_prefix(conn, b"UPLOAD_FAILED_INTEGRITY_CHECK")
                    send_bytes_with_length_prefix(conn, b"File integrity check failed.")

                with open(meta_file_path, 'w', encoding='utf-8') as mf:
                    json.dump(meta_data, mf, indent=4)

            except Exception as e:
                print(f"❌ [SERVER] Error saving file '{file_name}' for user {user_id}: {e}")
                send_bytes_with_length_prefix(conn, b"UPLOAD_FAILED_SERVER_ERROR")
                send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))

        elif command == "LIST_USER_FILES":
            user_files = []
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            current_user_id_map = load_json_db(USER_ID_MAP_DB, default_data_type=dict) # Load fresh map
            current_username = current_user_id_map.get(user_id, f"ID: {user_id}")

            if os.path.exists(user_dir):
                for f_name in os.listdir(user_dir):
                    if f_name.endswith(".meta"): # Skip meta files in direct listing
                        continue
                    
                    f_path = os.path.join(user_dir, f_name)
                    if os.path.isfile(f_path):
                        integrity_status = "unknown"
                        meta_path = f_path + ".meta"
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, 'r', encoding='utf-8') as mf:
                                    meta_data = json.load(mf)
                                    integrity_status = meta_data.get("status", "unknown")
                            except Exception as e_meta:
                                print(f"⚠️ [SERVER] Error reading meta file {meta_path}: {e_meta}")
                        
                        user_files.append({
                            'name': f_name,
                            'size': os.path.getsize(f_path),
                            'owner_id': user_id,
                            'owner_username': current_username,
                            'is_shared': False,
                            'integrity_status': integrity_status
                        })
            
            current_shared_files_data = load_json_db(SHARED_FILES_DB, default_data_type=dict) # Load fresh shared data
            shared_with_me = current_shared_files_data.get(user_id, [])
            for shared_file_info in shared_with_me:
                owner_id_shared = shared_file_info['owner_id']
                filename_shared = shared_file_info['filename']
                owner_dir_shared = os.path.join(USERS_FILES_ROOT_DIR, owner_id_shared)
                actual_file_path_shared = os.path.join(owner_dir_shared, filename_shared)

                if os.path.exists(actual_file_path_shared) and os.path.isfile(actual_file_path_shared):
                    owner_username_shared = current_user_id_map.get(owner_id_shared, f"ID: {owner_id_shared}")
                    integrity_status_shared = "unknown"
                    meta_path_shared = actual_file_path_shared + ".meta"
                    if os.path.exists(meta_path_shared):
                        try:
                            with open(meta_path_shared, 'r', encoding='utf-8') as mf_s:
                                meta_data_s = json.load(mf_s)
                                integrity_status_shared = meta_data_s.get("status", "unknown")
                        except Exception as e_meta_s:
                             print(f"⚠️ [SERVER] Error reading meta file {meta_path_shared}: {e_meta_s}")

                    user_files.append({
                        'name': filename_shared,
                        'size': os.path.getsize(actual_file_path_shared),
                        'owner_id': owner_id_shared,
                        'owner_username': owner_username_shared,
                        'is_shared': True,
                        'integrity_status': integrity_status_shared
                    })
                else:
                    print(f"⚠️ [SERVER] Shared file not found: {actual_file_path_shared} for user {user_id}")
            
            send_bytes_with_length_prefix(conn, b"LIST_SUCCESS")
            send_bytes_with_length_prefix(conn, json.dumps(user_files, ensure_ascii=False).encode('utf-8'))
            print(f"📋 [SERVER] Sent file list to user {user_id}")


        elif command == "DOWNLOAD_USER_FILE":
            file_name_to_download_bytes = recv_bytes_with_length_prefix(conn)
            owner_id_if_shared_bytes = recv_bytes_with_length_prefix(conn)

            if not (file_name_to_download_bytes and owner_id_if_shared_bytes):
                print(f"❌ [SERVER] Incomplete DOWNLOAD_USER_FILE data from {addr}.")
                return

            file_name_to_download = file_name_to_download_bytes.decode('utf-8')
            # owner_id_if_shared is the ID of the actual owner of the file.
            # user_id is the ID of the user requesting the download.
            actual_owner_id = owner_id_if_shared_bytes.decode('utf-8') 


            file_path = os.path.join(USERS_FILES_ROOT_DIR, actual_owner_id, file_name_to_download)

            if os.path.exists(file_path) and os.path.isfile(file_path):
                has_permission = False
                if actual_owner_id == user_id: # User is downloading their own file
                    has_permission = True
                else: # User is downloading a file shared with them
                    current_shared_files_data = load_json_db(SHARED_FILES_DB, default_data_type=dict)
                    shared_with_current_user = current_shared_files_data.get(user_id, [])
                    for sf in shared_with_current_user:
                        if sf['owner_id'] == actual_owner_id and sf['filename'] == file_name_to_download:
                            has_permission = True
                            break
                
                if has_permission:
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_SUCCESS")
                    send_bytes_with_length_prefix(conn, file_data)
                    print(f"⬇️ [SERVER] Sent file '{file_name_to_download}' to user {user_id} (Owner: {actual_owner_id}).")
                else:
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_FAILED_PERMISSION")
                    send_bytes_with_length_prefix(conn, b"Permission denied to access this file.")
                    print(f"🚫 [SERVER] User {user_id} permission denied for file '{file_name_to_download}' (Owner: {actual_owner_id}).")
            else:
                send_bytes_with_length_prefix(conn, b"DOWNLOAD_FAILED_NOT_FOUND")
                send_bytes_with_length_prefix(conn, b"File not found or has been deleted.")
                print(f"❌ [SERVER] Download request for '{file_name_to_download}' by user {user_id}, but file not found.")

        elif command == "DELETE_USER_FILE":
            file_name_to_delete_bytes = recv_bytes_with_length_prefix(conn)
            if not file_name_to_delete_bytes:
                print(f"❌ [SERVER] Incomplete DELETE_USER_FILE data from {addr}.")
                return
            file_name_to_delete = file_name_to_delete_bytes.decode('utf-8')
            
            # Users can only delete their own files. user_id is the owner.
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            file_path = os.path.join(user_dir, file_name_to_delete)
            meta_file_path = file_path + ".meta"

            if os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    if os.path.exists(meta_file_path):
                        os.remove(meta_file_path)
                    
                    # Remove from shared entries if this user owned the deleted file
                    current_shared_files_data = load_json_db(SHARED_FILES_DB, default_data_type=dict)
                    changed_shared_db = False
                    for receiver_id_key in list(current_shared_files_data.keys()):
                        original_len = len(current_shared_files_data[receiver_id_key])
                        current_shared_files_data[receiver_id_key] = [
                            sf for sf in current_shared_files_data[receiver_id_key] 
                            if not (sf['owner_id'] == user_id and sf['filename'] == file_name_to_delete)
                        ]
                        if not current_shared_files_data[receiver_id_key]:
                            del current_shared_files_data[receiver_id_key]
                            changed_shared_db = True
                        elif len(current_shared_files_data[receiver_id_key]) != original_len:
                            changed_shared_db = True
                    
                    if changed_shared_db:
                         save_json_db(SHARED_FILES_DB, current_shared_files_data)


                    print(f"🗑️ [SERVER] Deleted file '{file_name_to_delete}' for user {user_id}.")
                    send_bytes_with_length_prefix(conn, b"DELETE_SUCCESS")
                    send_bytes_with_length_prefix(conn, b"File deleted successfully.")
                except Exception as e:
                    print(f"❌ [SERVER] Error deleting file '{file_name_to_delete}' for user {user_id}: {e}")
                    send_bytes_with_length_prefix(conn, b"DELETE_FAILED")
                    send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))
            else:
                print(f"⚠️ [SERVER] Delete request for '{file_name_to_delete}' by {user_id}, but file not found.")
                send_bytes_with_length_prefix(conn, b"DELETE_FAILED_NOT_FOUND")
                send_bytes_with_length_prefix(conn, b"File not found to delete.")
        
        elif command == "SHARE_FILE":
            # sender_id is user_id
            receiver_username_bytes = recv_bytes_with_length_prefix(conn)
            file_name_to_share_bytes = recv_bytes_with_length_prefix(conn)

            if not (receiver_username_bytes and file_name_to_share_bytes):
                print(f"❌ [SERVER] Incomplete SHARE_FILE data from {addr}.")
                return

            receiver_username = receiver_username_bytes.decode('utf-8')
            file_name_to_share = file_name_to_share_bytes.decode('utf-8')

            current_user_id_map = load_json_db(USER_ID_MAP_DB, default_data_type=dict)
            receiver_id = None
            for uid, uname in current_user_id_map.items():
                if uname == receiver_username:
                    receiver_id = uid
                    break
            
            if receiver_id is None:
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED_NO_RECEIVER")
                send_bytes_with_length_prefix(conn, b"Receiver user not found.")
                return

            if user_id == receiver_id:
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED_SELF_SHARE")
                send_bytes_with_length_prefix(conn, b"Cannot share a file with yourself.")
                return

            sender_file_path = os.path.join(USERS_FILES_ROOT_DIR, user_id, file_name_to_share)
            if not (os.path.exists(sender_file_path) and os.path.isfile(sender_file_path)):
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED_FILE_NOT_FOUND")
                send_bytes_with_length_prefix(conn, b"File to share not found in your directory.")
                return
            
            current_shared_files_data = load_json_db(SHARED_FILES_DB, default_data_type=dict)
            shared_entry = {"owner_id": user_id, "filename": file_name_to_share} # owner_id is the sender
            
            if receiver_id not in current_shared_files_data:
                current_shared_files_data[receiver_id] = []
            
            if shared_entry not in current_shared_files_data[receiver_id]:
                current_shared_files_data[receiver_id].append(shared_entry)
                save_json_db(SHARED_FILES_DB, current_shared_files_data)
                print(f"🤝 [SERVER] Shared file '{file_name_to_share}' from {user_id} to {receiver_id} ({receiver_username}).")
                send_bytes_with_length_prefix(conn, b"SHARE_SUCCESS")
                send_bytes_with_length_prefix(conn, f"File '{file_name_to_share}' shared with '{receiver_username}'.".encode('utf-8'))
            else:
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED_ALREADY_SHARED")
                send_bytes_with_length_prefix(conn, b"This file is already shared with the user.")

        elif command == "REGISTER_USERNAME":
            # user_id is already received
            username_bytes = recv_bytes_with_length_prefix(conn)
            if not username_bytes:
                print(f"❌ [SERVER] Incomplete REGISTER_USERNAME data from {addr}.")
                return
            username = username_bytes.decode('utf-8')

            current_user_id_map = load_json_db(USER_ID_MAP_DB, default_data_type=dict)
            if user_id not in current_user_id_map or current_user_id_map[user_id] != username:
                current_user_id_map[user_id] = username
                save_json_db(USER_ID_MAP_DB, current_user_id_map)
                print(f"📝 [SERVER] UserID map updated: UserID '{user_id}' -> Username '{username}'.")
            send_bytes_with_length_prefix(conn, b"USERNAME_MAP_SUCCESS")
            send_bytes_with_length_prefix(conn, b"Username mapping updated successfully.")

        elif command == "LIST_ALL_USERNAMES":
            # user_id is the requester, not used directly for listing all.
            current_user_id_map = load_json_db(USER_ID_MAP_DB, default_data_type=dict)
            usernames_list = list(current_user_id_map.values())
            send_bytes_with_length_prefix(conn, b"USERNAME_LIST_SUCCESS")
            send_bytes_with_length_prefix(conn, json.dumps(usernames_list, ensure_ascii=False).encode('utf-8'))
            print(f"👥 [SERVER] Sent list of all usernames to user {user_id}.")

        else:
            print(f"❓ [SERVER] Invalid command from {addr}: {command}")
            send_bytes_with_length_prefix(conn, b"INVALID_COMMAND")
            send_bytes_with_length_prefix(conn, b"Invalid command received.")

    except ConnectionResetError:
        print(f"🔌 [SERVER] Client {addr} disconnected abruptly.")
    except UnicodeDecodeError as ude:
        print(f"❌ [SERVER] Unicode decode error processing data from {addr}: {ude}. Client might be sending malformed data.")
    except Exception as e:
        print(f"❌ [SERVER] Error handling client {addr}: {e}")
        try:
            # Try to inform the client about a generic server error if connection is still alive
            send_bytes_with_length_prefix(conn, b"SERVER_PROCESSING_ERROR")
            send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))
        except:
            pass # If sending error fails, just log and close
    finally:
        conn.close()
        print(f"🚪 [SERVER] Connection closed with {addr}")

def start_server():
    # Ensure DB files exist before starting, load_json_db handles creation if they don't
    if not os.path.exists(SHARED_FILES_DB):
        save_json_db(SHARED_FILES_DB, {})
    if not os.path.exists(USER_ID_MAP_DB):
        save_json_db(USER_ID_MAP_DB, {})

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"🚀 [SERVER] Listening for connections on {HOST}:{PORT}...")
        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.daemon = True # Allow main program to exit even if threads are running
            client_thread.start()

if __name__ == '__main__':
    start_server()