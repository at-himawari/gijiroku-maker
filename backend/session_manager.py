"""
Cognito セッション永続化とクリーンアップサービス
"""
import os
import logging
import asyncio
import json
import aiomysql
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from database import db_manager
from models import UserSession, SessionCreate
from logging_service import logging_service
from cognito_token_service import cognito_token_service

logger = logging.getLogger(__name__)

class SessionManager:
    """Cognito セッション管理サービス"""
    
    def __init__(self):
        """SessionManager を初期化"""
        self.cleanup_interval = 3600  # 1時間ごとにクリーンアップ
        self.inactive_timeout = 7200  # 2時間の非アクティブタイムアウト
        self.session_lifetime = 86400  # 24時間のセッション有効期限
        self.cleanup_task = None
        
    async def start_cleanup_task(self):
        """セッションクリーンアップタスクを開始"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("セッションクリーンアップタスクを開始しました")
    
    async def stop_cleanup_task(self):
        """セッションクリーンアップタスクを停止"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("セッションクリーンアップタスクを停止しました")
    
    async def _cleanup_loop(self):
        """セッションクリーンアップのメインループ"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                logger.info("セッションクリーンアップループがキャンセルされました")
                break
            except Exception as e:
                logger.error(f"セッションクリーンアップループエラー: {e}")
                # エラーが発生してもループを継続
                await asyncio.sleep(60)  # 1分待ってから再試行
    
    async def persist_session(self, session_data: SessionCreate, user_agent: Optional[str] = None) -> Optional[UserSession]:
        """
        Cognito セッション情報をローカルに永続化
        
        Args:
            session_data: セッション作成データ
            user_agent: ユーザーエージェント
            
        Returns:
            Optional[UserSession]: 作成されたセッション
        """
        try:
            # セッションデータにユーザーエージェントを追加
            if user_agent:
                session_data.user_agent = user_agent
            
            # データベースにセッションを作成
            session = await db_manager.create_session(session_data)
            
            if session:
                # セッション作成ログ
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "created", "success",
                    {
                        "session_id": session.session_id,
                        "expires_at": session.expires_at.isoformat(),
                        "cognito_user_sub": session.cognito_user_sub
                    },
                    session.user_id, session_data.client_ip
                )
                
                logger.info(f"Cognitoセッションを永続化しました: {session.session_id}")
                return session
            else:
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "created", "failure",
                    {"error": "session_creation_failed"},
                    session_data.user_id, session_data.client_ip
                )
                return None
                
        except Exception as e:
            logger.error(f"セッション永続化エラー: {e}")
            await logging_service.log_cognito_session_operation(
                "cognito_user", "created", "error",
                {"error": str(e)},
                session_data.user_id, session_data.client_ip
            )
            return None
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        セッション情報を取得
        
        Args:
            session_id: セッションID
            
        Returns:
            Optional[Dict]: セッション情報
        """
        try:
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT s.*, u.cognito_user_sub, u.is_active as user_active
                        FROM user_sessions s
                        JOIN users u ON s.user_id = u.user_id
                        WHERE s.session_id = %s
                    """, (session_id,))
                    
                    row = await cursor.fetchone()
                    if row:
                        session_info = dict(row)
                        
                        # 有効期限チェック
                        current_time = datetime.utcnow()
                        expires_at = session_info['expires_at']
                        last_activity = session_info['last_activity']
                        
                        session_info.update({
                            'is_expired': current_time > expires_at,
                            'is_inactive': current_time > last_activity + timedelta(seconds=self.inactive_timeout),
                            'seconds_until_expiry': max(0, int((expires_at - current_time).total_seconds())),
                            'seconds_since_activity': int((current_time - last_activity).total_seconds())
                        })
                        
                        return session_info
                    return None
                    
        except Exception as e:
            logger.error(f"セッション情報取得エラー: {e}")
            return None
    
    async def update_session_activity(self, session_id: str, ip_address: Optional[str] = None) -> bool:
        """
        セッションの最終活動時刻を更新
        
        Args:
            session_id: セッションID
            ip_address: クライアントのIPアドレス
            
        Returns:
            bool: 更新成功
        """
        try:
            success = await db_manager.update_session_activity(session_id)
            
            if success:
                logger.debug(f"セッション活動時刻を更新しました: {session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"セッション活動更新エラー: {e}")
            return False
    
    async def invalidate_session(self, session_id: str, reason: str = "manual", ip_address: Optional[str] = None) -> bool:
        """
        セッションを無効化
        
        Args:
            session_id: セッションID
            reason: 無効化理由
            ip_address: クライアントのIPアドレス
            
        Returns:
            bool: 無効化成功
        """
        try:
            # セッション情報を取得
            session_info = await self.get_session_info(session_id)
            
            # セッションを無効化
            success = await db_manager.invalidate_session(session_id)
            
            if success and session_info:
                # セッション無効化ログ
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "invalidated", "success",
                    {
                        "session_id": session_id,
                        "reason": reason,
                        "cognito_user_sub": session_info.get('cognito_user_sub')
                    },
                    session_info.get('user_id'), ip_address
                )
                
                logger.info(f"セッションを無効化しました: {session_id} (理由: {reason})")
            
            return success
            
        except Exception as e:
            logger.error(f"セッション無効化エラー: {e}")
            return False
    
    async def invalidate_user_sessions(self, user_id: str, reason: str = "user_action", ip_address: Optional[str] = None) -> int:
        """
        ユーザーの全セッションを無効化
        
        Args:
            user_id: ユーザーID
            reason: 無効化理由
            ip_address: クライアントのIPアドレス
            
        Returns:
            int: 無効化されたセッション数
        """
        try:
            # ユーザーのアクティブセッションを取得
            active_sessions = await self.get_user_active_sessions(user_id)
            
            # 全セッションを無効化
            success = await db_manager.invalidate_user_sessions(user_id)
            
            if success:
                # 各セッションの無効化ログ
                for session in active_sessions:
                    await logging_service.log_cognito_session_operation(
                        "cognito_user", "invalidated", "success",
                        {
                            "session_id": session['session_id'],
                            "reason": reason,
                            "batch_invalidation": True
                        },
                        user_id, ip_address
                    )
                
                logger.info(f"ユーザーの全セッションを無効化しました: {user_id} ({len(active_sessions)}件)")
                return len(active_sessions)
            
            return 0
            
        except Exception as e:
            logger.error(f"ユーザーセッション無効化エラー: {e}")
            return 0
    
    async def get_user_active_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        ユーザーのアクティブセッション一覧を取得
        
        Args:
            user_id: ユーザーID
            
        Returns:
            List[Dict]: アクティブセッション一覧
        """
        try:
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT session_id, created_at, last_activity, expires_at, 
                               client_ip, user_agent, cognito_user_sub
                        FROM user_sessions
                        WHERE user_id = %s AND is_active = TRUE
                        ORDER BY last_activity DESC
                    """, (user_id,))
                    
                    rows = await cursor.fetchall()
                    sessions = []
                    
                    current_time = datetime.utcnow()
                    
                    for row in rows:
                        session_dict = dict(row)
                        expires_at = session_dict['expires_at']
                        last_activity = session_dict['last_activity']
                        
                        session_dict.update({
                            'is_expired': current_time > expires_at,
                            'is_inactive': current_time > last_activity + timedelta(seconds=self.inactive_timeout),
                            'seconds_until_expiry': max(0, int((expires_at - current_time).total_seconds())),
                            'seconds_since_activity': int((current_time - last_activity).total_seconds())
                        })
                        
                        sessions.append(session_dict)
                    
                    return sessions
                    
        except Exception as e:
            logger.error(f"ユーザーアクティブセッション取得エラー: {e}")
            return []
    
    async def cleanup_expired_sessions(self) -> Dict[str, int]:
        """
        期限切れセッションの自動クリーンアップ
        
        Returns:
            Dict[str, int]: クリーンアップ結果
        """
        try:
            current_time = datetime.utcnow()
            
            # 期限切れセッションを取得
            expired_sessions = await self._get_expired_sessions()
            
            # 非アクティブセッションを取得
            inactive_sessions = await self._get_inactive_sessions()
            
            expired_count = 0
            inactive_count = 0
            
            # 期限切れセッションを無効化
            for session in expired_sessions:
                success = await self.invalidate_session(
                    session['session_id'], 
                    "expired", 
                    None
                )
                if success:
                    expired_count += 1
            
            # 非アクティブセッションを無効化
            for session in inactive_sessions:
                success = await self.invalidate_session(
                    session['session_id'], 
                    "inactive_timeout", 
                    None
                )
                if success:
                    inactive_count += 1
            
            total_cleaned = expired_count + inactive_count
            
            if total_cleaned > 0:
                logger.info(f"セッションクリーンアップ完了: 期限切れ {expired_count}件, 非アクティブ {inactive_count}件")
            
            return {
                'expired_count': expired_count,
                'inactive_count': inactive_count,
                'total_cleaned': total_cleaned
            }
            
        except Exception as e:
            logger.error(f"セッションクリーンアップエラー: {e}")
            return {
                'expired_count': 0,
                'inactive_count': 0,
                'total_cleaned': 0
            }
    
    async def _get_expired_sessions(self) -> List[Dict[str, Any]]:
        """期限切れセッションを取得"""
        try:
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT session_id, user_id, expires_at, cognito_user_sub
                        FROM user_sessions
                        WHERE expires_at < %s AND is_active = TRUE
                    """, (datetime.utcnow(),))
                    
                    return [dict(row) for row in await cursor.fetchall()]
                    
        except Exception as e:
            logger.error(f"期限切れセッション取得エラー: {e}")
            return []
    
    async def _get_inactive_sessions(self) -> List[Dict[str, Any]]:
        """非アクティブセッションを取得"""
        try:
            inactive_threshold = datetime.utcnow() - timedelta(seconds=self.inactive_timeout)
            
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT session_id, user_id, last_activity, cognito_user_sub
                        FROM user_sessions
                        WHERE last_activity < %s AND is_active = TRUE
                    """, (inactive_threshold,))
                    
                    return [dict(row) for row in await cursor.fetchall()]
                    
        except Exception as e:
            logger.error(f"非アクティブセッション取得エラー: {e}")
            return []
    
    async def extend_session(self, session_id: str, extension_hours: int = 24) -> Dict[str, Any]:
        """
        セッションの有効期限を延長
        
        Args:
            session_id: セッションID
            extension_hours: 延長時間（時間）
            
        Returns:
            Dict: 延長結果
        """
        try:
            # 現在のセッション情報を取得
            session_info = await self.get_session_info(session_id)
            if not session_info:
                return {
                    'success': False,
                    'error': 'session_not_found',
                    'message': 'セッションが見つかりません。'
                }
            
            # セッションがアクティブかチェック
            if not session_info['is_active']:
                return {
                    'success': False,
                    'error': 'session_inactive',
                    'message': 'セッションが無効です。'
                }
            
            # 新しい有効期限を計算
            new_expires_at = datetime.utcnow() + timedelta(hours=extension_hours)
            
            # セッションを延長
            success = await db_manager.extend_session(session_id, new_expires_at)
            
            if success:
                # セッション延長ログ
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "extended", "success",
                    {
                        "session_id": session_id,
                        "new_expires_at": new_expires_at.isoformat(),
                        "extension_hours": extension_hours
                    },
                    session_info['user_id'], None
                )
                
                logger.info(f"セッションを延長しました: {session_id} ({extension_hours}時間)")
                
                return {
                    'success': True,
                    'expires_at': new_expires_at.isoformat(),
                    'extension_hours': extension_hours,
                    'message': f'セッションを{extension_hours}時間延長しました。'
                }
            else:
                return {
                    'success': False,
                    'error': 'extension_failed',
                    'message': 'セッション延長に失敗しました。'
                }
                
        except Exception as e:
            logger.error(f"セッション延長エラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def get_session_statistics(self) -> Dict[str, Any]:
        """
        セッション統計情報を取得
        
        Returns:
            Dict: セッション統計
        """
        try:
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    # アクティブセッション数
                    await cursor.execute("""
                        SELECT COUNT(*) as active_count
                        FROM user_sessions
                        WHERE is_active = TRUE
                    """)
                    active_result = await cursor.fetchone()
                    
                    # 期限切れセッション数
                    await cursor.execute("""
                        SELECT COUNT(*) as expired_count
                        FROM user_sessions
                        WHERE expires_at < %s AND is_active = TRUE
                    """, (datetime.utcnow(),))
                    expired_result = await cursor.fetchone()
                    
                    # 非アクティブセッション数
                    inactive_threshold = datetime.utcnow() - timedelta(seconds=self.inactive_timeout)
                    await cursor.execute("""
                        SELECT COUNT(*) as inactive_count
                        FROM user_sessions
                        WHERE last_activity < %s AND is_active = TRUE
                    """, (inactive_threshold,))
                    inactive_result = await cursor.fetchone()
                    
                    # 今日作成されたセッション数
                    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                    await cursor.execute("""
                        SELECT COUNT(*) as today_count
                        FROM user_sessions
                        WHERE created_at >= %s
                    """, (today_start,))
                    today_result = await cursor.fetchone()
                    
                    return {
                        'active_sessions': active_result['active_count'],
                        'expired_sessions': expired_result['expired_count'],
                        'inactive_sessions': inactive_result['inactive_count'],
                        'sessions_created_today': today_result['today_count'],
                        'cleanup_interval_seconds': self.cleanup_interval,
                        'inactive_timeout_seconds': self.inactive_timeout,
                        'session_lifetime_seconds': self.session_lifetime,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"セッション統計取得エラー: {e}")
            return {
                'active_sessions': 0,
                'expired_sessions': 0,
                'inactive_sessions': 0,
                'sessions_created_today': 0,
                'error': str(e)
            }


# グローバルインスタンス
session_manager = SessionManager()