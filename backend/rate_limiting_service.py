"""
レート制限サービス - Cognito と連携したレート制限機能
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from database import db_manager
from logging_service import logging_service

logger = logging.getLogger(__name__)


class RateLimitingService:
    """レート制限サービスクラス"""
    
    def __init__(self):
        """レート制限サービスを初期化"""
        self.db = db_manager
        
        # メモリキャッシュ（本番環境ではRedisを推奨）
        self.rate_limit_cache = {}
        self.cognito_rate_cache = {}
    
    async def check_cognito_rate_limit(self, email: str, operation: str, 
                                     max_attempts: int = 5, 
                                     window_minutes: int = 30) -> Dict[str, Any]:
        """
        Cognito操作のレート制限をチェック
        
        Args:
            email: メールアドレス
            operation: 操作タイプ ("login", "register", "password_reset", etc.)
            max_attempts: 最大試行回数
            window_minutes: 時間窓（分）
            
        Returns:
            Dict: レート制限チェック結果
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=window_minutes)
            cache_key = f"{email}_{operation}"
            
            # 古いエントリをクリーンアップ
            if cache_key in self.cognito_rate_cache:
                self.cognito_rate_cache[cache_key] = [
                    attempt_time for attempt_time in self.cognito_rate_cache[cache_key]
                    if attempt_time > window_start
                ]
            
            # 現在の試行回数をチェック
            attempts = len(self.cognito_rate_cache.get(cache_key, []))
            
            if attempts >= max_attempts:
                # レート制限に達している
                oldest_attempt = min(self.cognito_rate_cache[cache_key])
                reset_time = oldest_attempt + timedelta(minutes=window_minutes)
                
                # セキュリティログを記録
                await logging_service.log_security_error(
                    email, "cognito_rate_limit_exceeded", 
                    {
                        "operation": operation,
                        "attempts": attempts,
                        "max_attempts": max_attempts,
                        "window_minutes": window_minutes,
                        "reset_time": reset_time.isoformat()
                    }
                )
                
                return {
                    'allowed': False,
                    'attempts': attempts,
                    'max_attempts': max_attempts,
                    'reset_time': reset_time.isoformat(),
                    'window_minutes': window_minutes,
                    'message': f'Cognito {operation} のレート制限に達しました。{window_minutes}分後に再試行してください。'
                }
            
            return {
                'allowed': True,
                'attempts': attempts,
                'max_attempts': max_attempts,
                'remaining': max_attempts - attempts,
                'window_minutes': window_minutes,
                'message': 'レート制限内です。'
            }
            
        except Exception as e:
            logger.error(f"Cognitoレート制限チェックエラー: {e}")
            # エラー時は安全側に倒してアクセスを許可
            return {
                'allowed': True,
                'attempts': 0,
                'max_attempts': max_attempts,
                'remaining': max_attempts,
                'message': 'レート制限チェックでエラーが発生しました。'
            }
    
    async def record_cognito_attempt(self, email: str, operation: str, 
                                   success: bool = True, ip_address: Optional[str] = None):
        """
        Cognito操作の試行を記録
        
        Args:
            email: メールアドレス
            operation: 操作タイプ
            success: 成功したかどうか
            ip_address: IPアドレス
        """
        try:
            current_time = datetime.utcnow()
            cache_key = f"{email}_{operation}"
            
            if cache_key not in self.cognito_rate_cache:
                self.cognito_rate_cache[cache_key] = []
            
            # 失敗した場合のみレート制限カウンターに追加
            if not success:
                self.cognito_rate_cache[cache_key].append(current_time)
                
                # ブルートフォース攻撃の検出
                await self._detect_brute_force_attack(email, operation, ip_address)
            
            # Cognitoログを記録
            await logging_service.log_cognito_operation(
                email, operation, 
                "success" if success else "failure",
                {
                    "timestamp": current_time.isoformat(),
                    "rate_limited": False
                },
                None, ip_address
            )
            
        except Exception as e:
            logger.error(f"Cognito試行記録エラー: {e}")

    async def _detect_brute_force_attack(self, email: str, operation: str, ip_address: Optional[str] = None):
        """
        ブルートフォース攻撃を検出
        
        Args:
            email: メールアドレス
            operation: 操作タイプ
            ip_address: IPアドレス
        """
        try:
            current_time = datetime.utcnow()
            
            # 過去15分間の失敗試行をチェック
            window_start = current_time - timedelta(minutes=15)
            cache_key = f"{email}_{operation}"
            
            if cache_key in self.cognito_rate_cache:
                recent_failures = [
                    attempt for attempt in self.cognito_rate_cache[cache_key]
                    if attempt > window_start
                ]
                
                # 15分間に10回以上の失敗でブルートフォース攻撃と判定
                if len(recent_failures) >= 10:
                    await logging_service.log_cognito_brute_force_attack(
                        email,
                        {
                            "operation": operation,
                            "attempt_count": len(recent_failures),
                            "time_window": "15_minutes",
                            "first_attempt": min(recent_failures).isoformat(),
                            "latest_attempt": max(recent_failures).isoformat(),
                            "attack_pattern": "rapid_failure_sequence"
                        },
                        None, ip_address
                    )
                    
                    logger.error(f"ブルートフォース攻撃を検出: {email} ({operation}) - {len(recent_failures)}回の失敗試行")
            
            # IPアドレスベースの攻撃検出
            if ip_address:
                await self._detect_ip_based_attack(ip_address, email, operation)
                
        except Exception as e:
            logger.error(f"ブルートフォース攻撃検出エラー: {e}")

    async def _detect_ip_based_attack(self, ip_address: str, email: str, operation: str):
        """
        IPアドレスベースの攻撃を検出
        
        Args:
            ip_address: IPアドレス
            email: メールアドレス
            operation: 操作タイプ
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=30)
            
            # 同一IPからの複数アカウントへの攻撃を検出
            ip_attempts = {}
            
            for cache_key, attempts in self.cognito_rate_cache.items():
                if operation in cache_key:
                    recent_attempts = [
                        attempt for attempt in attempts
                        if attempt > window_start
                    ]
                    
                    if recent_attempts:
                        # キャッシュキーからメールアドレスを抽出
                        target_email = cache_key.replace(f"_{operation}", "")
                        if target_email not in ip_attempts:
                            ip_attempts[target_email] = 0
                        ip_attempts[target_email] += len(recent_attempts)
            
            # 30分間に5つ以上の異なるアカウントに対する攻撃を検出
            if len(ip_attempts) >= 5:
                total_attempts = sum(ip_attempts.values())
                
                await logging_service.log_cognito_security_error(
                    "multiple_accounts", "credential_stuffing_attack",
                    {
                        "ip_address": ip_address,
                        "operation": operation,
                        "target_accounts": len(ip_attempts),
                        "total_attempts": total_attempts,
                        "time_window": "30_minutes",
                        "attack_pattern": "multiple_account_targeting",
                        "targeted_emails": list(ip_attempts.keys())[:10]  # 最初の10件のみ記録
                    },
                    None, ip_address
                )
                
                logger.error(f"クレデンシャルスタッフィング攻撃を検出: IP {ip_address} - {len(ip_attempts)}アカウントに対する攻撃")
                
        except Exception as e:
            logger.error(f"IPベース攻撃検出エラー: {e}")

    async def detect_suspicious_login_patterns(self, email: str, ip_address: Optional[str] = None) -> bool:
        """
        疑わしいログインパターンを検出
        
        Args:
            email: メールアドレス
            ip_address: IPアドレス
            
        Returns:
            bool: 疑わしいパターンが検出された場合 True
        """
        try:
            current_time = datetime.utcnow()
            
            # 過去1時間の成功ログインをチェック
            window_start = current_time - timedelta(hours=1)
            
            # 実際の実装では、データベースから成功ログインを取得する必要がある
            # ここでは簡略化してキャッシュベースで実装
            
            # 異常に高頻度のログイン（1時間に10回以上）
            login_cache_key = f"{email}_login_success"
            if login_cache_key not in self.rate_limit_cache:
                self.rate_limit_cache[login_cache_key] = []
            
            recent_logins = [
                login_time for login_time in self.rate_limit_cache[login_cache_key]
                if login_time > window_start
            ]
            
            if len(recent_logins) >= 10:
                await logging_service.log_cognito_security_error(
                    email, "suspicious_login_pattern",
                    {
                        "pattern_type": "high_frequency_login",
                        "login_count": len(recent_logins),
                        "time_window": "1_hour",
                        "first_login": min(recent_logins).isoformat(),
                        "latest_login": max(recent_logins).isoformat()
                    },
                    None, ip_address
                )
                
                logger.warning(f"疑わしいログインパターンを検出: {email} - 1時間に{len(recent_logins)}回のログイン")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"疑わしいログインパターン検出エラー: {e}")
            return False

    async def record_successful_login(self, email: str, ip_address: Optional[str] = None):
        """
        成功したログインを記録（パターン検出用）
        
        Args:
            email: メールアドレス
            ip_address: IPアドレス
        """
        try:
            current_time = datetime.utcnow()
            login_cache_key = f"{email}_login_success"
            
            if login_cache_key not in self.rate_limit_cache:
                self.rate_limit_cache[login_cache_key] = []
            
            self.rate_limit_cache[login_cache_key].append(current_time)
            
            # 疑わしいパターンをチェック
            await self.detect_suspicious_login_patterns(email, ip_address)
            
        except Exception as e:
            logger.error(f"成功ログイン記録エラー: {e}")
    
    async def check_ip_rate_limit(self, ip_address: str, endpoint: str,
                                max_requests: int = 100, 
                                window_minutes: int = 60) -> Dict[str, Any]:
        """
        IPアドレスベースのレート制限をチェック
        
        Args:
            ip_address: IPアドレス
            endpoint: エンドポイント名
            max_requests: 最大リクエスト数
            window_minutes: 時間窓（分）
            
        Returns:
            Dict: レート制限チェック結果
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=window_minutes)
            cache_key = f"{ip_address}_{endpoint}"
            
            # 古いエントリをクリーンアップ
            if cache_key in self.rate_limit_cache:
                self.rate_limit_cache[cache_key] = [
                    request_time for request_time in self.rate_limit_cache[cache_key]
                    if request_time > window_start
                ]
            
            # 現在のリクエスト数をチェック
            requests = len(self.rate_limit_cache.get(cache_key, []))
            
            if requests >= max_requests:
                # レート制限に達している
                oldest_request = min(self.rate_limit_cache[cache_key])
                reset_time = oldest_request + timedelta(minutes=window_minutes)
                
                # セキュリティログを記録
                await logging_service.log_security_error(
                    "unknown", "ip_rate_limit_exceeded", 
                    {
                        "ip_address": ip_address,
                        "endpoint": endpoint,
                        "requests": requests,
                        "max_requests": max_requests,
                        "window_minutes": window_minutes,
                        "reset_time": reset_time.isoformat()
                    },
                    None, ip_address
                )
                
                return {
                    'allowed': False,
                    'requests': requests,
                    'max_requests': max_requests,
                    'reset_time': reset_time.isoformat(),
                    'window_minutes': window_minutes,
                    'message': f'IPアドレス {ip_address} のレート制限に達しました。{window_minutes}分後に再試行してください。'
                }
            
            return {
                'allowed': True,
                'requests': requests,
                'max_requests': max_requests,
                'remaining': max_requests - requests,
                'window_minutes': window_minutes,
                'message': 'レート制限内です。'
            }
            
        except Exception as e:
            logger.error(f"IPレート制限チェックエラー: {e}")
            # エラー時は安全側に倒してアクセスを許可
            return {
                'allowed': True,
                'requests': 0,
                'max_requests': max_requests,
                'remaining': max_requests,
                'message': 'レート制限チェックでエラーが発生しました。'
            }
    
    async def record_ip_request(self, ip_address: str, endpoint: str):
        """
        IPアドレスのリクエストを記録
        
        Args:
            ip_address: IPアドレス
            endpoint: エンドポイント名
        """
        try:
            current_time = datetime.utcnow()
            cache_key = f"{ip_address}_{endpoint}"
            
            if cache_key not in self.rate_limit_cache:
                self.rate_limit_cache[cache_key] = []
            
            self.rate_limit_cache[cache_key].append(current_time)
            
        except Exception as e:
            logger.error(f"IPリクエスト記録エラー: {e}")
    
    async def check_user_rate_limit(self, user_id: str, operation: str,
                                  max_operations: int = 50, 
                                  window_minutes: int = 60) -> Dict[str, Any]:
        """
        ユーザーベースのレート制限をチェック
        
        Args:
            user_id: ユーザーID
            operation: 操作タイプ
            max_operations: 最大操作数
            window_minutes: 時間窓（分）
            
        Returns:
            Dict: レート制限チェック結果
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=window_minutes)
            cache_key = f"user_{user_id}_{operation}"
            
            # 古いエントリをクリーンアップ
            if cache_key in self.rate_limit_cache:
                self.rate_limit_cache[cache_key] = [
                    operation_time for operation_time in self.rate_limit_cache[cache_key]
                    if operation_time > window_start
                ]
            
            # 現在の操作数をチェック
            operations = len(self.rate_limit_cache.get(cache_key, []))
            
            if operations >= max_operations:
                # レート制限に達している
                oldest_operation = min(self.rate_limit_cache[cache_key])
                reset_time = oldest_operation + timedelta(minutes=window_minutes)
                
                # セキュリティログを記録
                await logging_service.log_security_error(
                    "unknown", "user_rate_limit_exceeded", 
                    {
                        "user_id": user_id,
                        "operation": operation,
                        "operations": operations,
                        "max_operations": max_operations,
                        "window_minutes": window_minutes,
                        "reset_time": reset_time.isoformat()
                    },
                    user_id
                )
                
                return {
                    'allowed': False,
                    'operations': operations,
                    'max_operations': max_operations,
                    'reset_time': reset_time.isoformat(),
                    'window_minutes': window_minutes,
                    'message': f'ユーザー {operation} のレート制限に達しました。{window_minutes}分後に再試行してください。'
                }
            
            return {
                'allowed': True,
                'operations': operations,
                'max_operations': max_operations,
                'remaining': max_operations - operations,
                'window_minutes': window_minutes,
                'message': 'レート制限内です。'
            }
            
        except Exception as e:
            logger.error(f"ユーザーレート制限チェックエラー: {e}")
            # エラー時は安全側に倒してアクセスを許可
            return {
                'allowed': True,
                'operations': 0,
                'max_operations': max_operations,
                'remaining': max_operations,
                'message': 'レート制限チェックでエラーが発生しました。'
            }
    
    async def record_user_operation(self, user_id: str, operation: str):
        """
        ユーザーの操作を記録
        
        Args:
            user_id: ユーザーID
            operation: 操作タイプ
        """
        try:
            current_time = datetime.utcnow()
            cache_key = f"user_{user_id}_{operation}"
            
            if cache_key not in self.rate_limit_cache:
                self.rate_limit_cache[cache_key] = []
            
            self.rate_limit_cache[cache_key].append(current_time)
            
        except Exception as e:
            logger.error(f"ユーザー操作記録エラー: {e}")
    
    async def get_rate_limit_status(self, identifier: str, 
                                  identifier_type: str = "email") -> Dict[str, Any]:
        """
        レート制限の状態を取得
        
        Args:
            identifier: 識別子（メールアドレス、IPアドレス、ユーザーIDなど）
            identifier_type: 識別子タイプ ("email", "ip", "user")
            
        Returns:
            Dict: レート制限状態
        """
        try:
            current_time = datetime.utcnow()
            status = {
                'identifier': identifier,
                'identifier_type': identifier_type,
                'current_time': current_time.isoformat(),
                'limits': []
            }
            
            # 該当するキャッシュエントリを検索
            cache_to_check = self.cognito_rate_cache if identifier_type == "email" else self.rate_limit_cache
            
            for cache_key, attempts in cache_to_check.items():
                if identifier in cache_key:
                    # 1時間以内のエントリのみ
                    recent_attempts = [
                        attempt for attempt in attempts
                        if attempt > current_time - timedelta(hours=1)
                    ]
                    
                    if recent_attempts:
                        status['limits'].append({
                            'cache_key': cache_key,
                            'recent_attempts': len(recent_attempts),
                            'oldest_attempt': min(recent_attempts).isoformat(),
                            'newest_attempt': max(recent_attempts).isoformat()
                        })
            
            return status
            
        except Exception as e:
            logger.error(f"レート制限状態取得エラー: {e}")
            return {
                'identifier': identifier,
                'identifier_type': identifier_type,
                'error': str(e),
                'limits': []
            }
    
    async def cleanup_expired_entries(self):
        """
        期限切れのレート制限エントリをクリーンアップ
        """
        try:
            current_time = datetime.utcnow()
            cutoff_time = current_time - timedelta(hours=24)
            
            # Cognitoレートキャッシュのクリーンアップ
            for cache_key in list(self.cognito_rate_cache.keys()):
                self.cognito_rate_cache[cache_key] = [
                    attempt for attempt in self.cognito_rate_cache[cache_key]
                    if attempt > cutoff_time
                ]
                
                # 空のエントリを削除
                if not self.cognito_rate_cache[cache_key]:
                    del self.cognito_rate_cache[cache_key]
            
            # 一般レートキャッシュのクリーンアップ
            for cache_key in list(self.rate_limit_cache.keys()):
                self.rate_limit_cache[cache_key] = [
                    attempt for attempt in self.rate_limit_cache[cache_key]
                    if attempt > cutoff_time
                ]
                
                # 空のエントリを削除
                if not self.rate_limit_cache[cache_key]:
                    del self.rate_limit_cache[cache_key]
            
            logger.info("レート制限キャッシュのクリーンアップが完了しました")
            
        except Exception as e:
            logger.error(f"レート制限クリーンアップエラー: {e}")


# グローバルインスタンス
rate_limiting_service = RateLimitingService()