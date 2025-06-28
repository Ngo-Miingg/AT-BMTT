# file: crypto_utils.py (Phiên bản cuối cùng, dùng padding chuẩn)

import os, base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, DES3
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA512
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad # <<< THÊM VÀO

# Không cần các hàm _pad, _unpad tự viết nữa

def generate_rsa_keys(user_name, key_size=2048):
    print(f"Đang tạo cặp khóa RSA {key_size}-bit cho '{user_name}'...")
    key = RSA.generate(key_size)
    if not os.path.exists(user_name): os.makedirs(user_name)
    with open(f"{user_name}/private.pem", "wb") as f: f.write(key.export_key())
    with open(f"{user_name}/public.pem", "wb") as f: f.write(key.publickey().export_key())
    print(f"-> Đã tạo và lưu cặp khóa cho '{user_name}' thành công.")
    return True

def load_rsa_key(key_path):
    try:
        with open(key_path, "rb") as f: return RSA.import_key(f.read())
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file khóa tại '{key_path}'")
        return None

def rsa_encrypt(data, public_key_path):
    public_key = load_rsa_key(public_key_path)
    if not public_key: return None
    cipher_rsa = PKCS1_v1_5.new(public_key)
    return base64.b64encode(cipher_rsa.encrypt(data))

def rsa_decrypt(encrypted_data_b64, private_key_path):
    private_key = load_rsa_key(private_key_path)
    if not private_key: return None
    try:
        encrypted_data = base64.b64decode(encrypted_data_b64)
        cipher_rsa = PKCS1_v1_5.new(private_key)
        return cipher_rsa.decrypt(encrypted_data, None)
    except (ValueError, TypeError):
        return None

def sign_data(data_to_sign, private_key_path):
    private_key = load_rsa_key(private_key_path)
    if not private_key: return None
    h = SHA512.new(data_to_sign)
    signer = pkcs1_15.new(private_key)
    return base64.b64encode(signer.sign(h))

def verify_signature(data_to_verify, signature_b64, public_key_path):
    public_key = load_rsa_key(public_key_path)
    if not public_key: return False
    try:
        signature = base64.b64decode(signature_b64)
        h = SHA512.new(data_to_verify)
        verifier = pkcs1_15.new(public_key)
        verifier.verify(h, signature)
        return True
    except (ValueError, TypeError):
        return False

def encrypt_3des(plaintext, session_key):
    iv = get_random_bytes(DES3.block_size)
    cipher = DES3.new(session_key, DES3.MODE_CBC, iv)
    # Dùng hàm pad chuẩn
    padded_plaintext = pad(plaintext, DES3.block_size)
    ciphertext = cipher.encrypt(padded_plaintext)
    return base64.b64encode(iv), base64.b64encode(ciphertext)

def decrypt_3des(iv_b64, ciphertext_b64, session_key):
    try:
        iv, ciphertext = base64.b64decode(iv_b64), base64.b64decode(ciphertext_b64)
        cipher = DES3.new(session_key, DES3.MODE_CBC, iv)
        decrypted_padded_plaintext = cipher.decrypt(ciphertext)
        # Dùng hàm unpad chuẩn, an toàn hơn
        return unpad(decrypted_padded_plaintext, DES3.block_size)
    except Exception as e:
        print(f"LỖI BÊN TRONG decrypt_3des (có thể do padding sai): {e}")
        return None

def hash_sha512(data):
    return SHA512.new(data).hexdigest()