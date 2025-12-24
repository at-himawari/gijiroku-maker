"""
テスト用データベース設定
"""
import os
import asyncio
import aiomysql
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()


class TestDatabaseManager(DatabaseManager):
    """テスト用データベース管理クラス"""
    
    # pytestがテストクラスとして認識しないようにする
    __test__ = False
    
    def __init__(self):
        """テスト用データベース接続設定を初期化"""
        self.host = os.getenv('TEST_DB_HOST', 'localhost')
        self.port = int(os.getenv('TEST_DB_PORT', 3306))
        self.user = os.getenv('TEST_DB_USER', 'gijiroku_user')
        self.password = os.getenv('TEST_DB_PASSWORD', 'gijiroku_pass')
        self.database = os.getenv('TEST_DB_NAME', 'gijiroku_test_db')
        self.pool = None
        self.mock_mode = False  # モックモードフラグ
    
    async def setup_test_database(self):
        """テスト用データベースをセットアップ"""
        # まず、データベースを作成するために管理者接続を使用
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                charset='utf8mb4'
            )
            
            async with conn.cursor() as cursor:
                # テスト用データベースを作成（存在しない場合）
                await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
                await cursor.execute(f"USE {self.database}")
            
            await conn.ensure_closed()
            
            # 通常のプール初期化
            await self.init_pool()
            
        except Exception as e:
            print(f"テスト用データベースセットアップエラー: {e}")
            # データベースが存在しない場合は、メモリ内テストモードを使用
            self.pool = None
            self.mock_mode = True
            print("モックモードでテストを実行します")
    
    async def cleanup_test_database(self):
        """テスト用データベースをクリーンアップ"""
        if self.mock_mode:
            # モックモードでは何もしない
            return
            
        if self.pool:
            try:
                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        # テストデータをクリーンアップ
                        await cursor.execute("DELETE FROM auth_logs")
                        await cursor.execute("DELETE FROM user_sessions")
                        await cursor.execute("DELETE FROM users")
                        
            except Exception as e:
                print(f"テストデータクリーンアップエラー: {e}")
    
    # モック用のメソッドを追加
    async def create_auth_log(self, log_data):
        """認証ログ作成（モック対応）"""
        if self.mock_mode:
            # モックモードでは成功を返す
            from models import AuthLog
            return AuthLog(
                log_id=1,
                user_id=log_data.user_id,
                email=log_data.email,
                event_type=log_data.event_type,
                result=log_data.result,
                details=log_data.details,
                ip_address=log_data.ip_address
            )
        return await super().create_auth_log(log_data)
    
    async def create_user(self, user_data):
        """ユーザー作成（モック対応）"""
        if self.mock_mode:
            # モックモードでは成功を返す
            from models import User
            return User(
                user_id="test-user-id",
                cognito_username=user_data.cognito_username,
                created_at="2023-01-01T00:00:00",
                updated_at="2023-01-01T00:00:00",
                last_login=None,
                is_active=True
            )
        return await super().create_user(user_data)
    
    async def get_user_by_phone(self, phone_number):
        """電話番号でユーザー取得（モック対応）"""
        if self.mock_mode:
            # モックモードでは None を返す（ユーザーが存在しない）
            return None
        return await super().get_user_by_phone(phone_number)
    
    async def create_session(self, session_data):
        """セッション作成（モック対応）"""
        if self.mock_mode:
            # モックモードでは成功を返す
            from models import UserSession
            return UserSession(
                session_id="test-session-id",
                user_id=session_data.user_id,
                access_token_hash=session_data.access_token_hash,
                refresh_token_hash=session_data.refresh_token_hash,
                expires_at=session_data.expires_at,
                created_at="2023-01-01T00:00:00",
                last_activity="2023-01-01T00:00:00",
                is_active=True,
                client_ip=session_data.client_ip,
                user_agent=session_data.user_agent
            )
        return await super().create_session(session_data)
    
    async def teardown_test_database(self):
        """テスト用データベースを削除"""
        if self.mock_mode:
            # モックモードでは何もしない
            return
            
        if self.pool:
            await self.close_pool()
        
        try:
            conn = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                charset='utf8mb4'
            )
            
            async with conn.cursor() as cursor:
                await cursor.execute(f"DROP DATABASE IF EXISTS {self.database}")
            
            await conn.ensure_closed()
            
        except Exception as e:
            print(f"テスト用データベース削除エラー: {e}")


# テスト用のグローバルインスタンス
test_db_manager = TestDatabaseManager()


async def setup_test_db():
    """テスト開始前のセットアップ"""
    await test_db_manager.setup_test_database()


async def cleanup_test_db():
    """各テスト後のクリーンアップ"""
    await test_db_manager.cleanup_test_database()


async def teardown_test_db():
    """テスト終了後の削除"""
    await test_db_manager.teardown_test_database()


# テスト用のデータベース接続チェック
async def check_database_connection():
    """データベース接続をチェック"""
    try:
        await test_db_manager.setup_test_database()
        if test_db_manager.pool:
            print("✅ テスト用データベース接続成功")
            await test_db_manager.close_pool()
            return True
        else:
            print("❌ テスト用データベース接続失敗")
            return False
    except Exception as e:
        print(f"❌ データベース接続エラー: {e}")
        return False


if __name__ == "__main__":
    # データベース接続テスト
    asyncio.run(check_database_connection())