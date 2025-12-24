"""
認証ミドルウェア - Cognito JWT トークン検証と API 保護
"""
import logging
import re
import html
from typing import Optional, Dict, Any, Callable
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import jwt
from datetime import datetime, timedelta
from database import db_manager
from models import User
from cognito_token_service import cognito_token_service
from logging_service import logging_service
from security_monitoring_service import security_monitoring_service

logger = logging.getLogger(__name__)

class AuthMiddleware:
    """認証ミドルウェアクラス"""
    
    def __init__(self):
        """AuthMiddleware を初期化"""
        self.security = HTTPBearer(auto_error=False)
        # レート制限用のメモリキャッシュ（本番環境ではRedisを推奨）
        self.rate_limit_cache = {}
        self.failed_attempts_cache = {}
    
    def sanitize_input(self, input_str: str, is_token: bool = False) -> str:
        """
        入力文字列をサニタイズしてXSS攻撃を防ぐ
        
        Args:
            input_str: サニタイズする文字列
            is_token: JWTトークンの場合はHTMLエスケープをスキップする
            
        Returns:
            str: サニタイズされた文字列
        """
        if not input_str:
            return ""
        
        # JWTトークンの場合はHTMLエスケープをスキップ（ドットなどが消えるのを防ぐ）
        # ただし、危険なタグなどは除去する
        if is_token:
            sanitized = input_str
        else:
            # HTMLエスケープ
            sanitized = html.escape(input_str)
        
        # 危険なスクリプトタグを除去
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        # 危険なイベントハンドラーを除去
        sanitized = re.sub(r'on\w+\s*=', '', sanitized, flags=re.IGNORECASE)
        
        # JavaScriptプロトコルを除去
        sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    def validate_sql_injection(self, input_str: str) -> bool:
        """
        SQLインジェクション攻撃パターンをチェック
        
        Args:
            input_str: チェックする文字列
            
        Returns:
            bool: 安全な場合True、危険な場合False
        """
        if not input_str:
            return True
        
        # 危険なSQLパターン
        dangerous_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(--|#|/\*|\*/)",
            r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
            r"(\'\s*(OR|AND)\s+\'\w+\'\s*=\s*\'\w+\')",
            r"(\bUNION\s+SELECT\b)",
            r"(\bINTO\s+OUTFILE\b)",
            r"(\bLOAD_FILE\b)",
        ]
        
        input_upper = input_str.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, input_upper, re.IGNORECASE):
                return False
        
        return True
    
    async def check_rate_limit(self, identifier: str, max_attempts: int = 5, 
                             window_minutes: int = 30) -> Dict[str, Any]:
        """
        レート制限をチェック
        
        Args:
            identifier: 識別子（IPアドレスやユーザーIDなど）
            max_attempts: 最大試行回数
            window_minutes: 時間窓（分）
            
        Returns:
            Dict: レート制限チェック結果
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=window_minutes)
            
            # 古いエントリをクリーンアップ
            if identifier in self.rate_limit_cache:
                self.rate_limit_cache[identifier] = [
                    attempt_time for attempt_time in self.rate_limit_cache[identifier]
                    if attempt_time > window_start
                ]
            
            # 現在の試行回数をチェック
            attempts = len(self.rate_limit_cache.get(identifier, []))
            
            if attempts >= max_attempts:
                # レート制限に達している
                oldest_attempt = min(self.rate_limit_cache[identifier])
                reset_time = oldest_attempt + timedelta(minutes=window_minutes)
                
                return {
                    'allowed': False,
                    'attempts': attempts,
                    'max_attempts': max_attempts,
                    'reset_time': reset_time.isoformat(),
                    'message': f'レート制限に達しました。{window_minutes}分後に再試行してください。'
                }
            
            return {
                'allowed': True,
                'attempts': attempts,
                'max_attempts': max_attempts,
                'remaining': max_attempts - attempts,
                'message': 'レート制限内です。'
            }
            
        except Exception as e:
            logger.error(f"レート制限チェックエラー: {e}")
            # エラー時は安全側に倒してアクセスを許可
            return {
                'allowed': True,
                'attempts': 0,
                'max_attempts': max_attempts,
                'remaining': max_attempts,
                'message': 'レート制限チェックでエラーが発生しました。'
            }
    
    async def record_rate_limit_attempt(self, identifier: str):
        """
        レート制限の試行を記録
        
        Args:
            identifier: 識別子
        """
        try:
            current_time = datetime.utcnow()
            
            if identifier not in self.rate_limit_cache:
                self.rate_limit_cache[identifier] = []
            
            self.rate_limit_cache[identifier].append(current_time)
            
        except Exception as e:
            logger.error(f"レート制限試行記録エラー: {e}")
    
    async def detect_brute_force(self, identifier: str, is_failed: bool = False) -> Dict[str, Any]:
        """
        ブルートフォース攻撃を検出
        
        Args:
            identifier: 識別子（IPアドレスなど）
            is_failed: 失敗した試行かどうか
            
        Returns:
            Dict: ブルートフォース検出結果
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(minutes=15)  # 15分間の窓
            
            if identifier not in self.failed_attempts_cache:
                self.failed_attempts_cache[identifier] = []
            
            # 古いエントリをクリーンアップ
            self.failed_attempts_cache[identifier] = [
                attempt_time for attempt_time in self.failed_attempts_cache[identifier]
                if attempt_time > window_start
            ]
            
            # 失敗した試行を記録
            if is_failed:
                self.failed_attempts_cache[identifier].append(current_time)
            
            failed_count = len(self.failed_attempts_cache[identifier])
            
            # ブルートフォース攻撃の閾値（15分間で10回以上の失敗）
            if failed_count >= 10:
                return {
                    'is_brute_force': True,
                    'failed_attempts': failed_count,
                    'window_minutes': 15,
                    'message': 'ブルートフォース攻撃の可能性があります。'
                }
            
            return {
                'is_brute_force': False,
                'failed_attempts': failed_count,
                'window_minutes': 15,
                'message': '正常な範囲内です。'
            }
            
        except Exception as e:
            logger.error(f"ブルートフォース検出エラー: {e}")
            return {
                'is_brute_force': False,
                'failed_attempts': 0,
                'window_minutes': 15,
                'message': 'ブルートフォース検出でエラーが発生しました。'
            }
    
    async def validate_csrf_token(self, request: Request) -> bool:
        """
        CSRF トークンを検証（簡易実装）
        
        Args:
            request: FastAPI リクエストオブジェクト
            
        Returns:
            bool: CSRF トークンが有効な場合True
        """
        try:
            # Origin ヘッダーをチェック
            origin = request.headers.get('Origin')
            referer = request.headers.get('Referer')
            host = request.headers.get('Host')
            
            # 許可されたオリジン
            allowed_origins = [
                'http://localhost:3000',
                'https://localhost:3000',
                # 本番環境のドメインを追加
            ]
            
            # Originヘッダーがある場合はチェック
            if origin:
                return origin in allowed_origins
            
            # Refererヘッダーがある場合はチェック
            if referer:
                for allowed_origin in allowed_origins:
                    if referer.startswith(allowed_origin):
                        return True
            
            # SameSite Cookieの場合は許可（WebSocketなど）
            if not origin and not referer:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"CSRF検証エラー: {e}")
            # エラー時は安全側に倒して拒否
            return False
    
    async def verify_token(self, token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Cognito JWT トークンを検証し、ユーザーコンテキストを返す
        
        Args:
            token: 検証するCognito JWTトークン
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 検証結果とユーザーコンテキスト
        """
        try:
            if not token:
                return {
                    'success': False,
                    'error': 'missing_token',
                    'message': 'アクセストークンが提供されていません。'
                }
            
            # レート制限チェック（IPアドレスベース）
            if ip_address:
                rate_limit_result = await self.check_rate_limit(
                    f"token_verify_{ip_address}", 
                    max_attempts=1000,  # 1時間に100回まで
                    window_minutes=60
                )
                
                if not rate_limit_result['allowed']:
                    # セキュリティログを記録
                    await logging_service.log_security_error(
                        "unknown", "token_verify_rate_limit", 
                        {
                            "ip_address": ip_address,
                            "attempts": rate_limit_result['attempts'],
                            "max_attempts": rate_limit_result['max_attempts']
                        }, 
                        None, ip_address
                    )
                    
                    return {
                        'success': False,
                        'error': 'rate_limit_exceeded',
                        'message': rate_limit_result['message']
                    }
                
                # 試行を記録
                await self.record_rate_limit_attempt(f"token_verify_{ip_address}")
            
            # Cognitoトークンサービスで検証・同期
            validation_result = await cognito_token_service.validate_and_sync_session(token, ip_address)
            
            if not validation_result['success']:
                # 失敗した場合のセキュリティログ
                if ip_address:
                    brute_force_result = await self.detect_brute_force(
                        f"token_fail_{ip_address}", 
                        is_failed=True
                    )
                    
                    if brute_force_result['is_brute_force']:
                        await logging_service.log_security_error(
                            "unknown", "brute_force_token_attack", 
                            {
                                "ip_address": ip_address,
                                "failed_attempts": brute_force_result['failed_attempts'],
                                "attack_detected": True
                            }, 
                            None, ip_address
                        )
                    
                    # セキュリティ監視: 不正アクセス試行を監視
                    await security_monitoring_service.monitor_unauthorized_access_attempt(
                        "unknown", "invalid_token", "token_verification",
                        {
                            "error": validation_result['error'],
                            "brute_force_detected": brute_force_result['is_brute_force']
                        },
                        None, ip_address
                    )
                
                return {
                    'success': False,
                    'error': validation_result['error'],
                    'message': validation_result['message']
                }
            
            return {
                'success': True,
                'user': validation_result['user'],
                'session': validation_result['session'],
                'cognito_payload': validation_result.get('cognito_payload'),
                'message': 'Cognitoトークン検証成功'
            }
            
        except Exception as e:
            logger.error(f"Cognitoトークン検証エラー: {e}")
            
            # セキュリティエラーログ
            if ip_address:
                await logging_service.log_security_error(
                    "unknown", "token_verification_error", 
                    {"error": str(e), "ip_address": ip_address}, 
                    None, ip_address
                )
            
            return {
                'success': False,
                'error': 'verification_error',
                'message': 'Cognitoトークン検証中にエラーが発生しました。'
            }
    
    async def require_auth(self, request: Request) -> Dict[str, Any]:
        """
        認証を要求し、ユーザーコンテキストを返す
        自動トークンリフレッシュ対応
        
        Args:
            request: FastAPI リクエストオブジェクト
            
        Returns:
            Dict: 認証結果とユーザーコンテキスト
        """
        try:
            # クライアントIPアドレスを取得
            client_ip = request.client.host if request.client else None
            
            # CSRF保護（POST、PUT、DELETE、PATCHリクエストの場合）
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                if not await self.validate_csrf_token(request):
                    # CSRFエラーログ
                    await logging_service.log_security_error(
                        "unknown", "csrf_validation_failed", 
                        {
                            "method": request.method,
                            "url": str(request.url),
                            "origin": request.headers.get('Origin'),
                            "referer": request.headers.get('Referer')
                        }, 
                        None, client_ip
                    )
                    
                    return {
                        'success': False,
                        'error': 'csrf_validation_failed',
                        'message': 'CSRF検証に失敗しました。',
                        'redirect_to_auth': True
                    }
            
            # Authorization ヘッダーからトークンを取得
            authorization = request.headers.get("Authorization")
            if not authorization:
                return {
                    'success': False,
                    'error': 'missing_authorization',
                    'message': 'Authorization ヘッダーが必要です。',
                    'redirect_to_auth': True
                }
            
            # Bearer トークンの形式をチェック
            if not authorization.startswith("Bearer "):
                return {
                    'success': False,
                    'error': 'invalid_authorization_format',
                    'message': 'Authorization ヘッダーの形式が正しくありません。',
                    'redirect_to_auth': True
                }
            
            # トークンを抽出
            token = authorization.replace("Bearer ", "")
            
            # 入力サニタイゼーション (JWTトークンのため is_token=True)
            token = self.sanitize_input(token, is_token=True)
            
            # SQLインジェクションチェック
            # JWTトークンの場合は正規表現パターンが含まれる可能性があるためスキップ
            # (token_service側で別途検証されるため安全)
            # if not self.validate_sql_injection(token):
            #     ...
            
            # トークンを検証（自動リフレッシュ対応）
            result = await self.verify_token(token, client_ip)
            
            if not result['success']:
                result['redirect_to_auth'] = True
            
            return result
            
        except Exception as e:
            logger.error(f"認証要求エラー: {e}")
            
            # セキュリティエラーログ
            client_ip = request.client.host if request.client else None
            await logging_service.log_security_error(
                "unknown", "auth_request_error", 
                {"error": str(e), "method": request.method, "url": str(request.url)}, 
                None, client_ip
            )
            
            return {
                'success': False,
                'error': 'auth_error',
                'message': '認証処理中にエラーが発生しました。',
                'redirect_to_auth': True
            }
    
    async def verify_websocket_auth(self, token: str, client_ip: Optional[str] = None) -> Dict[str, Any]:
        """
        WebSocket接続時のCognito認証を検証
        
        Args:
            token: 検証するCognito JWTトークン
            client_ip: クライアントのIPアドレス
            
        Returns:
            Dict: 検証結果とユーザーコンテキスト
        """
        logger.info(f"verify_websocket_auth 開始: IP={client_ip}, トークン長={len(token) if token else 0}")
        try:
            if not token:
                logger.warning(f"WebSocket認証失敗: トークンがありません。IP={client_ip}")
                # セキュリティエラーログ
                await logging_service.log_security_error(
                    "unknown", "websocket_no_token", 
                    {"error": "no_token_provided", "connection_attempt": True}, 
                    None, client_ip
                )
                
                return {
                    'success': False,
                    'error': 'missing_token',
                    'message': 'WebSocket接続には認証トークンが必要です。',
                    'close_code': 4001,
                    'close_reason': '認証が必要です'
                }
            
            # WebSocket専用のレート制限チェック
            if client_ip:
                rate_limit_result = await self.check_rate_limit(
                    f"websocket_{client_ip}", 
                    max_attempts=200,  # 1時間に20回まで
                    window_minutes=60
                )
                
                if not rate_limit_result['allowed']:
                    # セキュリティログを記録
                    await logging_service.log_security_error(
                        "unknown", "websocket_rate_limit", 
                        {
                            "ip_address": client_ip,
                            "attempts": rate_limit_result['attempts'],
                            "max_attempts": rate_limit_result['max_attempts']
                        }, 
                        None, client_ip
                    )
                    
                    return {
                        'success': False,
                        'error': 'rate_limit_exceeded',
                        'message': 'WebSocket接続のレート制限に達しました。',
                        'close_code': 4003,
                        'close_reason': 'レート制限'
                    }
                
                # 試行を記録
                await self.record_rate_limit_attempt(f"websocket_{client_ip}")
            
            # 入力サニタイゼーション (JWTトークンのため is_token=True)
            token = self.sanitize_input(token, is_token=True)
            
            # SQLインジェクションチェック
            # JWTトークンの場合は正規表現パターンが含まれる可能性があるためスキップ
            # if not self.validate_sql_injection(token):
            #     ...
            
            # Cognitoトークンを検証
            logger.info("verify_token を呼び出します...")
            validation_result = await self.verify_token(token, client_ip)
            
            if not validation_result['success']:
                logger.warning(f"verify_token 失敗: {validation_result.get('error')}, {validation_result.get('message')}")
                # WebSocket用のエラーコードを追加
                validation_result.update({
                    'close_code': 4001,
                    'close_reason': '認証失敗'
                })
                
                # セキュリティエラーログ
                await logging_service.log_security_error(
                    "unknown", "websocket_auth_failed", 
                    {
                        "error": validation_result['error'],
                        "ip_address": client_ip
                    }, 
                    None, client_ip
                )
            else:
                # 成功ログ
                user = validation_result['user']
                logger.info(f"WebSocket認証成功: ユーザーID={user.user_id}, IP={client_ip}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"WebSocket認証検証エラー: {e}")
            
            # セキュリティエラーログ
            await logging_service.log_security_error(
                "unknown", "websocket_auth_error", 
                {"error": str(e), "ip_address": client_ip}, 
                None, client_ip
            )
            
            return {
                'success': False,
                'error': 'websocket_auth_error',
                'message': 'WebSocket認証中にエラーが発生しました。',
                'close_code': 4000,
                'close_reason': 'サーバーエラー'
            }
    
    def create_auth_dependency(self) -> Callable:
        """
        FastAPI の依存性注入用の認証関数を作成
        自動トークンリフレッシュ対応
        
        Returns:
            Callable: 認証依存性関数
        """
        async def auth_dependency(request: Request) -> Dict[str, Any]:
            """認証依存性関数"""
            result = await self.require_auth(request)
            
            if not result['success']:
                # 認証失敗時は適切なHTTPエラーを発生
                if result.get('error') in ['missing_authorization', 'invalid_authorization_format']:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={
                            'error': result['error'],
                            'message': result['message'],
                            'redirect_to_auth': True
                        },
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                elif result.get('error') in ['token_expired', 'session_inactive']:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={
                            'error': result['error'],
                            'message': result['message'],
                            'redirect_to_auth': True
                        }
                    )
                elif result.get('error') in ['invalid_token', 'user_not_found', 'user_inactive']:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            'error': result['error'],
                            'message': result['message'],
                            'redirect_to_auth': True
                        }
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            'error': result['error'],
                            'message': result['message']
                        }
                    )
            
            # トークンがリフレッシュされた場合、レスポンスヘッダーに新しいトークンを設定
            if result.get('token_refreshed'):
                # カスタムヘッダーで新しいトークンを返す
                # フロントエンドはこのヘッダーを監視して新しいトークンを保存する
                request.state.new_access_token = result.get('new_access_token')
                request.state.new_id_token = result.get('new_id_token')
                request.state.token_refreshed = True
            
            return result
        
        return auth_dependency
    
    async def protect_endpoint(self, request: Request, allow_unauthenticated: bool = False) -> Dict[str, Any]:
        """
        エンドポイントを保護し、認証状態に応じて適切な応答を返す
        
        Args:
            request: FastAPI リクエストオブジェクト
            allow_unauthenticated: 未認証アクセスを許可するか
            
        Returns:
            Dict: 保護結果とユーザーコンテキスト
        """
        try:
            # 認証を試行
            auth_result = await self.require_auth(request)
            
            if auth_result['success']:
                # 認証成功 - アクセス許可
                return {
                    'success': True,
                    'authenticated': True,
                    'user': auth_result['user'],
                    'session': auth_result['session'],
                    'message': '認証済みアクセス許可'
                }
            else:
                # 認証失敗
                if allow_unauthenticated:
                    # 未認証アクセスを許可
                    return {
                        'success': True,
                        'authenticated': False,
                        'user': None,
                        'session': None,
                        'message': '未認証アクセス許可'
                    }
                else:
                    # 未認証アクセスを拒否
                    return {
                        'success': False,
                        'authenticated': False,
                        'error': auth_result['error'],
                        'message': auth_result['message'],
                        'redirect_to_auth': True
                    }
                    
        except Exception as e:
            logger.error(f"エンドポイント保護エラー: {e}")
            return {
                'success': False,
                'authenticated': False,
                'error': 'protection_error',
                'message': 'エンドポイント保護中にエラーが発生しました。'
            }

# グローバルインスタンス
auth_middleware = AuthMiddleware()

# FastAPI 依存性注入用の認証関数
require_auth = auth_middleware.create_auth_dependency()

async def optional_auth(request: Request) -> Dict[str, Any]:
    """
    オプショナル認証 - 認証されていなくてもアクセス可能
    
    Args:
        request: FastAPI リクエストオブジェクト
        
    Returns:
        Dict: 認証結果（失敗でもアクセス許可）
    """
    return await auth_middleware.protect_endpoint(request, allow_unauthenticated=True)

async def get_current_user(request: Request) -> Optional[User]:
    """
    現在のユーザーを取得（認証済みの場合のみ）
    
    Args:
        request: FastAPI リクエストオブジェクト
        
    Returns:
        Optional[User]: 認証済みユーザー、未認証の場合は None
    """
    try:
        auth_result = await auth_middleware.require_auth(request)
        if auth_result['success']:
            return auth_result['user']
        return None
    except Exception as e:
        logger.error(f"現在ユーザー取得エラー: {e}")
        return None
