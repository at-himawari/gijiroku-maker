"""
セキュリティ統合テスト
CSRF攻撃対策、XSS攻撃対策、レート制限統合、認証バイパス試行のテスト
要件: 8.1, 8.5
"""
import pytest
import json
import time
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, List
import hashlib
import hmac
from datetime import datetime, timedelta

# セキュリティミドルウェア
class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF攻撃対策ミドルウェア"""
    
    def __init__(self, app, secret_key: str = "test-csrf-secret"):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        # GET、HEAD、OPTIONS以外のリクエストでCSRFトークンをチェック
        if request.method not in ["GET", "HEAD", "OPTIONS"]:
            csrf_token = request.headers.get("X-CSRF-Token")
            if not csrf_token or not self._validate_csrf_token(csrf_token):
                return JSONResponse(
                    status_code=403,
                    content={"error": "CSRF token missing or invalid", "message": "CSRFトークンが無効です"}
                )
        
        response = await call_next(request)
        return response
    
    def _validate_csrf_token(self, token: str) -> bool:
        """CSRFトークンの検証"""
        try:
            # 簡易的なトークン検証（実際の実装ではより厳密な検証が必要）
            expected = hmac.new(
                self.secret_key.encode(),
                "csrf-protection".encode(),
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(token, expected)
        except Exception:
            return False

class RateLimitMiddleware(BaseHTTPMiddleware):
    """レート制限ミドルウェア"""
    
    def __init__(self, app, max_requests: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts: Dict[str, List[datetime]] = {}
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        
        # 現在時刻
        now = datetime.now()
        
        # クライアントのリクエスト履歴を取得
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []
        
        # 古いリクエストを削除
        cutoff_time = now - timedelta(seconds=self.window_seconds)
        self.request_counts[client_ip] = [
            req_time for req_time in self.request_counts[client_ip]
            if req_time > cutoff_time
        ]
        
        # レート制限チェック
        if len(self.request_counts[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "message": "リクエスト制限に達しました"}
            )
        
        # リクエストを記録
        self.request_counts[client_ip].append(now)
        
        response = await call_next(request)
        return response

class XSSProtectionMiddleware(BaseHTTPMiddleware):
    """XSS攻撃対策ミドルウェア"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # XSS保護ヘッダーを追加
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'"
        
        return response

# セキュリティテスト用のFastAPIアプリケーション
security_test_app = FastAPI()

# ミドルウェアを追加
security_test_app.add_middleware(XSSProtectionMiddleware)
security_test_app.add_middleware(RateLimitMiddleware, max_requests=5, window_seconds=10)
security_test_app.add_middleware(CSRFProtectionMiddleware)
security_test_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 認証スキーム
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """認証ユーザーの取得"""
    token = credentials.credentials
    if token != "valid-test-token":
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return {"user_id": "test-user-123", "email": "test@example.com"}

# テスト用エンドポイント
@security_test_app.get("/")
async def root():
    return {"message": "Security test API"}

@security_test_app.post("/auth/login")
async def login(request: Request):
    """ログインエンドポイント（CSRF保護対象）"""
    body = await request.json()
    email = body.get("email")
    password = body.get("password")
    
    # 簡易認証チェック
    if email == "test@example.com" and password == "TestPassword123!":
        return {
            "success": True,
            "access_token": "valid-test-token",
            "message": "ログインが完了しました"
        }
    else:
        raise HTTPException(status_code=401, detail="認証に失敗しました")

@security_test_app.get("/protected")
async def protected_endpoint(current_user: dict = Depends(get_current_user)):
    """保護されたエンドポイント"""
    return {"message": "保護されたリソースにアクセスしました", "user": current_user}

@security_test_app.post("/data")
async def create_data(request: Request, current_user: dict = Depends(get_current_user)):
    """データ作成エンドポイント（CSRF保護対象）"""
    body = await request.json()
    return {"message": "データが作成されました", "data": body, "user": current_user}

@security_test_app.get("/public")
async def public_endpoint():
    """パブリックエンドポイント"""
    return {"message": "パブリックリソースです"}

