"""
移行ミドルウェア - 電話番号認証システムの無効化状態をチェック
"""
import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from database import db_manager

logger = logging.getLogger(__name__)


class MigrationMiddleware:
    """移行状態管理ミドルウェア"""
    
    def __init__(self):
        self._phone_auth_disabled = None
        self._last_check_time = None
        self._cache_duration = 300  # 5分間キャッシュ
    
    async def is_phone_auth_disabled(self) -> bool:
        """
        電話番号認証が無効化されているかチェック
        
        Returns:
            bool: 無効化されている場合True
        """
        try:
            import time
            current_time = time.time()
            
            # キャッシュが有効な場合はキャッシュ値を返す
            if (self._phone_auth_disabled is not None and 
                self._last_check_time is not None and 
                current_time - self._last_check_time < self._cache_duration):
                return self._phone_auth_disabled
            
            # データベースから設定を取得
            query = """
            SELECT setting_value 
            FROM system_settings 
            WHERE setting_key = 'phone_auth_disabled'
            """
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query)
                    result = await cursor.fetchone()
                    
                    if result:
                        disabled = result[0].lower() == 'true'
                    else:
                        disabled = False
                    
                    # キャッシュを更新
                    self._phone_auth_disabled = disabled
                    self._last_check_time = current_time
                    
                    return disabled
                    
        except Exception as e:
            logger.error(f"電話番号認証状態チェックエラー: {e}")
            # エラー時は安全側に倒して無効化されていないとみなす
            return False
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """
        移行状態の詳細情報を取得
        
        Returns:
            Dict: 移行状態情報
        """
        try:
            query = """
            SELECT setting_key, setting_value, updated_at
            FROM system_settings 
            WHERE setting_key IN (
                'phone_auth_disabled',
                'cognito_migration_status',
                'migration_start_date',
                'migration_completion_date'
            )
            """
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query)
                    results = await cursor.fetchall()
                    
                    status_info = {}
                    for row in results:
                        status_info[row[0]] = {
                            'value': row[1],
                            'updated_at': row[2].isoformat() if row[2] else None
                        }
                    
                    return status_info
                    
        except Exception as e:
            logger.error(f"移行状態取得エラー: {e}")
            return {}
    
    async def check_phone_auth_endpoint(self, request: Request) -> Optional[HTTPException]:
        """
        電話番号認証エンドポイントへのアクセスをチェック
        
        Args:
            request: FastAPI リクエストオブジェクト
            
        Returns:
            Optional[HTTPException]: 無効化されている場合はHTTPException、そうでなければNone
        """
        try:
            # 電話番号認証関連のエンドポイントパス
            phone_auth_endpoints = [
                '/auth/signup/initiate',
                '/auth/signup/verify',
                '/auth/signin/initiate',
                '/auth/signin/verify'
            ]
            
            request_path = str(request.url.path)
            
            # 電話番号認証エンドポイントかチェック
            if request_path in phone_auth_endpoints:
                is_disabled = await self.is_phone_auth_disabled()
                
                if is_disabled:
                    logger.warning(f"無効化された電話番号認証エンドポイントへのアクセス: {request_path}")
                    
                    return HTTPException(
                        status_code=status.HTTP_410_GONE,
                        detail={
                            'error': 'phone_auth_disabled',
                            'message': '電話番号認証システムは無効化されました。メールアドレス+パスワード認証をご利用ください。',
                            'migration_info': {
                                'new_auth_method': 'email_password',
                                'registration_endpoint': '/auth/cognito/register',
                                'login_endpoint': '/auth/cognito/login'
                            }
                        }
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"電話番号認証エンドポイントチェックエラー: {e}")
            # エラー時は安全側に倒してアクセスを許可
            return None
    
    async def update_migration_status(self, status: str, additional_info: Optional[Dict[str, Any]] = None) -> bool:
        """
        移行状態を更新
        
        Args:
            status: 移行状態 ('not_started', 'in_progress', 'completed', 'failed')
            additional_info: 追加情報
            
        Returns:
            bool: 更新成功の場合True
        """
        try:
            from datetime import datetime
            
            now = datetime.utcnow()
            
            # 移行状態を更新
            query = """
            UPDATE system_settings 
            SET setting_value = %s, updated_at = %s
            WHERE setting_key = 'cognito_migration_status'
            """
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (status, now))
                    
                    # 追加情報がある場合は更新
                    if additional_info:
                        for key, value in additional_info.items():
                            update_query = """
                            INSERT INTO system_settings (setting_key, setting_value, created_at, updated_at)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            setting_value = VALUES(setting_value),
                            updated_at = VALUES(updated_at)
                            """
                            await cursor.execute(update_query, (key, str(value), now, now))
                    
                    await conn.commit()
            
            # キャッシュをクリア
            self._phone_auth_disabled = None
            self._last_check_time = None
            
            logger.info(f"移行状態を更新しました: {status}")
            return True
            
        except Exception as e:
            logger.error(f"移行状態更新エラー: {e}")
            return False


# グローバルインスタンス
migration_middleware = MigrationMiddleware()