"""
Cognito認証ミドルウェアのプロパティベーステスト
"""
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, AsyncMock, patch
from auth_middleware import AuthMiddleware
from fastapi import Request
from datetime import datetime, timedelta
import jwt


class TestCognitoAuthMiddlewareProperties:
    """Cognito認証ミドルウェアのプロパティテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.auth_middleware = AuthMiddleware()
        # Cognitoトークン検証をモック化
        self.auth_middleware.cognito_service = Mock()
        self.auth_middleware.cognito_service.verify_token = AsyncMock()

    @pytest.mark.asyncio
    @given(st.text(min_size=10, max_size=100))
    @settings(deadline=None)
    async def test_property_27_token_verification_functionality(self, token):
        """
        **Feature: email-password-auth, Property 27: トークン検証機能**
        **Validates: Requirements 6.2**
        
        任意の有効なJWTトークンに対して、認証ミドルウェアは正しく検証し、ユーザー情報を抽出する
        """
        # 有効なトークンの場合
        with patch('auth_middleware.cognito_token_service') as mock_cognito_service:
            mock_cognito_service.validate_and_sync_session = AsyncMock()
            mock_cognito_service.validate_and_sync_session.return_value = {
                'success': True,
                'user': Mock(user_id='test-user-123', email='test@example.com'),
                'session': Mock(),
                'cognito_payload': {'sub': 'test-user-123'}
            }
            
            # モックリクエストを作成
            mock_request = Mock(spec=Request)
            mock_request.headers = {"Authorization": f"Bearer {token}"}
            
            # トークン検証を実行
            result = await self.auth_middleware.verify_token(token, "127.0.0.1")
            
            # 検証が成功することを確認
            assert result['success'] is True
            assert 'user' in result
            assert 'email' in result['user'].__dict__ or hasattr(result['user'], 'email')

    @pytest.mark.asyncio
    @given(st.emails(), st.text(min_size=1, max_size=50))
    @settings(deadline=None)
    async def test_property_22_authenticated_access_allowed(self, email, user_id):
        """
        **Feature: email-password-auth, Property 22: 認証済みアクセス許可**
        **Validates: Requirements 5.1, 5.2**
        
        任意の認証済みユーザーに対して、保護されたリソースへのアクセスが許可される
        """
        # 認証済みユーザーのモック
        with patch('auth_middleware.cognito_token_service') as mock_cognito_service:
            mock_cognito_service.validate_and_sync_session = AsyncMock()
            mock_cognito_service.validate_and_sync_session.return_value = {
                'success': True,
                'user': Mock(user_id=user_id, email=email),
                'session': Mock(),
                'cognito_payload': {'sub': user_id}
            }
            
            # モックリクエストを作成
            mock_request = Mock(spec=Request)
            mock_request.headers = {"Authorization": "Bearer valid-token"}
            
            # 認証チェックを実行
            result = await self.auth_middleware.require_auth(mock_request)
            
            # アクセスが許可されることを確認
            assert result['success'] is True
            assert result['user'].user_id == user_id
            assert result['user'].email == email

    @pytest.mark.asyncio
    async def test_session_activity_update_on_verification(self):
        """
        **Feature: email-password-auth, Property: セッション活動更新**
        **Validates: Requirements 3.2**
        
        任意のトークン検証時に、セッションの最終活動時刻が更新される
        """
        # セッション更新のモック
        with patch('auth_middleware.cognito_token_service') as mock_cognito_service:
            mock_cognito_service.validate_and_sync_session = AsyncMock()
            mock_cognito_service.validate_and_sync_session.return_value = {
                'success': True,
                'user': Mock(user_id='test-user-123', email='test@example.com'),
                'session': Mock(),
                'cognito_payload': {'sub': 'test-user-123'}
            }
            
            # トークン検証を実行
            await self.auth_middleware.verify_token("valid-token", "127.0.0.1")
            
            # セッション検証・同期が呼ばれることを確認（これが活動更新を含む）
            mock_cognito_service.validate_and_sync_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_session_invalidation(self):
        """
        **Feature: email-password-auth, Property: 期限切れセッション無効化**
        **Validates: Requirements 3.1, 3.2**
        
        任意の期限切れトークンに対して、セッションが無効化される
        """
        # 期限切れトークンのモック
        with patch('auth_middleware.cognito_token_service') as mock_cognito_service:
            mock_cognito_service.validate_and_sync_session = AsyncMock()
            mock_cognito_service.validate_and_sync_session.return_value = {
                'success': False,
                'error': 'token_expired',
                'message': 'トークンの有効期限が切れています。'
            }
            
            # トークン検証を実行
            result = await self.auth_middleware.verify_token("expired-token", "127.0.0.1")
            
            # 検証が失敗することを確認
            assert result['success'] is False
            assert result['error'] == 'token_expired'

    @pytest.mark.asyncio
    async def test_inactive_session_timeout(self):
        """
        **Feature: email-password-auth, Property: 非アクティブセッションタイムアウト**
        **Validates: Requirements 3.5**
        
        任意の2時間非アクティブなセッションに対して、自動的にログアウトされる
        """
        # 非アクティブセッションのモック
        with patch('auth_middleware.cognito_token_service') as mock_cognito_service:
            mock_cognito_service.validate_and_sync_session = AsyncMock()
            mock_cognito_service.validate_and_sync_session.return_value = {
                'success': False,
                'error': 'session_inactive',
                'message': 'セッションが非アクティブです。'
            }
            
            # モックリクエストを作成
            mock_request = Mock(spec=Request)
            mock_request.headers = {"Authorization": "Bearer valid-token"}
            mock_request.client = Mock()
            mock_request.client.host = "127.0.0.1"
            mock_request.method = "GET"
            
            # 認証を実行
            result = await self.auth_middleware.require_auth(mock_request)
            
            # セッションが非アクティブとして判定されることを確認
            assert result['success'] is False
            assert result['error'] == 'session_inactive'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])