@security_test_app.post("/xss-test")
async def xss_test_endpoint(request: Request):
    """XSSテスト用エンドポイント"""
    body = await request.json()
    user_input = body.get("input", "")
    
    # 入力サニタイゼーション（簡易版）
    sanitized_input = user_input.replace("<", "&lt;").replace(">", "&gt;")
    
    return {"message": "入力を受け付けました", "sanitized_input": sanitized_input}


class TestSecurityIntegration:
    """セキュリティ統合テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        # 各テストで新しいアプリインスタンスを作成してレート制限をリセット
        test_app = FastAPI()
        test_app.add_middleware(XSSProtectionMiddleware)
        test_app.add_middleware(RateLimitMiddleware, max_requests=10, window_seconds=60)
        test_app.add_middleware(CSRFProtectionMiddleware)
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # エンドポイントを追加
        @test_app.get("/")
        async def root():
            return {"message": "Security test API"}

        @test_app.post("/auth/login")
        async def login(request: Request):
            body = await request.json()
            email = body.get("email")
            password = body.get("password")
            if email == "test@example.com" and password == "TestPassword123!":
                return {"success": True, "access_token": "valid-test-token", "message": "ログインが完了しました"}
            else:
                raise HTTPException(status_code=401, detail="認証に失敗しました")

        @test_app.get("/protected")
        async def protected_endpoint(current_user: dict = Depends(get_current_user)):
            return {"message": "保護されたリソースにアクセスしました", "user": current_user}

        @test_app.post("/data")
        async def create_data(request: Request, current_user: dict = Depends(get_current_user)):
            body = await request.json()
            return {"message": "データが作成されました", "data": body, "user": current_user}

        @test_app.get("/public")
        async def public_endpoint():
            return {"message": "パブリックリソースです"}

        @test_app.post("/xss-test")
        async def xss_test_endpoint(request: Request):
            body = await request.json()
            user_input = body.get("input", "")
            # より包括的なサニタイゼーション
            sanitized_input = (user_input
                             .replace("<", "&lt;")
                             .replace(">", "&gt;")
                             .replace("javascript:", "")
                             .replace("data:", "")
                             .replace("vbscript:", ""))
            return {"message": "入力を受け付けました", "sanitized_input": sanitized_input}
        
        self.client = TestClient(test_app)
        
        # 有効なCSRFトークンを生成
        self.valid_csrf_token = hmac.new(
            "test-csrf-secret".encode(),
            "csrf-protection".encode(),
            hashlib.sha256
        ).hexdigest()
        
        # テスト用認証トークン
        self.valid_token = "valid-test-token"
        self.invalid_token = "invalid-test-token"
    
    def test_csrf_attack_prevention(self):
        """CSRF攻撃対策テスト"""
        # CSRFトークンなしでPOSTリクエスト（攻撃をシミュレーション）
        response = self.client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"}
        )
        
        # CSRF攻撃が防がれることを確認
        assert response.status_code == 403
        assert "CSRF" in response.json()["error"]
        assert "CSRFトークンが無効です" in response.json()["message"]
    
    def test_csrf_valid_token_access(self):
        """有効なCSRFトークンでのアクセステスト"""
        # 有効なCSRFトークンでPOSTリクエスト
        headers = {"X-CSRF-Token": self.valid_csrf_token}
        response = self.client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
            headers=headers
        )
        
        # 正常にアクセスできることを確認
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_xss_attack_prevention(self):
        """XSS攻撃対策テスト"""
        # XSS攻撃を含む入力をテスト
        malicious_input = "<script>alert('XSS')</script>"
        
        headers = {"X-CSRF-Token": self.valid_csrf_token}
        response = self.client.post(
            "/xss-test",
            json={"input": malicious_input},
            headers=headers
        )
        
        # XSS攻撃が防がれることを確認
        assert response.status_code == 200
        response_data = response.json()
        assert "&lt;script&gt;" in response_data["sanitized_input"]
        assert "&lt;/script&gt;" in response_data["sanitized_input"]
        
        # セキュリティヘッダーが設定されていることを確認
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert "Content-Security-Policy" in response.headers
    
    def test_rate_limiting_integration(self):
        """レート制限統合テスト"""
        # 短時間で大量のリクエストを送信
        responses = []
        for i in range(12):  # 制限は10リクエスト/60秒
            response = self.client.get("/public")
            responses.append(response)
        
        # 最初の10リクエストは成功
        for i in range(10):
            assert responses[i].status_code == 200
        
        # 11番目以降のリクエストはレート制限でブロック
        for i in range(10, 12):
            assert responses[i].status_code == 429
            assert "Rate limit exceeded" in responses[i].json()["error"]
            assert "リクエスト制限に達しました" in responses[i].json()["message"]
    
    def test_authentication_bypass_attempt(self):
        """認証バイパス試行テスト"""
        # 無効なトークンで保護されたエンドポイントにアクセス
        headers = {"Authorization": f"Bearer {self.invalid_token}"}
        response = self.client.get("/protected", headers=headers)
        
        # 認証が失敗することを確認
        assert response.status_code == 401
        assert "Invalid authentication credentials" in response.json()["detail"]
    
    def test_authentication_bypass_no_token(self):
        """トークンなしでの認証バイパス試行テスト"""
        # トークンなしで保護されたエンドポイントにアクセス
        response = self.client.get("/protected")
        
        # 認証が必要であることを確認
        assert response.status_code == 403  # FastAPIのHTTPBearerは403を返す
    
    def test_valid_authentication_access(self):
        """有効な認証でのアクセステスト"""
        # 有効なトークンで保護されたエンドポイントにアクセス
        headers = {"Authorization": f"Bearer {self.valid_token}"}
        response = self.client.get("/protected", headers=headers)
        
        # 正常にアクセスできることを確認
        assert response.status_code == 200
        assert "保護されたリソースにアクセスしました" in response.json()["message"]
        assert response.json()["user"]["user_id"] == "test-user-123"
    
    def test_combined_security_measures(self):
        """複合セキュリティ対策テスト"""
        # 有効な認証とCSRFトークンで保護されたエンドポイントにアクセス
        headers = {
            "Authorization": f"Bearer {self.valid_token}",
            "X-CSRF-Token": self.valid_csrf_token
        }
        
        response = self.client.post(
            "/data",
            json={"name": "テストデータ", "value": 123},
            headers=headers
        )
        
        # 正常にアクセスできることを確認
        assert response.status_code == 200
        assert "データが作成されました" in response.json()["message"]
        assert response.json()["user"]["user_id"] == "test-user-123"
    
    def test_invalid_csrf_with_valid_auth(self):
        """有効な認証だが無効なCSRFトークンのテスト"""
        headers = {
            "Authorization": f"Bearer {self.valid_token}",
            "X-CSRF-Token": "invalid-csrf-token"
        }
        
        response = self.client.post(
            "/data",
            json={"name": "テストデータ", "value": 123},
            headers=headers
        )
        
        # CSRF保護により拒否されることを確認
        assert response.status_code == 403
        assert "CSRF" in response.json()["error"]
    
    def test_security_headers_presence(self):
        """セキュリティヘッダーの存在確認テスト"""
        response = self.client.get("/public")
        
        # 必要なセキュリティヘッダーが設定されていることを確認
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
    
    def test_cors_configuration(self):
        """CORS設定テスト"""
        # プリフライトリクエストをシミュレーション
        response = self.client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token"
            }
        )
        
        # CORS設定が正しく動作することを確認
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers
    
    def test_malicious_input_sanitization(self):
        """悪意のある入力のサニタイゼーションテスト"""
        malicious_inputs = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "'; DROP TABLE users; --",
            "<iframe src='javascript:alert(\"XSS\")'></iframe>"
        ]
        
        headers = {"X-CSRF-Token": self.valid_csrf_token}
        
        for malicious_input in malicious_inputs:
            response = self.client.post(
                "/xss-test",
                json={"input": malicious_input},
                headers=headers
            )
            
            # 入力がサニタイズされていることを確認
            assert response.status_code == 200
            sanitized = response.json()["sanitized_input"]
            assert "<script>" not in sanitized
            assert "javascript:" not in sanitized
            assert "<iframe" not in sanitized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])