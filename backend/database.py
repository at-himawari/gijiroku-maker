"""
データベース接続とCRUD操作
"""
import os
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
import aiomysql
from dotenv import load_dotenv
from models import User, UserSession, AuthLog, UserCreate, SessionCreate, AuthLogCreate

load_dotenv()

logger = logging.getLogger(__name__)

import boto3
import json
from botocore.exceptions import ClientError

# AWS Secrets Managerからシークレットを取得する関数
def get_aws_secret(secret_name: str, region_name: str = "ap-northeast-1"):
    """
    AWS Secrets Managerから値を取得する関数
    
    Args:
        secret_name: Secrets Managerで作成したシークレットの名前
        region_name: リージョン名（デフォルトは東京: ap-northeast-1）
        
    Returns:
        dict: シークレットのキーと値の辞書 (JSONの場合)
        str:  単なる文字列として保存されている場合は文字列
    """

    # セッションの作成
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # 権限エラーや存在しないシークレットなどのエラーハンドリング
        print(f"エラーが発生しました: {e}")
        raise e

    # シークレットの取得
    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
        
        # JSON形式であれば辞書に変換して返すのが便利です
        try:
            return json.loads(secret)
        except json.JSONDecodeError:
            # JSONでない単純な文字列の場合はそのまま返す
            return secret
    else:
        # バイナリデータの場合（あまり一般的ではありませんがデコードが必要）
        return get_secret_value_response['SecretBinary']


