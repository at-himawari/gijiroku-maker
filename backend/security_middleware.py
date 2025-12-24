"""
セキュリティミドルウェア - SQL インジェクション、XSS、CSRF 対策
"""
import logging
import re
import html
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from logging_service import logging_service

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """セキュリティミドルウェアクラス"""
    
    def __init__(self, app, allowed_origins: Optional[List[str]] = None):
        """
        セキュリティミドルウェアを初期化
        
        Args:
            app: FastAPI アプリケーション
            allowed_origins: 許可されたオリジンのリスト
        """
        super().__init__(app)
        self.allowed_origins = allowed_origins or [
            'http://localhost:3000',
            'https://localhost:3000'
        ]
        
        # セキュリティイベントのキャッシュ（本番環境ではRedisを推奨）
        self.security_events_cache = {}
        
        # 危険なSQLパターン
        self.sql_injection_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(--|#|/\*|\*/)",
            r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
            r"(\'\s*(OR|AND)\s+\'\w+\'\s*=\s*\'\w+\')",
            r"(\bUNION\s+SELECT\b)",
            r"(\bINTO\s+OUTFILE\b)",
            r"(\bLOAD_FILE\b)",
            r"(\bINTO\s+DUMPFILE\b)",
            r"(\bSLEEP\s*\()",
            r"(\bBENCHMARK\s*\()",
            r"(\bEXTRACTVALUE\s*\()",
            r"(\bUPDATEXML\s*\()",
        ]
        
        # 危険なXSSパターン
        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"on\w+\s*=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
            r"<link[^>]*>",
            r"<meta[^>]*>",
            r"<style[^>]*>.*?</style>",
        ]
    
    def sanitize_input(self, input_str: str) -> str:
        """
        入力文字列をサニタイズしてXSS攻撃を防ぐ
        
        Args:
            input_str: サニタイズする文字列
            
        Returns:
            str: サニタイズされた文字列
        """
        if not input_str or not isinstance(input_str, str):
            return ""
        
        # HTMLエスケープ
        sanitized = html.escape(input_str)
        
        # 危険なXSSパターンを除去
        for pattern in self.xss_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        return sanitized
    
    def detect_sql_injection(self, input_str: str) -> Dict[str, Any]:
        """
        SQLインジェクション攻撃パターンを検出
        
        Args:
            input_str: チェックする文字列
            
        Returns:
            Dict: 検出結果
        """
        if not input_str or not isinstance(input_str, str):
            return {'detected': False, 'patterns': []}
        
        detected_patterns = []
        input_upper = input_str.upper()
        
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, input_upper, re.IGNORECASE):
                detected_patterns.append(pattern)
        
        return {
            'detected': len(detected_patterns) > 0,
            'patterns': detected_patterns,
            'input_preview': input_str[:100] + "..." if len(input_str) > 100 else input_str
        }
    
    def detect_xss_attack(self, input_str: str) -> Dict[str, Any]:
        """
        XSS攻撃パターンを検出
        
        Args:
            input_str: チェックする文字列
            
        Returns:
            Dict: 検出結果
        """
        if not input_str or not isinstance(input_str, str):
            return {'detected': False, 'patterns': []}
        
        detected_patterns = []
        
        for pattern in self.xss_patterns:
            if re.search(pattern, input_str, re.IGNORECASE | re.DOTALL):
                detected_patterns.append(pattern)
        
        return {
            'detected': len(detected_patterns) > 0,
            'patterns': detected_patterns,
            'input_preview': input_str[:100] + "..." if len(input_str) > 100 else input_str
        }
    
    def validate_csrf_token(self, request: Request) -> Dict[str, Any]:
        """
        CSRF トークンを検証
        
        Args:
            request: FastAPI リクエストオブジェクト
            
        Returns:
            Dict: CSRF検証結果
        """
        try:
            # Origin ヘッダーをチェック
            origin = request.headers.get('Origin')
            referer = request.headers.get('Referer')
            host = request.headers.get('Host')
            
            # Originヘッダーがある場合はチェック
            if origin:
                if origin in self.allowed_origins:
                    return {'valid': True, 'method': 'origin_header'}
                else:
                    return {
                        'valid': False, 
                        'method': 'origin_header',
                        'origin': origin,
                        'allowed_origins': self.allowed_origins
                    }
            
            # Refererヘッダーがある場合はチェック
            if referer:
                for allowed_origin in self.allowed_origins:
                    if referer.startswith(allowed_origin):
                        return {'valid': True, 'method': 'referer_header'}
                
                return {
                    'valid': False, 
                    'method': 'referer_header',
                    'referer': referer,
                    'allowed_origins': self.allowed_origins
                }
            
            # SameSite Cookieの場合やWebSocketなどは許可
            if not origin and not referer:
                return {'valid': True, 'method': 'no_headers'}
            
            return {
                'valid': False, 
                'method': 'unknown',
                'origin': origin,
                'referer': referer
            }
            
        except Exception as e:
            logger.error(f"CSRF検証エラー: {e}")
            return {
                'valid': False, 
                'method': 'error',
                'error': str(e)
            }
    
    async def record_security_event(self, event_type: str, client_ip: str, 
                                  details: Dict[str, Any]):
        """
        セキュリティイベントを記録
        
        Args:
            event_type: イベントタイプ
            client_ip: クライアントIPアドレス
            details: イベント詳細
        """
        try:
            current_time = datetime.utcnow()
            
            # イベントキャッシュに記録
            if client_ip not in self.security_events_cache:
                self.security_events_cache[client_ip] = []
            
            self.security_events_cache[client_ip].append({
                'event_type': event_type,
                'timestamp': current_time,
                'details': details
            })
            
            # 古いイベントをクリーンアップ（24時間以上前）
            cutoff_time = current_time - timedelta(hours=24)
            self.security_events_cache[client_ip] = [
                event for event in self.security_events_cache[client_ip]
                if event['timestamp'] > cutoff_time
            ]
            
            # ログサービスに記録
            await logging_service.log_security_error(
                "unknown", event_type, details, None, client_ip
            )
            
        except Exception as e:
            logger.error(f"セキュリティイベント記録エラー: {e}")
    
    async def check_security_threshold(self, client_ip: str) -> Dict[str, Any]:
        """
        セキュリティイベントの閾値をチェック
        
        Args:
            client_ip: クライアントIPアドレス
            
        Returns:
            Dict: 閾値チェック結果
        """
        try:
            if client_ip not in self.security_events_cache:
                return {'blocked': False, 'events_count': 0}
            
            current_time = datetime.utcnow()
            recent_events = [
                event for event in self.security_events_cache[client_ip]
                if event['timestamp'] > current_time - timedelta(hours=1)
            ]
            
            events_count = len(recent_events)
            
            # 1時間に10回以上のセキュリティイベントでブロック
            if events_count >= 10:
                return {
                    'blocked': True,
                    'events_count': events_count,
                    'threshold': 10,
                    'window_hours': 1,
                    'message': 'セキュリティイベントの閾値を超えました。'
                }
            
            return {
                'blocked': False,
                'events_count': events_count,
                'threshold': 10,
                'window_hours': 1
            }
            
        except Exception as e:
            logger.error(f"セキュリティ閾値チェックエラー: {e}")
            return {'blocked': False, 'events_count': 0}
    
    async def sanitize_request_data(self, request: Request) -> Dict[str, Any]:
        """
        リクエストデータをサニタイズ
        
        Args:
            request: FastAPI リクエストオブジェクト
            
        Returns:
            Dict: サニタイズ結果
        """
        try:
            security_issues = []
            
            # クエリパラメータをチェック
            for key, value in request.query_params.items():
                # トークンパラメータは別途認証ミドルウェアで検証されるため、
                # SQLインジェクションチェックから除外する（JWTには危険なパターンが含まれる可能性があるため）
                if key == 'token':
                    continue
                
                # SQLインジェクションチェック
                sql_result = self.detect_sql_injection(value)
                if sql_result['detected']:
                    security_issues.append({
                        'type': 'sql_injection',
                        'location': 'query_params',
                        'key': key,
                        'patterns': sql_result['patterns'],
                        'value_preview': sql_result['input_preview']
                    })
                
                # XSSチェック
                xss_result = self.detect_xss_attack(value)
                if xss_result['detected']:
                    security_issues.append({
                        'type': 'xss_attack',
                        'location': 'query_params',
                        'key': key,
                        'patterns': xss_result['patterns'],
                        'value_preview': xss_result['input_preview']
                    })
            
            # ヘッダーをチェック（User-Agent、Refererなど）
            suspicious_headers = ['User-Agent', 'Referer', 'X-Forwarded-For']
            for header_name in suspicious_headers:
                header_value = request.headers.get(header_name)
                if header_value:
                    # SQLインジェクションチェック
                    sql_result = self.detect_sql_injection(header_value)
                    if sql_result['detected']:
                        security_issues.append({
                            'type': 'sql_injection',
                            'location': 'headers',
                            'key': header_name,
                            'patterns': sql_result['patterns'],
                            'value_preview': sql_result['input_preview']
                        })
                    
                    # XSSチェック
                    xss_result = self.detect_xss_attack(header_value)
                    if xss_result['detected']:
                        security_issues.append({
                            'type': 'xss_attack',
                            'location': 'headers',
                            'key': header_name,
                            'patterns': xss_result['patterns'],
                            'value_preview': xss_result['input_preview']
                        })
            
            return {
                'has_issues': len(security_issues) > 0,
                'issues': security_issues,
                'issues_count': len(security_issues)
            }
            
        except Exception as e:
            logger.error(f"リクエストデータサニタイズエラー: {e}")
            return {
                'has_issues': False,
                'issues': [],
                'issues_count': 0,
                'error': str(e)
            }
    
    async def dispatch(self, request: Request, call_next):
        """
        ミドルウェアのメイン処理
        
        Args:
            request: FastAPI リクエストオブジェクト
            call_next: 次のミドルウェアまたはエンドポイント
            
        Returns:
            Response: レスポンス
        """
        # WebSocket接続の場合は、後続の認証ミドルウェアやエンドポイントで
        # 認証・セキュリティチェックを行うため、ここではバイパスする
        # (BaseHTTPMiddlewareがWebSocketを完全にサポートしていないことによる不具合を防ぐため)
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        try:
            client_ip = request.client.host if request.client else "unknown"
            
            # セキュリティ閾値チェック
            threshold_result = await self.check_security_threshold(client_ip)
            if threshold_result['blocked']:
                await self.record_security_event(
                    "security_threshold_exceeded",
                    client_ip,
                    {
                        'events_count': threshold_result['events_count'],
                        'threshold': threshold_result['threshold'],
                        'url': str(request.url),
                        'method': request.method
                    }
                )
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        'error': 'security_threshold_exceeded',
                        'message': 'セキュリティイベントの閾値を超えました。しばらく後に再試行してください。'
                    }
                )
            
            # リクエストデータのセキュリティチェック
            sanitize_result = await self.sanitize_request_data(request)
            
            if sanitize_result['has_issues']:
                # セキュリティ問題を記録
                for issue in sanitize_result['issues']:
                    await self.record_security_event(
                        issue['type'],
                        client_ip,
                        {
                            'location': issue['location'],
                            'key': issue['key'],
                            'patterns': issue['patterns'],
                            'value_preview': issue['value_preview'],
                            'url': str(request.url),
                            'method': request.method
                        }
                    )
                
                # 攻撃を拒否
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        'error': 'security_violation',
                        'message': 'セキュリティ違反が検出されました。',
                        'issues_count': sanitize_result['issues_count']
                    }
                )
            
            # CSRF保護（POST、PUT、DELETE、PATCHリクエストの場合）
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                csrf_result = self.validate_csrf_token(request)
                
                if not csrf_result['valid']:
                    await self.record_security_event(
                        "csrf_validation_failed",
                        client_ip,
                        {
                            'method': request.method,
                            'url': str(request.url),
                            'csrf_method': csrf_result['method'],
                            'origin': csrf_result.get('origin'),
                            'referer': csrf_result.get('referer')
                        }
                    )
                    
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            'error': 'csrf_validation_failed',
                            'message': 'CSRF検証に失敗しました。'
                        }
                    )
            
            # 次のミドルウェアまたはエンドポイントを呼び出し
            response = await call_next(request)
            
            # セキュリティヘッダーを追加
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
            
            return response
            
        except Exception as e:
            logger.error(f"セキュリティミドルウェアエラー: {e}")
            
            # エラーログを記録
            client_ip = request.client.host if request.client else "unknown"
            await self.record_security_event(
                "security_middleware_error",
                client_ip,
                {
                    'error': str(e),
                    'url': str(request.url),
                    'method': request.method
                }
            )
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    'error': 'security_middleware_error',
                    'message': 'セキュリティミドルウェアでエラーが発生しました。'
                }
            )


# セキュリティミドルウェアのファクトリー関数
def create_security_middleware(allowed_origins: Optional[List[str]] = None):
    """
    セキュリティミドルウェアを作成
    
    Args:
        allowed_origins: 許可されたオリジンのリスト
        
    Returns:
        SecurityMiddleware: セキュリティミドルウェアインスタンス
    """
    return SecurityMiddleware(None, allowed_origins)
