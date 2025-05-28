import socket
import os
import json
import threading

# --- Cấu hình Socket Server ---
HOST = '0.0.0.0'  # Lắng nghe trên tất cả các giao diện mạng
PORT = 65432       # Cổng mặc định
BUFFER_SIZE = 4096

# Thư mục gốc để lưu file của các người dùng
USERS_FILES_ROOT_DIR = 'users_encrypted_files'
os.makedirs(USERS_FILES_ROOT_DIR, exist_ok=True)

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
    print(f"✅ [SERVER] Connected by {addr}")
    try:
        command_bytes = recv_bytes_with_length_prefix(conn)
        if not command_bytes:
            print("[SERVER] No command received, closing connection.")
            return

        command = command_bytes.decode('utf-8')
        print(f"[SERVER] Nhận lệnh: {command}")

        # Các lệnh liên quan đến người dùng
        if command in ["UPLOAD_USER_FILE", "LIST_USER_FILES", "DOWNLOAD_USER_FILE", "DELETE_USER_FILE"]:
            user_id_bytes = recv_bytes_with_length_prefix(conn)
            if not user_id_bytes:
                send_bytes_with_length_prefix(conn, b"ERROR")
                send_bytes_with_length_prefix(conn, b"User ID not provided.")
                return

            user_id = user_id_bytes.decode('utf-8')
            user_dir = os.path.join(USERS_FILES_ROOT_DIR, user_id)
            os.makedirs(user_dir, exist_ok=True) # Tạo thư mục cho user nếu chưa có

            if command == "UPLOAD_USER_FILE":
                filename = recv_bytes_with_length_prefix(conn).decode('utf-8')
                file_data = recv_bytes_with_length_prefix(conn)
                
                filepath = os.path.join(user_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(file_data)
                print(f"⬆️ [SERVER] User {user_id}: Đã nhận và lưu file: {filename}")
                send_bytes_with_length_prefix(conn, b"UPLOAD_SUCCESS")
                send_bytes_with_length_prefix(conn, b"File da duoc upload thanh cong.")

            elif command == "LIST_USER_FILES":
                files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))]
                files_json = json.dumps(files)
                print(f"📋 [SERVER] User {user_id}: Gửi danh sách file: {files}")
                send_bytes_with_length_prefix(conn, b"LIST_SUCCESS")
                send_bytes_with_length_prefix(conn, files_json.encode('utf-8'))

            elif command == "DOWNLOAD_USER_FILE":
                filename = recv_bytes_with_length_prefix(conn).decode('utf-8')
                filepath = os.path.join(user_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        file_data = f.read()
                    print(f"⬇️ [SERVER] User {user_id}: Gửi file: {filename}")
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_SUCCESS")
                    send_bytes_with_length_prefix(conn, file_data)
                else:
                    print(f"❌ [SERVER] User {user_id}: File không tồn tại: {filename}")
                    send_bytes_with_length_prefix(conn, b"DOWNLOAD_FAILED")
                    send_bytes_with_length_prefix(conn, b"File khong ton tai tren server.")

            elif command == "DELETE_USER_FILE":
                filename = recv_bytes_with_length_prefix(conn).decode('utf-8')
                filepath = os.path.join(user_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"🗑️ [SERVER] User {user_id}: Đã xóa file: {filename}")
                    send_bytes_with_length_prefix(conn, b"DELETE_SUCCESS")
                    send_bytes_with_length_prefix(conn, b"File da duoc xoa thanh cong.")
                else:
                    print(f"❌ [SERVER] User {user_id}: File không tồn tại để xóa: {filename}")
                    send_bytes_with_length_prefix(conn, b"DELETE_FAILED")
                    send_bytes_with_length_prefix(conn, b"File khong ton tai de xoa.")
        else:
            print(f"❓ [SERVER] Lệnh không hợp lệ: {command}")
            send_bytes_with_length_prefix(conn, b"INVALID_COMMAND")
            send_bytes_with_length_prefix(conn, b"Lenh khong hop le.")

    except ConnectionResetError:
        print(f"🔌 [SERVER] Client {addr} đã ngắt kết nối đột ngột.")
    except Exception as e:
        print(f"❌ [SERVER] Lỗi xử lý client {addr}: {e}")
        # Gửi lỗi cho client nếu có thể
        try:
            send_bytes_with_length_prefix(conn, b"SERVER_ERROR")
            send_bytes_with_length_prefix(conn, str(e).encode('utf-8'))
        except:
            pass # Không thể gửi lỗi nếu kết nối đã chết
    finally:
        conn.close()
        print(f"🚪 [SERVER] Đã đóng kết nối với {addr}")

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Cho phép tái sử dụng địa chỉ
        s.bind((HOST, PORT))
        s.listen()
        print(f"🚀 [SERVER] Server đang lắng nghe trên {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            # Sử dụng luồng riêng cho mỗi client để xử lý song song
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.start()

if __name__ == "__main__":
    start_server()