class DatabaseManager:
    """データベース管理クラス"""
    
    def __init__(self):
        """データベース接続設定を初期化"""
        SECRET_NAME = "gijiroku_maker/prod"
        secrets = get_aws_secret(SECRET_NAME)
        if secrets and isinstance(secrets, dict):
            self.user = secrets.get('username',"root")
            self.password = secrets.get('password',"")
            self.database = secrets.get('dbname',"gijiroku_maker")
            self.host = secrets.get('host', 'localhost')
            self.port = int(secrets.get('port', 3306))        

        self.pool = None
    
    async def init_pool(self):
        """コネクションプールを初期化"""
        try:
            self.pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=True,
                maxsize=10,
                minsize=1
            )
            logger.info("データベース接続プールを初期化しました")
            
            # テーブルを作成
            await self._create_tables()
            
        except Exception as e:
            logger.error(f"データベース接続プール初期化エラー: {e}")
            raise
    
    async def _create_tables(self):
        """必要なテーブルを作成（Cognito中心管理）"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Cognito中心管理ユーザーテーブル（最小限の情報のみ）
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id VARCHAR(36) PRIMARY KEY,
                        cognito_user_sub VARCHAR(255) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        last_login TIMESTAMP NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        
                        INDEX idx_cognito_user_sub (cognito_user_sub),
                        INDEX idx_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # Cognito統合セッションテーブル
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        cognito_user_sub VARCHAR(255) NOT NULL,
                        access_token_hash VARCHAR(255) NOT NULL,
                        id_token_hash VARCHAR(255) NULL,
                        refresh_token_hash VARCHAR(255) NULL,
                        encrypted_refresh_token TEXT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        client_ip VARCHAR(45) NULL,
                        user_agent TEXT NULL,
                        
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        INDEX idx_user_id (user_id),
                        INDEX idx_cognito_user_sub (cognito_user_sub),
                        INDEX idx_expires_at (expires_at),
                        INDEX idx_access_token_hash (access_token_hash),
                        INDEX idx_is_active (is_active)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # encrypted_refresh_tokenカラムを追加（既存テーブルの場合）
                try:
                    await cursor.execute("""
                        ALTER TABLE user_sessions 
                        ADD COLUMN encrypted_refresh_token TEXT NULL
                    """)
                    logger.info("user_sessionsテーブルにencrypted_refresh_tokenカラムを追加しました")
                except Exception as e:
                    # カラムが既に存在する場合はエラーを無視
                    if "Duplicate column name" not in str(e):
                        logger.warning(f"encrypted_refresh_tokenカラム追加でエラー: {e}")
                    pass
                # 認証ログテーブル（Cognito対応）
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth_logs (
                        log_id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NULL,
                        email VARCHAR(255) NULL,
                        event_type VARCHAR(50) NOT NULL,
                        result VARCHAR(20) NOT NULL,
                        details JSON NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ip_address VARCHAR(45) NULL,
                        
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
                        INDEX idx_user_id (user_id),
                        INDEX idx_email (email),
                        INDEX idx_event_type (event_type),
                        INDEX idx_result (result),
                        INDEX idx_timestamp (timestamp)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # アプリケーションユーザーデータテーブル（ビジネスデータ管理）
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS app_user_data (
                        app_user_id VARCHAR(36) PRIMARY KEY,
                        cognito_sub VARCHAR(36) UNIQUE NOT NULL,
                        subscription_status ENUM('free', 'premium') DEFAULT 'free',
                        usage_count INT DEFAULT 0,
                        monthly_usage_count INT DEFAULT 0,
                        last_usage_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        preferences JSON NULL,
                        profile_data JSON NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        
                        INDEX idx_cognito_sub (cognito_sub),
                        INDEX idx_subscription_status (subscription_status),
                        INDEX idx_created_at (created_at),
                        INDEX idx_usage_count (usage_count)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                # seconds_balanceカラムを追加（既存テーブルの場合）
                try:
                    await cursor.execute("""
                        ALTER TABLE app_user_data 
                        ADD COLUMN seconds_balance FLOAT DEFAULT 300.0
                    """)
                    logger.info("app_user_dataテーブルにseconds_balanceカラムを追加しました")
                except Exception as e:
                    if "Duplicate column name" not in str(e):
                        logger.warning(f"seconds_balanceカラム追加でエラー: {e}")
                    pass
                
                logger.info("Cognito中心管理データベーステーブルを作成しました")
    
    async def close_pool(self):
        """コネクションプールを閉じる"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("データベース接続プールを閉じました")
    
    # ユーザー関連操作（Cognito中心管理）
    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        """新しいユーザーを作成（Cognito中心管理）"""
        try:
            user = User(
                cognito_user_sub=user_data.cognito_user_sub
            )
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        INSERT INTO users (user_id, cognito_user_sub, created_at, is_active)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        user.user_id,
                        user.cognito_user_sub,
                        user.created_at,
                        user.is_active
                    ))
                    
            logger.info(f"Cognitoユーザーを作成しました: {user.user_id} (Sub: {user.cognito_user_sub})")
            return user
            
        except Exception as e:
            logger.error(f"Cognitoユーザー作成エラー: {e}")
            return None
    
    async def get_user_by_cognito_sub(self, cognito_user_sub: str) -> Optional[User]:
        """Cognito User Subでユーザーを取得"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM users WHERE cognito_user_sub = %s
                    """, (cognito_user_sub,))
                    
                    row = await cursor.fetchone()
                    if row:
                        return User(**row)
                    return None
                    
        except Exception as e:
            logger.error(f"Cognitoユーザー取得エラー: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """メールアドレスでユーザーを取得（Cognito経由）"""
        try:
            # Cognitoでユーザーを検索してUser Subを取得
            from cognito_service import CognitoService
            cognito_service = CognitoService()
            
            try:
                response = cognito_service.cognito_client.admin_get_user(
                    UserPoolId=cognito_service.user_pool_id,
                    Username=email
                )
                
                # Cognito User Subを取得
                cognito_user_sub = None
                for attr in response['UserAttributes']:
                    if attr['Name'] == 'sub':
                        cognito_user_sub = attr['Value']
                        break
                
                if cognito_user_sub:
                    return await self.get_user_by_cognito_sub(cognito_user_sub)
                
            except Exception as e:
                logger.debug(f"Cognitoユーザー検索エラー: {e}")
                return None
                
            return None
                    
        except Exception as e:
            logger.error(f"メールアドレスでのユーザー取得エラー: {e}")
            return None
    
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """ユーザーIDでユーザーを取得"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM users WHERE user_id = %s
                    """, (user_id,))
                    
                    row = await cursor.fetchone()
                    if row:
                        return User(**row)
                    return None
                    
        except Exception as e:
            logger.error(f"ユーザー取得エラー: {e}")
            return None
    
    async def update_user_login(self, user_id: str) -> bool:
        """ユーザーのログイン時刻を更新"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE users 
                        SET last_login = %s
                        WHERE user_id = %s
                    """, (datetime.utcnow(), user_id))
                    
            return True
            
        except Exception as e:
            logger.error(f"ユーザーログイン更新エラー: {e}")
            return False
    
    # セッション関連操作（Cognito統合）
    async def create_session(self, session_data: SessionCreate) -> Optional[UserSession]:
        """新しいセッションを作成（Cognito統合）"""
        try:
            import hashlib
            from encryption_utils import encryption_utils
            
            expires_at = datetime.utcnow() + timedelta(seconds=session_data.expires_in)
            
            # トークンをハッシュ化して保存
            access_token_hash = hashlib.sha256(session_data.access_token.encode()).hexdigest()
            id_token_hash = hashlib.sha256(session_data.id_token.encode()).hexdigest() if session_data.id_token else None
            refresh_token_hash = hashlib.sha256(session_data.refresh_token.encode()).hexdigest() if session_data.refresh_token else None
            
            # Refresh Tokenを暗号化して保存
            encrypted_refresh_token = None
            if session_data.refresh_token:
                try:
                    encrypted_refresh_token = encryption_utils.encrypt_token(session_data.refresh_token)
                except Exception as e:
                    logger.error(f"Refresh Token暗号化エラー: {e}")
                    # 暗号化に失敗してもセッション作成は継続
            
            session = UserSession(
                user_id=session_data.user_id,
                cognito_user_sub=session_data.cognito_user_sub,
                access_token=session_data.access_token,
                id_token=session_data.id_token,
                refresh_token=session_data.refresh_token,
                expires_at=expires_at,
                client_ip=session_data.client_ip,
                user_agent=session_data.user_agent
            )
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        INSERT INTO user_sessions 
                        (session_id, user_id, cognito_user_sub, access_token_hash, id_token_hash, 
                         refresh_token_hash, encrypted_refresh_token, expires_at, created_at, last_activity, is_active, 
                         client_ip, user_agent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        session.session_id,
                        session.user_id,
                        session.cognito_user_sub,
                        access_token_hash,
                        id_token_hash,
                        refresh_token_hash,
                        encrypted_refresh_token,
                        session.expires_at,
                        session.created_at,
                        session.last_activity,
                        session.is_active,
                        session.client_ip,
                        session.user_agent
                    ))
                    
            logger.info(f"Cognitoセッションを作成しました: {session.session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Cognitoセッション作成エラー: {e}")
            return None
    
    async def get_session_by_token(self, access_token: str) -> Optional[UserSession]:
        """アクセストークンでセッションを取得（Cognito統合）"""
        try:
            import hashlib
            
            access_token_hash = hashlib.sha256(access_token.encode()).hexdigest()
            
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM user_sessions 
                        WHERE access_token_hash = %s AND is_active = TRUE
                    """, (access_token_hash,))
                    
                    row = await cursor.fetchone()
                    if row:
                        # トークンを復元（実際のトークンは保存していないので、引数のトークンを使用）
                        session_dict = dict(row)
                        session_dict['access_token'] = access_token
                        return UserSession(**session_dict)
                    return None
                    
        except Exception as e:
            logger.error(f"Cognitoセッション取得エラー: {e}")
            return None
    
    async def update_session_activity(self, session_id: str) -> bool:
        """セッションの最終活動時刻を更新"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET last_activity = %s
                        WHERE session_id = %s AND is_active = TRUE
                    """, (datetime.utcnow(), session_id))
                    
            return True
            
        except Exception as e:
            logger.error(f"セッション活動更新エラー: {e}")
            return False
    
    async def invalidate_session(self, session_id: str) -> bool:
        """セッションを無効化"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET is_active = FALSE
                        WHERE session_id = %s
                    """, (session_id,))
                    
            logger.info(f"セッションを無効化しました: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"セッション無効化エラー: {e}")
            return False
    
    async def invalidate_user_sessions(self, user_id: str) -> bool:
        """ユーザーの全セッションを無効化"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET is_active = FALSE
                        WHERE user_id = %s
                    """, (user_id,))
                    
            logger.info(f"ユーザーの全セッションを無効化しました: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"ユーザーセッション無効化エラー: {e}")
            return False
    
    async def cleanup_expired_sessions(self) -> int:
        """期限切れセッションをクリーンアップ"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # 24時間経過したセッションを無効化
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET is_active = FALSE
                        WHERE expires_at < %s AND is_active = TRUE
                    """, (datetime.utcnow(),))
                    
                    expired_count = cursor.rowcount
                    
                    # 2時間非アクティブなセッションを無効化
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET is_active = FALSE
                        WHERE last_activity < %s AND is_active = TRUE
                    """, (datetime.utcnow() - timedelta(hours=2),))
                    
                    inactive_count = cursor.rowcount
                    
            total_cleaned = expired_count + inactive_count
            if total_cleaned > 0:
                logger.info(f"期限切れセッションをクリーンアップしました: {total_cleaned}件")
            
            return total_cleaned
            
        except Exception as e:
            logger.error(f"セッションクリーンアップエラー: {e}")
            return 0
    
    async def extend_session(self, session_id: str, new_expires_at: datetime) -> bool:
        """セッションの有効期限を延長"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE user_sessions 
                        SET expires_at = %s, last_activity = %s
                        WHERE session_id = %s AND is_active = TRUE
                    """, (new_expires_at, datetime.utcnow(), session_id))
                    
            logger.info(f"セッション有効期限を延長しました: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"セッション延長エラー: {e}")
            return False
    
    async def get_session_by_id(self, session_id: str) -> Optional[UserSession]:
        """セッションIDでセッションを取得"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM user_sessions 
                        WHERE session_id = %s AND is_active = TRUE
                    """, (session_id,))
                    
                    row = await cursor.fetchone()
                    if row:
                        return UserSession(**row)
                    return None
                    
        except Exception as e:
            logger.error(f"セッション取得エラー: {e}")
            return None
    
    # ログ関連操作（Cognito統合）
    async def create_auth_log(self, log_data: AuthLogCreate) -> Optional[AuthLog]:
        """認証ログを作成（Cognito統合）"""
        try:
            # log_data.details は辞書の可能性があり、JSON文字列に変換が必要
            details_json = json.dumps(log_data.details) if isinstance(log_data.details, dict) else log_data.details

            log = AuthLog(
                user_id=log_data.user_id,
                email=log_data.email,  # phone_numberからemailに変更
                event_type=log_data.event_type,
                result=log_data.result,
                details=details_json,
                ip_address=log_data.ip_address
            )
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        INSERT INTO auth_logs 
                        (log_id, user_id, email, event_type, result, details, timestamp, ip_address)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        log.log_id,
                        log.user_id,
                        log.email,
                        log.event_type,
                        log.result,
                        details_json, # JSON文字列を使用
                        log.timestamp,
                        log.ip_address
                    ))
                    
            return log
            
        except Exception as e:
            logger.error(f"認証ログ作成エラー: {e}")
            return None

    # アプリケーションユーザーデータ関連操作
    async def create_app_user_data(self, cognito_sub: str, initial_data: dict = None) -> Optional[dict]:
        """アプリケーションユーザーデータを作成"""
        try:
            import uuid
            app_user_id = str(uuid.uuid4())
            
            # デフォルトの初期データ
            default_preferences = {
                "language": "ja",
                "theme": "light",
                "notifications": True
            }
            
            default_profile = {
                "display_name": "",
                "avatar_url": "",
                "timezone": "Asia/Tokyo"
            }
            
            preferences = initial_data.get('preferences', default_preferences) if initial_data else default_preferences
            profile_data = initial_data.get('profile_data', default_profile) if initial_data else default_profile
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        INSERT INTO app_user_data 
                        (app_user_id, cognito_sub, subscription_status, usage_count, 
                         monthly_usage_count, seconds_balance, preferences, profile_data, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        app_user_id,
                        cognito_sub,
                        'free',
                        0,
                        0,
                        300.0, # 初期値5分
                        json.dumps(preferences),
                        json.dumps(profile_data),
                        datetime.utcnow(),
                        datetime.utcnow()
                    ))
                    
            logger.info(f"アプリケーションユーザーデータを作成しました: {app_user_id} (Cognito Sub: {cognito_sub})")
            
            return {
                'app_user_id': app_user_id,
                'cognito_sub': cognito_sub,
                'seconds_balance': 300.0,
                'subscription_status': 'free',
                'usage_count': 0,
                'monthly_usage_count': 0,
                'preferences': preferences,
                'profile_data': profile_data,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"アプリケーションユーザーデータ作成エラー: {e}")
            return None
    
    async def get_app_user_data_by_cognito_sub(self, cognito_sub: str) -> Optional[dict]:
        """Cognito Subでアプリケーションユーザーデータを取得（月次リセットチェック付き）"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM app_user_data WHERE cognito_sub = %s
                    """, (cognito_sub,))
                    
                    row = await cursor.fetchone()
                    if row:
                        data = dict(row)
                        # 月次リセットチェック
                        last_reset = data.get('last_usage_reset')
                        now = datetime.utcnow()
                        # 前回リセットから月が変わっているかチェック
                        if last_reset and (now.year > last_reset.year or now.month > last_reset.month):
                            # 月が変わった場合、Freeプラン分(300秒)を下回っていれば300秒まで補充
                            # (購入分は持ち越すが、Free枠は毎月リセットという考え方で、最低300秒を保証)
                            new_balance = data['seconds_balance']
                            if new_balance < 300.0:
                                new_balance = 300.0
                            
                            await cursor.execute("""
                                UPDATE app_user_data 
                                SET monthly_usage_count = 0, last_usage_reset = %s, seconds_balance = %s
                                WHERE cognito_sub = %s
                            """, (now, new_balance, cognito_sub))
                            data['seconds_balance'] = new_balance
                            data['monthly_usage_count'] = 0
                        
                        # JSONパース
                        if data.get('preferences') and isinstance(data['preferences'], str):
                            data['preferences'] = json.loads(data['preferences'])
                        if data.get('profile_data') and isinstance(data['profile_data'], str):
                            data['profile_data'] = json.loads(data['profile_data'])
                        return data
                    return None
        except Exception as e:
            logger.error(f"データ取得エラー: {e}")
            return None
        
    async def add_balance(self, cognito_sub: str, seconds: float) -> bool:
        """残高を追加（Stripe購入時など）"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET seconds_balance = seconds_balance + %s, 
                            subscription_status = 'premium',
                            updated_at = %s
                        WHERE cognito_sub = %s
                    """, (seconds, datetime.utcnow(), cognito_sub))
            logger.info(f"残高を追加しました: {cognito_sub} (+{seconds}s)")
            return True
        except Exception as e:
            logger.error(f"残高追加エラー: {e}")
            return False

    async def deduct_balance(self, cognito_sub: str, seconds: float) -> bool:
        """残高を消費（音声認識利用時）"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET seconds_balance = GREATEST(0, seconds_balance - %s),
                            usage_count = usage_count + 1,
                            monthly_usage_count = monthly_usage_count + 1,
                            updated_at = %s
                        WHERE cognito_sub = %s
                    """, (seconds, datetime.utcnow(), cognito_sub))
            return True
        except Exception as e:
            logger.error(f"残高消費エラー: {e}")
            return False
    
    async def get_app_user_data_by_app_id(self, app_user_id: str) -> Optional[dict]:
        """アプリケーションユーザーIDでデータを取得"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM app_user_data WHERE app_user_id = %s
                    """, (app_user_id,))
                    
                    row = await cursor.fetchone()
                    if row:
                        # JSONフィールドをパース
                        result = dict(row)
                        if result.get('preferences'):
                            result['preferences'] = json.loads(result['preferences'])
                        if result.get('profile_data'):
                            result['profile_data'] = json.loads(result['profile_data'])
                        return result
                    return None
                    
        except Exception as e:
            logger.error(f"アプリケーションユーザーデータ取得エラー: {e}")
            return None
    
    async def update_app_user_profile(self, cognito_sub: str, profile_updates: dict) -> bool:
        """ユーザープロフィールを更新"""
        try:
            # 現在のデータを取得
            current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
            if not current_data:
                # データが存在しない場合は作成
                await self.create_app_user_data(cognito_sub)
                current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
                if not current_data:
                    return False
            
            # プロフィールデータを更新
            current_profile = current_data.get('profile_data', {})
            current_profile.update(profile_updates)
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET profile_data = %s, updated_at = %s
                        WHERE cognito_sub = %s
                    """, (
                        json.dumps(current_profile),
                        datetime.utcnow(),
                        cognito_sub
                    ))
                    
            logger.info(f"ユーザープロフィールを更新しました: {cognito_sub}")
            return True
            
        except Exception as e:
            logger.error(f"ユーザープロフィール更新エラー: {e}")
            return False
    
    async def update_app_user_preferences(self, cognito_sub: str, preferences_updates: dict) -> bool:
        """ユーザー設定を更新"""
        try:
            # 現在のデータを取得
            current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
            if not current_data:
                # データが存在しない場合は作成
                await self.create_app_user_data(cognito_sub)
                current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
                if not current_data:
                    return False
            
            # 設定データを更新
            current_preferences = current_data.get('preferences', {})
            current_preferences.update(preferences_updates)
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET preferences = %s, updated_at = %s
                        WHERE cognito_sub = %s
                    """, (
                        json.dumps(current_preferences),
                        datetime.utcnow(),
                        cognito_sub
                    ))
                    
            logger.info(f"ユーザー設定を更新しました: {cognito_sub}")
            return True
            
        except Exception as e:
            logger.error(f"ユーザー設定更新エラー: {e}")
            return False
    
    async def increment_usage_count(self, cognito_sub: str, increment: int = 1) -> bool:
        """使用回数をインクリメント"""
        try:
            # 現在のデータを取得
            current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
            if not current_data:
                # データが存在しない場合は作成
                await self.create_app_user_data(cognito_sub)
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET usage_count = usage_count + %s, 
                            monthly_usage_count = monthly_usage_count + %s,
                            updated_at = %s
                        WHERE cognito_sub = %s
                    """, (increment, increment, datetime.utcnow(), cognito_sub))
                    
            logger.info(f"使用回数をインクリメントしました: {cognito_sub} (+{increment})")
            return True
            
        except Exception as e:
            logger.error(f"使用回数インクリメントエラー: {e}")
            return False
    
    async def update_subscription_status(self, cognito_sub: str, status: str) -> bool:
        """サブスクリプション状態を更新"""
        try:
            if status not in ['free', 'premium']:
                logger.error(f"無効なサブスクリプション状態: {status}")
                return False
            
            # 現在のデータを取得
            current_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
            if not current_data:
                # データが存在しない場合は作成
                await self.create_app_user_data(cognito_sub)
            
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET subscription_status = %s, updated_at = %s
                        WHERE cognito_sub = %s
                    """, (status, datetime.utcnow(), cognito_sub))
                    
            logger.info(f"サブスクリプション状態を更新しました: {cognito_sub} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"サブスクリプション状態更新エラー: {e}")
            return False
    
    async def reset_monthly_usage(self, cognito_sub: str) -> bool:
        """月次使用回数をリセット"""
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        UPDATE app_user_data 
                        SET monthly_usage_count = 0, 
                            last_usage_reset = %s,
                            updated_at = %s
                        WHERE cognito_sub = %s
                    """, (datetime.utcnow(), datetime.utcnow(), cognito_sub))
                    
            logger.info(f"月次使用回数をリセットしました: {cognito_sub}")
            return True
            
        except Exception as e:
            logger.error(f"月次使用回数リセットエラー: {e}")
            return False
    
    async def get_user_usage_statistics(self, cognito_sub: str) -> Optional[dict]:
        """ユーザーの使用統計を取得"""
        try:
            app_data = await self.get_app_user_data_by_cognito_sub(cognito_sub)
            if not app_data:
                return None
            
            return {
                'total_usage': app_data.get('usage_count', 0),
                'monthly_usage': app_data.get('monthly_usage_count', 0),
                'subscription_status': app_data.get('subscription_status', 'free'),
                'last_usage_reset': app_data.get('last_usage_reset'),
                'member_since': app_data.get('created_at')
            }
            
        except Exception as e:
            logger.error(f"使用統計取得エラー: {e}")
            return None


# グローバルなデータベースマネージャーインスタンス
db_manager = DatabaseManager()
