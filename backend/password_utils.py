"""
パスワードハッシュ化ユーティリティ
"""
import bcrypt


def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """パスワードを検証"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
