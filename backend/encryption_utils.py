"""
暗号化ユーティリティ - Refresh Token暗号化/復号化
"""
import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class EncryptionUtils:
    """暗号化ユーティリティクラス"""
    
    def __init__(self):
        """EncryptionUtils を初期化"""
        # 環境変数から暗号化キーを取得
        self.encryption_key = os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            # 開発環境用のデフォルトキー（本番環境では必ず環境変数で設定）
            logger.warning("ENCRYPTION_KEYが設定されていません。開発用デフォルトキーを使用します。")
            self.encryption_key = "dev-encryption-key-change-in-production"
        
        # Fernetキーを生成
        self.fernet_key = self._derive_key(self.encryption_key)
        self.fernet = Fernet(self.fernet_key)
    
    def _derive_key(self, password: str) -> bytes:
        """
        パスワードからFernetキーを導出
        
        Args:
            password: パスワード文字列
            
        Returns:
            bytes: 導出されたキー
        """
        try:
            # 固定ソルト（本番環境では動的ソルトを推奨）
            salt = b'cognito_refresh_token_salt_2024'
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            return key
            
        except Exception as e:
            logger.error(f"キー導出エラー: {e}")
            raise
    
    def encrypt_token(self, token: str) -> str:
        """
        トークンを暗号化
        
        Args:
            token: 暗号化するトークン
            
        Returns:
            str: 暗号化されたトークン（Base64エンコード）
        """
        try:
            if not token:
                return ""
            
            # トークンを暗号化
            encrypted_token = self.fernet.encrypt(token.encode())
            
            # Base64エンコードして文字列として返す
            return base64.urlsafe_b64encode(encrypted_token).decode()
            
        except Exception as e:
            logger.error(f"トークン暗号化エラー: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        暗号化されたトークンを復号化
        
        Args:
            encrypted_token: 暗号化されたトークン（Base64エンコード）
            
        Returns:
            str: 復号化されたトークン
        """
        try:
            if not encrypted_token:
                return ""
            
            # Base64デコード
            encrypted_data = base64.urlsafe_b64decode(encrypted_token.encode())
            
            # 復号化
            decrypted_token = self.fernet.decrypt(encrypted_data)
            
            return decrypted_token.decode()
            
        except Exception as e:
            logger.error(f"トークン復号化エラー: {e}")
            raise
    
    def is_token_encrypted(self, token: str) -> bool:
        """
        トークンが暗号化されているかチェック
        
        Args:
            token: チェックするトークン
            
        Returns:
            bool: 暗号化されている場合True
        """
        try:
            if not token:
                return False
            
            # Base64デコードを試行
            try:
                encrypted_data = base64.urlsafe_b64decode(token.encode())
                # 復号化を試行
                self.fernet.decrypt(encrypted_data)
                return True
            except:
                return False
                
        except Exception as e:
            logger.error(f"暗号化チェックエラー: {e}")
            return False


# グローバルインスタンス
encryption_utils = EncryptionUtils()