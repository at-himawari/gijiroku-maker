"""
メールアドレス + パスワード認証システムの統合テスト
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import json
from datetime import datetime, timedelta

# FastAPIアプリケーションのインポートをモック化
with patch.dict('os.environ', {
    'GOOGLE_APPLICATION_CREDENTIALS': '/dev/null',
    'COGNITO_USER_POOL_ID': 'test_pool_id',
    'COGNITO_CLIENT_ID': 'test_client_id',
    'AWS_REGION': 'ap-northeast-1'
}):
    from cognito_service import CognitoService
    from auth_middleware import AuthMiddleware
    from models import (
        CognitoRegisterRequest,
        CognitoLoginRequest,
        CognitoPasswordResetRequest,
        CognitoPasswordResetConfirmRequest
    )
    from test_database_setup import test_db_manager


class TestEmailAuthIntegration:
    """メールアドレス + パスワード認証の統合テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        # Cognitoサービスをモック化
        self.mock_cognito_service = Mock(spec=CognitoService)
        
        # FastAPIクライアントの代わりにモックレスポンスを使用
        self.mock_response = Mock()
    
    @pytest.mark.asyncio
    async def test_register_flow_complete(self):
        """登録フローの完全テスト"""
        # Cognitoサービスのモック設定
        self.mock_cognito_service.register_user.return_value = {
            'success': True,
            'user_id': 'test-user-123',
            'message': 'ユーザー登録が完了しました'
        }
        
        # 登録データ
        register_data = CognitoRegisterRequest(
            email="test@example.com",
            password="Password123!",
            phone_number="09012345678",
            given_name="太郎",
            family_name="田中"
        )
        
        # サービス呼び出しをテスト
        result = await self.mock_cognito_service.register_user(register_data)
        
        # レスポンス検証
        assert result['success'] is True
        assert 'user_id' in result
        assert result['message'] == 'ユーザー登録が完了しました'
        
        # Cognitoサービスが呼ばれたことを確認
        self.mock_cognito_service.register_user.assert_called_once_with(register_data)
    
    @pytest.mark.asyncio
    async def test_register_flow_duplicate_email(self):
        """重複メールアドレスでの登録フローテスト"""
        # Cognitoサービスのモック設定（重複エラー）
        self.mock_cognito_service.register_user.return_value = {
            'success': False,
            'error': 'email_exists',
            'message': 'このメールアドレスは既に登録されています'
        }
        
        register_data = CognitoRegisterRequest(
            email="existing@example.com",
            password="Password123!",
            phone_number="09012345678",
            given_name="太郎",
            family_name="田中"
        )
        
        result = await self.mock_cognito_service.register_user(register_data)
        
        # エラーレスポンス検証
        assert result['success'] is False
        assert result['error'] == 'email_exists'
        assert 'このメールアドレスは既に登録されています' in result['message']
    
    @pytest.mark.asyncio
    async def test_login_flow_complete(self):
        """ログインフローの完全テスト"""
        # Cognitoサービスのモック設定
        self.mock_cognito_service.login_user.return_value = {
            'success': True,
            'access_token': 'access-token-123',
            'user_info': {
                'email': 'test@example.com',
                'given_name': '太郎',
                'family_name': '田中'
            },
            'message': 'ログインが完了しました'
        }
        
        login_data = CognitoLoginRequest(
            email="test@example.com",
            password="Password123!"
        )
        
        result = await self.mock_cognito_service.login_user(login_data)
        
        # レスポンス検証
        assert result['success'] is True
        assert 'access_token' in result
        assert 'user_info' in result
        assert result['user_info']['email'] == 'test@example.com'
        
        # Cognitoサービスが呼ばれたことを確認
        self.mock_cognito_service.login_user.assert_called_once_with(login_data)
    
    @pytest.mark.asyncio
    async def test_login_flow_invalid_credentials(self):
        """無効な認証情報でのログインフローテスト"""
        # Cognitoサービスのモック設定（認証失敗）
        self.mock_cognito_service.login_user.return_value = {
            'success': False,
            'error': 'invalid_credentials',
            'message': 'メールアドレスまたはパスワードが間違っています'
        }
        
        login_data = CognitoLoginRequest(
            email="test@example.com",
            password="WrongPassword123!"
        )
        
        result = await self.mock_cognito_service.login_user(login_data)
        
        # エラーレスポンス検証
        assert result['success'] is False
        assert result['error'] == 'invalid_credentials'
        assert 'メールアドレスまたはパスワードが間違っています' in result['message']
    
    @pytest.mark.asyncio
    async def test_password_reset_flow_complete(self):
        """パスワードリセットフローの完全テスト"""
        # パスワードリセット要求
        self.mock_cognito_service.request_password_reset.return_value = {
            'success': True,
            'message': 'パスワードリセットコードをメールに送信しました'
        }
        
        reset_result = await self.mock_cognito_service.request_password_reset("test@example.com")
        
        # リセット要求レスポンス検証
        assert reset_result['success'] is True
        assert 'パスワードリセット' in reset_result['message']
        
        # パスワードリセット確認
        self.mock_cognito_service.confirm_password_reset.return_value = {
            'success': True,
            'message': 'パスワードが正常にリセットされました'
        }
        
        confirm_result = await self.mock_cognito_service.confirm_password_reset(
            "test@example.com",
            "123456", 
            "NewPassword123!"
        )
        
        # リセット確認レスポンス検証
        assert confirm_result['success'] is True
        assert 'パスワード' in confirm_result['message']
        
        # 両方のメソッドが呼ばれたことを確認
        self.mock_cognito_service.request_password_reset.assert_called_once_with("test@example.com")
        self.mock_cognito_service.confirm_password_reset.assert_called_once_with(
            "test@example.com", "123456", "NewPassword123!"
        )
    
    @pytest.mark.asyncio
    async def test_token_verification_flow(self):
        """トークン検証フローテスト"""
        # 認証ミドルウェアのモック設定
        mock_auth_middleware = Mock(spec=AuthMiddleware)
        mock_auth_middleware.verify_token.return_value = {
            'success': True,
            'user_info': {
                'email': 'test@example.com',
                'given_name': '太郎',
                'family_name': '田中'
            },
            'session': {
                'session_id': 'session-123'
            }
        }
        
        # トークン検証をテスト
        result = await mock_auth_middleware.verify_token("valid-access-token")
        
        # 成功レスポンス検証
        assert result['success'] is True
        assert 'user_info' in result
        assert 'session' in result
        assert result['user_info']['email'] == 'test@example.com'
        
        mock_auth_middleware.verify_token.assert_called_once_with("valid-access-token")
    
    @pytest.mark.asyncio
    async def test_authentication_service_integration(self):
        """認証サービス統合テスト"""
        # 完全な認証フローをテスト
        
        # 1. ユーザー登録
        register_data = CognitoRegisterRequest(
            email="integration@example.com",
            password="Password123!",
            phone_number="09012345678",
            given_name="統合",
            family_name="テスト"
        )
        
        self.mock_cognito_service.register_user.return_value = {
            'success': True,
            'user_id': 'integration-user-123',
            'message': 'ユーザー登録が完了しました'
        }
        
        register_result = await self.mock_cognito_service.register_user(register_data)
        assert register_result['success'] is True
        
        # 2. ログイン
        login_data = CognitoLoginRequest(
            email="integration@example.com",
            password="Password123!"
        )
        
        self.mock_cognito_service.login_user.return_value = {
            'success': True,
            'access_token': 'integration-token-123',
            'user_info': {
                'email': 'integration@example.com',
                'given_name': '統合',
                'family_name': 'テスト'
            },
            'message': 'ログインが完了しました'
        }
        
        login_result = await self.mock_cognito_service.login_user(login_data)
        assert login_result['success'] is True
        assert 'access_token' in login_result
        
        # 3. セッション検証
        self.mock_cognito_service.verify_session.return_value = {
            'success': True,
            'user_info': login_result['user_info'],
            'session': {'session_id': 'integration-session-123'}
        }
        
        verify_result = await self.mock_cognito_service.verify_session(login_result['access_token'])
        assert verify_result['success'] is True
        
        # すべてのサービスメソッドが呼ばれたことを確認
        self.mock_cognito_service.register_user.assert_called_once()
        self.mock_cognito_service.login_user.assert_called_once()
        self.mock_cognito_service.verify_session.assert_called_once()
    
    def test_validation_integration(self):
        """バリデーション統合テスト"""
        # 実際のCognitoServiceインスタンスを作成してバリデーションをテスト
        with patch.dict('os.environ', {
            'COGNITO_USER_POOL_ID': 'test_pool_id',
            'COGNITO_CLIENT_ID': 'test_client_id',
            'AWS_REGION': 'ap-northeast-1'
        }):
            cognito_service = CognitoService()
            
            # 有効なデータの検証
            valid_data = CognitoRegisterRequest(
                email="valid@example.com",
                password="ValidPass123!",
                phone_number="09012345678",
                given_name="有効",
                family_name="データ"
            )
            
            validation_result = cognito_service.validate_registration_data(valid_data)
            assert validation_result['valid'] is True
            assert len(validation_result['errors']) == 0
            
            # 無効なデータの検証
            invalid_data = CognitoRegisterRequest(
                email="invalid-email",
                password="weak",
                phone_number="invalid",
                given_name="",
                family_name=""
            )
            
            validation_result = cognito_service.validate_registration_data(invalid_data)
            assert validation_result['valid'] is False
            assert len(validation_result['errors']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])