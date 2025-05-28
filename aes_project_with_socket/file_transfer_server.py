import socket
import os
import json
import threading
import glob

# --- Cấu hình Socket Server ---
HOST = '0.0.0.0'  # Lắng nghe trên tất cả các giao diện mạng
PORT = 65432       # Cổng mặc định
BUFFER_SIZE = 4096

# Thư mục gốc để lưu file của các người dùng
USERS_FILES_ROOT_DIR = 'users_encrypted_files'
os.makedirs(USERS_FILES_ROOT_DIR, exist_ok=True)

# File để lưu trữ thông tin chia sẻ file
SHARED_FILES_DB = 'shared_files.json'
# File để lưu trữ ánh xạ username <-> user_id (để tìm user_id của người nhận)
USER_ID_MAP_DB = 'user_id_map.json'

def load_shared_files_db():
    """Tải cơ sở dữ liệu file chia sẻ từ file JSON."""
    if not os.path.exists(SHARED_FILES_DB):
        return {}
    with open(SHARED_FILES_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_shared_files_db(data):
    """Lưu cơ sở dữ liệu file chia sẻ vào file JSON."""
    with open(SHARED_FILES_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_user_id_map():
    """Tải ánh xạ username <-> user_id từ file JSON."""
    if not os.path.exists(USER_ID_MAP_DB):
        return {}
    with open(USER_ID_MAP_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_user_id_map(data):
    """Lưu ánh xạ username <-> user_id vào file JSON."""
    with open(USER_ID_MAP_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Khởi tạo hoặc tải dữ liệu khi server khởi động
SHARED_FILES_DATA = load_shared_files_db()
USER_ID_MAP_DATA = load_user_id_map()

# Hàm trợ giúp để gửi/nhận dữ liệu
def send_bytes_with_length_prefix(conn, data):
    conn.sendall(len(data).to_bytes(8, 'big'))
    conn.sendall(data)

def recv_bytes_with_length_prefix(conn):
    len_bytes = conn.recv(8)
    if not len_bytes:
        return b""
    data_len = int.from_bytes(len_bytes, 'big')

    data = b""
    while len(data) < data_len:
        packet = conn.recv(min(BUFFER_SIZE, data_len - len(data)))
        if not packet:
            print("[SERVER] Client closed connection unexpectedly while receiving data.")
            return b""
        data += packet
    return data

# Hàm xử lý client
def handle_client(conn, addr):
    global SHARED_FILES_DATA, USER_ID_MAP_DATA
    print(f"✅ [SERVER] Connected by {addr}")
    try:
        command = recv_bytes_with_length_prefix(conn).decode('utf-8')
        user_id = recv_bytes_with_length_prefix(conn).decode('utf-8')

        if command == "UPLOAD_USER_FILE":
            file_name = recv_bytes_with_length_prefix(conn).decode('utf-8')
            file_data = recv_bytes_with_length_prefix(conn)
            
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            os.makedirs(user_dir, exist_ok=True)
            file_path = os.path.join(user_dir, file_name)

            try:
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                print(f"📦 [SERVER] Đã nhận file '{file_name}' từ người dùng {user_id}")
                send_bytes_with_length_prefix(conn, b"UPLOAD_SUCCESS")
                send_bytes_with_length_prefix(conn, b"File da duoc tai len thanh cong.")
            except Exception as e:
                print(f"❌ [SERVER] Lỗi lưu file '{file_name}' cho người dùng {user_id}: {e}")
                send_bytes_with_length_prefix(conn, b"UPLOAD_FAILED")
                send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))

        elif command == "LIST_USER_FILES":
            user_files = []
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            
            # Lấy username của người dùng hiện tại
            current_username = USER_ID_MAP_DATA.get(user_id, "Unknown User")

            if os.path.exists(user_dir):
                for f_name in os.listdir(user_dir):
                    f_path = os.path.join(user_dir, f_name)
                    if os.path.isfile(f_path):
                        user_files.append({
                            'name': f_name,
                            'size': os.path.getsize(f_path),
                            'owner_id': user_id,
                            'owner_username': current_username, # Thêm owner_username
                            'is_shared': False
                        })
            
            # Thêm các file được chia sẻ với người dùng này
            shared_with_me = SHARED_FILES_DATA.get(user_id, [])
            for shared_file_info in shared_with_me:
                owner_dir = os.path.join(USERS_FILES_ROOT_DIR, shared_file_info['owner_id'])
                actual_file_path = os.path.join(owner_dir, shared_file_info['filename'])
                if os.path.exists(actual_file_path) and os.path.isfile(actual_file_path):
                    # Lấy username của chủ sở hữu thực sự
                    owner_username = USER_ID_MAP_DATA.get(shared_file_info['owner_id'], "Unknown User")
                    user_files.append({
                        'name': shared_file_info['filename'],
                        'size': os.path.getsize(actual_file_path),
                        'owner_id': shared_file_info['owner_id'],
                        'owner_username': owner_username, # Thêm owner_username cho file chia sẻ
                        'is_shared': True
                    })
                else:
                    print(f"⚠️ [SERVER] File được chia sẻ không tồn tại: {actual_file_path}")
            
            send_bytes_with_length_prefix(conn, b"LIST_SUCCESS")
            send_bytes_with_length_prefix(conn, json.dumps(user_files, ensure_ascii=False).encode('utf-8'))
            print(f"📋 [SERVER] Đã gửi danh sách file cho người dùng {user_id}")


        elif command == "DOWNLOAD_USER_FILE":
            file_name_to_download = recv_bytes_with_length_prefix(conn).decode('utf-8')
            owner_id_if_shared = recv_bytes_with_length_prefix(conn).decode('utf-8')

            target_user_id = user_id
            actual_owner_id = owner_id_if_shared if owner_id_if_shared != "N/A" else target_user_id

            file_path = os.path.join(USERS_FILES_ROOT_DIR, actual_owner_id, file_name_to_download)

            if os.path.exists(file_path) and os.path.isfile(file_path):
                has_permission = False
                if actual_owner_id == target_user_id:
                    has_permission = True
                else:
                    shared_with_current_user = SHARED_FILES_DATA.get(target_user_id, [])
                    for sf in shared_with_current_user:
                        if sf['owner_id'] == actual_owner_id and sf['filename'] == file_name_to_download:
                            has_permission = True
                            break
                
                if has_permission:
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_SUCCESS")
                    send_bytes_with_length_prefix(conn, file_data)
                    print(f"⬇️ [SERVER] Đã gửi file '{file_name_to_download}' cho người dùng {user_id} (chủ sở hữu: {actual_owner_id}).")
                else:
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_FAILED")
                    send_bytes_with_length_prefix(conn, b"Khong co quyen truy cap file nay.")
                    print(f"🚫 [SERVER] Người dùng {user_id} không có quyền tải file '{file_name_to_download}' (chủ sở hữu: {actual_owner_id}).")
            else:
                send_bytes_with_length_prefix(conn, b"DOWNLOAD_FAILED")
                send_bytes_with_length_prefix(conn, b"File khong ton tai hoac da bi xoa.")
                print(f"❌ [SERVER] Yêu cầu tải file '{file_name_to_download}' từ người dùng {user_id} nhưng file không tồn tại.")

        elif command == "DELETE_USER_FILE":
            file_name_to_delete = recv_bytes_with_length_prefix(conn).decode('utf-8')
            
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            file_path = os.path.join(user_dir, file_name_to_delete)

            if os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    
                    for receiver_id in list(SHARED_FILES_DATA.keys()):
                        SHARED_FILES_DATA[receiver_id] = [
                            sf for sf in SHARED_FILES_DATA[receiver_id] 
                            if not (sf['owner_id'] == user_id and sf['filename'] == file_name_to_delete)
                        ]
                        if not SHARED_FILES_DATA[receiver_id]:
                            del SHARED_FILES_DATA[receiver_id]
                    save_shared_files_db(SHARED_FILES_DATA)

                    print(f"🗑️ [SERVER] Đã xóa file '{file_name_to_delete}' của người dùng {user_id}.")
                    send_bytes_with_length_prefix(conn, b"DELETE_SUCCESS")
                    send_bytes_with_length_prefix(conn, b"File da duoc xoa thanh cong.")
                except Exception as e:
                    print(f"❌ [SERVER] Lỗi xóa file '{file_name_to_delete}' của người dùng {user_id}: {e}")
                    send_bytes_with_length_prefix(conn, b"DELETE_FAILED")
                    send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))
            else:
                print(f"⚠️ [SERVER] Yêu cầu xóa file '{file_name_to_delete}' từ {user_id} nhưng file không tồn tại.")
                send_bytes_with_length_prefix(conn, b"DELETE_FAILED")
                send_bytes_with_length_prefix(conn, b"File khong ton tai de xoa.")
        
        elif command == "SHARE_FILE":
            sender_id = user_id
            receiver_username = recv_bytes_with_length_prefix(conn).decode('utf-8')
            file_name_to_share = recv_bytes_with_length_prefix(conn).decode('utf-8')

            receiver_id = None
            for uid, uname in USER_ID_MAP_DATA.items():
                if uname == receiver_username:
                    receiver_id = uid
                    break
            
            if receiver_id is None:
                print(f"❌ [SERVER] Không tìm thấy người dùng nhận '{receiver_username}'.")
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED")
                send_bytes_with_length_prefix(conn, b"Nguoi dung nhan khong ton tai.")
                return

            if sender_id == receiver_id:
                print(f"❌ [SERVER] Người gửi và người nhận là một: {sender_id}.")
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED")
                send_bytes_with_length_prefix(conn, b"Khong the tu chia se file cho ban than.")
                return

            sender_file_path = os.path.join(USERS_FILES_ROOT_DIR, sender_id, file_name_to_share)
            if not (os.path.exists(sender_file_path) and os.path.isfile(sender_file_path)):
                print(f"❌ [SERVER] File '{file_name_to_share}' không tồn tại trong thư mục của người gửi {sender_id}.")
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED")
                send_bytes_with_length_prefix(conn, b"File khong ton tai de chia se.")
                return
            
            shared_entry = {"owner_id": sender_id, "filename": file_name_to_share}
            
            if receiver_id not in SHARED_FILES_DATA:
                SHARED_FILES_DATA[receiver_id] = []
            
            if shared_entry not in SHARED_FILES_DATA[receiver_id]:
                SHARED_FILES_DATA[receiver_id].append(shared_entry)
                save_shared_files_db(SHARED_FILES_DATA)
                print(f"🤝 [SERVER] Đã chia sẻ file '{file_name_to_share}' từ {sender_id} tới {receiver_id}.")
                send_bytes_with_length_prefix(conn, b"SHARE_SUCCESS")
                send_bytes_with_length_prefix(conn, f"Da chia se file '{file_name_to_share}' voi nguoi dung '{receiver_username}' thanh cong.".encode('utf-8'))
            else:
                print(f"⚠️ [SERVER] File '{file_name_to_share}' đã được chia sẻ với người dùng '{receiver_username}' trước đó.")
                send_bytes_with_length_prefix(conn, b"SHARE_FAILED")
                send_bytes_with_length_prefix(conn, b"File nay da duoc chia se voi nguoi dung do.")

        elif command == "REGISTER_USERNAME":
            username = recv_bytes_with_length_prefix(conn).decode('utf-8')
            if user_id not in USER_ID_MAP_DATA or USER_ID_MAP_DATA[user_id] != username:
                USER_ID_MAP_DATA[user_id] = username
                save_user_id_map(USER_ID_MAP_DATA)
                print(f"📝 [SERVER] Đã cập nhật ánh xạ: UserID '{user_id}' -> Username '{username}'.")
            send_bytes_with_length_prefix(conn, b"USERNAME_MAP_SUCCESS")
            send_bytes_with_length_prefix(conn, b"Cap nhat username thanh cong.")

        elif command == "LIST_ALL_USERNAMES":
            usernames_list = list(USER_ID_MAP_DATA.values())
            send_bytes_with_length_prefix(conn, b"USERNAME_LIST_SUCCESS")
            send_bytes_with_length_prefix(conn, json.dumps(usernames_list, ensure_ascii=False).encode('utf-8'))
            print(f"👥 [SERVER] Đã gửi danh sách usernames cho người dùng {user_id}.")

        else:
            print(f"❓ [SERVER] Lệnh không hợp lệ: {command}")
            send_bytes_with_length_prefix(conn, b"INVALID_COMMAND")
            send_bytes_with_length_prefix(conn, b"Lenh khong hop le.")

    except ConnectionResetError:
        print(f"🔌 [SERVER] Client {addr} đã ngắt kết nối đột ngột.")
    except Exception as e:
        print(f"❌ [SERVER] Lỗi xử lý client {addr}: {e}")
        try:
            send_bytes_with_length_prefix(conn, b"SERVER_ERROR")
            send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))
        except:
            pass
    finally:
        conn.close()
        print(f"🚪 [SERVER] Đã đóng kết nối với {addr}")

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"🚀 [SERVER] Lắng nghe kết nối trên {HOST}:{PORT}...")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == '__main__':
    if not os.path.exists(SHARED_FILES_DB):
        save_shared_files_db({})
    if not os.path.exists(USER_ID_MAP_DB):
        save_user_id_map({})
    start_server()
