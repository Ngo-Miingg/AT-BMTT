# file: create_admin.py
# Chạy file này để tạo tài khoản admin một cách thủ công.

from app import app, db, User
from werkzeug.security import generate_password_hash
import crypto_utils
import os

# --- THÔNG TIN TÀI KHOẢN ADMIN ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password123' # Bạn có thể đổi mật khẩu này nếu muốn

def create_admin_user():
    """Hàm để kiểm tra và tạo user admin trong database."""
    # Phải chạy trong "app context" để có thể truy cập database
    with app.app_context():
        # 1. Tạo các bảng trong DB nếu chúng chưa tồn tại
        db.create_all()

        # 2. Kiểm tra xem admin đã tồn tại chưa
        if User.query.filter_by(username=ADMIN_USERNAME).first():
            print(f"-> Tài khoản '{ADMIN_USERNAME}' đã tồn tại.")
            return

        # 3. Nếu chưa tồn tại, bắt đầu tạo mới
        print(f"Đang tạo tài khoản admin với tên '{ADMIN_USERNAME}'...")
        
        # Tạo cặp khóa RSA
        crypto_utils.generate_rsa_keys(ADMIN_USERNAME)
        
        # Băm mật khẩu
        password_hash = generate_password_hash(ADMIN_PASSWORD)
        
        # Tạo đối tượng User
        new_admin = User(
            username=ADMIN_USERNAME,
            password_hash=password_hash,
            public_key_path=f'{ADMIN_USERNAME}/public.pem',
            private_key_path=f'{ADMIN_USERNAME}/private.pem'
        )
        
        # Lưu vào database
        db.session.add(new_admin)
        db.session.commit()
        
        print(f"!!! Đã tạo tài khoản admin thành công !!!")
        print(f"Tên đăng nhập: {ADMIN_USERNAME}")
        print(f"Mật khẩu: {ADMIN_PASSWORD}")

if __name__ == '__main__':
    create_admin_user()