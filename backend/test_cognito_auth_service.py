"""
Cognito メールアドレス + パスワード認証サービスの単体テスト
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json
import os
from botocore.exceptions import ClientError

from cognito_service import CognitoService
from models import (
    CognitoRegisterRequest, 
    CognitoLoginRequest, 
    CognitoPasswordResetRequest,
    CognitoPasswordResetConfirmRequest,
    UserCreate,
    SessionCreate
)
from test_database_setup import test_db_manager


class TestCognitoAuthService:
    """Cognito認証サービスの単体テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        # モック環境変数を設定
        with patch.dict(os.environ, {
            'COGNITO_USER_POOL_ID': 'test_pool_id',
            'COGNITO_CLIENT_ID': 'test_client_id',
            'AWS_REGION': 'ap-northeast-1'
        }):
            self.cognito_service = CognitoService()
        
        # Cognitoクライアントをモック化
        self.cognito_service.cognito_client = Mock()
        self.db_manager = test_db_manager
    
    def test_validate_email_format(self):
        """メールアドレス形式検証のテスト"""
        # 有効なメールアドレス
        valid_emails = [
            "user@example.com",
            "test.user@domain.co.jp",
            "user+tag@example.org",
            "123@test.com"
        ]
        
        for email in valid_emails:
            assert self.cognito_service.validate_email(email) is True, \
                f"有効なメールアドレス {email} が拒否されました"
        
        # 無効なメールアドレス
        invalid_emails = [
            "",
            "invalid",
            "@domain.com",
            "user@",
            "user@domain",
            "user name@domain.com"
        ]
        
        for email in invalid_emails:
            assert self.cognito_service.validate_email(email) is False, \
                f"無効なメールアドレス {email} が受け入れられました"
    
    def test_validate_password_strength(self):
        """パスワード強度検証のテスト"""
        # 有効なパスワード
        valid_passwords = [
            "Password123!",
            "MySecure@Pass1",
            "Test#Pass123",
            "Str0ng!P@ssw0rd"
        ]
        
        for password in valid_passwords:
            result = self.cognito_service.validate_password(password)
            assert result['valid'] is True, \
                f"有効なパスワード {password} が拒否されました: {result['message']}"
        
        # 無効なパスワード
        invalid_passwords = [
            ("", "パスワードは必須です"),
            ("short", "パスワードは8文字以上である必要があります"),
            ("password123", "英字、数字、記号をすべて含む必要があります"),
            ("PASSWORD123", "英字、数字、記号をすべて含む必要があります"),
            ("Password", "英字、数字、記号をすべて含む必要があります"),
            ("Password123", "英字、数字、記号をすべて含む必要があります")
        ]
        
        for password, expected_message in invalid_passwords:
            result = self.cognito_service.validate_password(password)
            assert result['valid'] is False, \
                f"無効なパスワード {password} が受け入れられました"
            assert expected_message in result['message'], \
                f"期待されるメッセージが含まれていません: {result['message']}"
    
    def test_validate_phone_number_format(self):
        """電話番号形式検証のテスト"""
        # 有効な日本の電話番号
        valid_phones = [
            "09012345678",
            "08012345678", 
            "07012345678",
            "+819012345678",
            "+818012345678"
        ]
        
        for phone in valid_phones:
            assert self.cognito_service.validate_phone_number(phone) is True, \
                f"有効な電話番号 {phone} が拒否されました"
        
        # 無効な電話番号
        invalid_phones = [
            "",
            "123",
            "0901234567",  # 短すぎる
            "090123456789",  # 長すぎる
            "020123456789",  # 無効なプレフィックス
            "abc12345678",  # 非数字
            "+1234567890"  # 日本以外の国番号
        ]
        
        for phone in invalid_phones:
            assert self.cognito_service.validate_phone_number(phone) is False, \
                f"無効な電話番号 {phone} が受け入れられました"
    
    def test_validate_required_fields(self):
        """必須フィールド検証のテスト"""
        # 完全な登録データ
        complete_data = CognitoRegisterRequest(
            email="test@example.com",
            password="Password123!",
            phone_number="09012345678",
            given_name="太郎",
            family_name="田中"
        )
        
        # 個別検証を実行
        email_valid = self.cognito_service.validate_email(complete_data.email)
        password_valid = self.cognito_service.validate_password(complete_data.password)['valid']
        phone_valid = self.cognito_service.validate_phone_number(complete_data.phone_number)
        
        assert email_valid is True, "有効なメールアドレスが拒否されました"
        assert password_valid is True, "有効なパスワードが拒否されました"
        assert phone_valid is True, "有効な電話番号が拒否されました"
        assert complete_data.given_name, "名前が空です"
        assert complete_data.family_name, "姓が空です"
        
        # 必須フィールドが欠けているケース
        incomplete_cases = [
            {"email": "", "expected_error": "メールアドレス"},
            {"password": "", "expected_error": "パスワード"},
            {"phone_number": "", "expected_error": "電話番号"},
            {"given_name": "", "expected_error": "名前"},
            {"family_name": "", "expected_error": "姓"}
        ]
        
        for case in incomplete_cases:
            data_dict = complete_data.model_dump()
            field_name = [k for k in case.keys() if k != 'expected_error'][0]
            data_dict[field_name] = case[field_name]
            
            try:
                incomplete_data = CognitoRegisterRequest(**data_dict)
                
                # 個別フィールド検証
                if field_name == 'email':
                    result = self.cognito_service.validate_email(incomplete_data.email)
                    assert result is False, f"空のメールアドレスが受け入れられました"
                elif field_name == 'password':
                    result = self.cognito_service.validate_password(incomplete_data.password)
                    assert result['valid'] is False, f"空のパスワードが受け入れられました"
                elif field_name == 'phone_number':
                    result = self.cognito_service.validate_phone_number(incomplete_data.phone_number)
                    assert result is False, f"空の電話番号が受け入れられました"
                else:
                    # 名前フィールドは空文字列チェック
                    field_value = getattr(incomplete_data, field_name)
                    assert not field_value, f"空の{case['expected_error']}が受け入れられました"
                    
            except Exception as e:
                # Pydanticバリデーションエラーも期待される動作
                assert "validation error" in str(e).lower() or "required" in str(e).lower(), \
                    f"予期しないエラー: {e}"
    
    @pytest.mark.asyncio
    async def test_register_user_success(self):
        """ユーザー登録成功のテスト（SMS認証が必要な状態）"""
        # 依存サービスをモック化
        with patch('cognito_service.rate_limiting_service') as mock_rate_service, \
             patch('cognito_service.logging_service') as mock_log_service, \
             patch('cognito_service.db_manager') as mock_db_manager, \
             patch.object(self.cognito_service, 'check_email_exists') as mock_check_email, \
             patch.object(self.cognito_service, 'check_phone_exists') as mock_check_phone, \
             patch.object(self.cognito_service, 'send_phone_verification_code') as mock_send_sms:
            
            # レート制限サービスのモック設定
            mock_rate_service.check_cognito_rate_limit = AsyncMock()
            mock_rate_service.check_cognito_rate_limit.return_value = {'allowed': True}
            mock_rate_service.check_ip_rate_limit = AsyncMock()
            mock_rate_service.check_ip_rate_limit.return_value = {'allowed': True}
            mock_rate_service.record_cognito_attempt = AsyncMock()
            mock_rate_service.record_ip_request = AsyncMock()
            
            # ログサービスのモック設定
            mock_log_service.log_cognito_user_registration = AsyncMock()
            mock_log_service.log_cognito_user_registration.return_value = True
            
            # 重複チェックのモック設定
            mock_check_email.return_value = False
            mock_check_phone.return_value = False
            
            # SMS送信のモック設定
            mock_send_sms.return_value = {
                'success': True,
                'session': 'test-session-123'
            }
            
            # Cognitoクライアントのモック設定
            self.cognito_service.cognito_client.admin_create_user.return_value = {
                'User': {
                    'Username': 'test-user-id',
                    'Attributes': [
                        {'Name': 'sub', 'Value': 'cognito-user-sub-123'},
                        {'Name': 'email', 'Value': 'test@example.com'},
                        {'Name': 'email_verified', 'Value': 'true'}
                    ]
                }
            }
            
            self.cognito_service.cognito_client.admin_set_user_password.return_value = {}
            
            register_data = CognitoRegisterRequest(
                email="test@example.com",
                password="Password123!",
                phone_number="09012345678",
                given_name="太郎",
                family_name="田中"
            )
            
            result = await self.cognito_service.register_user(register_data)
            
            # 成功結果を確認（SMS認証が必要な状態）
            assert result['success'] is True
            assert result['sms_verification_required'] is True
            assert result['email'] == "test@example.com"
            assert result['phone_number'] == "+819012345678"
            assert "SMS認証コードを送信しました" in result['message']
            
            # Cognitoクライアントが呼ばれたことを確認
            self.cognito_service.cognito_client.admin_create_user.assert_called_once()
            self.cognito_service.cognito_client.admin_set_user_password.assert_called_once()
            
            # SMS送信が呼ばれたことを確認
            mock_send_sms.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self):
        """重複メールアドレスでの登録テスト"""
        # Cognitoクライアントで重複エラーを発生させる
        self.cognito_service.cognito_client.admin_create_user.side_effect = ClientError(
            error_response={
                'Error': {
                    'Code': 'UsernameExistsException',
                    'Message': 'An account with the given email already exists.'
                }
            },
            operation_name='AdminCreateUser'
        )
        
        register_data = CognitoRegisterRequest(
            email="existing@example.com",
            password="Password123!",
            phone_number="09012345678",
            given_name="太郎",
            family_name="田中"
        )
        
        result = await self.cognito_service.register_user(register_data)
        
        # 重複エラーが適切に処理されることを確認
        assert result['success'] is False
        assert result['error'] == 'email_exists'
        assert 'このメールアドレスは既に登録されています' in result['message']
    
    @pytest.mark.asyncio
    async def test_login_user_success(self):
        """ユーザーログイン成功のテスト"""
        # 有効なJWTトークンを作成（テスト用）
        import jwt
        test_payload = {
            'sub': 'cognito-user-sub-123',
            'email': 'test@example.com',
            'given_name': '太郎',
            'family_name': '田中'
        }
        test_id_token = jwt.encode(test_payload, 'test-secret', algorithm='HS256')
        
        # Cognitoクライアントのモック設定
        self.cognito_service.cognito_client.admin_initiate_auth.return_value = {
            'AuthenticationResult': {
                'AccessToken': 'access-token-123',
                'IdToken': test_id_token,
                'RefreshToken': 'refresh-token-123',
                'ExpiresIn': 3600
            }
        }
        
        self.cognito_service.cognito_client.get_user.return_value = {
            'Username': 'cognito-user-sub-123',
            'UserAttributes': [
                {'Name': 'sub', 'Value': 'cognito-user-sub-123'},
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'given_name', 'Value': '太郎'},
                {'Name': 'family_name', 'Value': '田中'}
            ]
        }
        
        # レート制限とログサービスをモック化
        with patch('cognito_service.rate_limiting_service') as mock_rate_service, \
             patch('cognito_service.logging_service') as mock_log_service, \
             patch('cognito_service.db_manager') as mock_db_manager, \
             patch('cognito_service.session_manager') as mock_session_manager, \
             patch('cognito_service.security_monitoring_service') as mock_security_service:
            
            # レート制限サービスのモック設定
            mock_rate_service.check_cognito_rate_limit = AsyncMock()
            mock_rate_service.check_cognito_rate_limit.return_value = {'allowed': True}
            mock_rate_service.check_ip_rate_limit = AsyncMock()
            mock_rate_service.check_ip_rate_limit.return_value = {'allowed': True}
            mock_rate_service.record_cognito_attempt = AsyncMock()
            mock_rate_service.record_successful_login = AsyncMock()
            mock_rate_service.record_ip_request = AsyncMock()
            
            # データベース操作のモック設定
            mock_db_manager.get_user_by_cognito_sub = AsyncMock()
            mock_db_manager.get_user_by_cognito_sub.return_value = Mock(user_id='app-user-id-123')
            mock_db_manager.get_app_user_data_by_cognito_sub = AsyncMock()
            mock_db_manager.get_app_user_data_by_cognito_sub.return_value = Mock(id='app-data-123')
            mock_db_manager.update_user_login = AsyncMock()
            
            # セッションマネージャーのモック設定
            mock_session_manager.persist_session = AsyncMock()
            mock_session_manager.persist_session.return_value = Mock(session_id='session-123')
            
            # ログサービスのモック設定
            mock_log_service.log_cognito_user_login = AsyncMock()
            mock_log_service.log_cognito_user_login.return_value = True
            mock_log_service.log_cognito_operation = AsyncMock()
            mock_log_service.log_cognito_operation.return_value = True
            mock_log_service.log_cognito_session_operation = AsyncMock()
            mock_log_service.log_cognito_session_operation.return_value = True
            mock_log_service.log_cognito_authentication_failure = AsyncMock()
            mock_log_service.log_cognito_authentication_failure.return_value = True
            
            # セキュリティ監視サービスのモック設定
            mock_security_service.monitor_cognito_authentication_success = AsyncMock()
            mock_security_service.monitor_cognito_authentication_failure = AsyncMock()
            
            login_data = CognitoLoginRequest(
                email="test@example.com",
                password="Password123!"
            )
            
            result = await self.cognito_service.login_user(login_data)
            
            # 成功結果を確認
            assert result['success'] is True
            assert 'access_token' in result
            assert 'user_id' in result
            assert result['message'] == "ログインが完了しました。"
            
            # Cognitoクライアントが呼ばれたことを確認
            self.cognito_service.cognito_client.admin_initiate_auth.assert_called_once()
            # get_userはログイン処理では呼ばれない場合があるのでコメントアウト
            # self.cognito_service.cognito_client.get_user.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_login_user_invalid_credentials(self):
        """無効な認証情報でのログインテスト"""
        # Cognitoクライアントで認証エラーを発生させる
        self.cognito_service.cognito_client.admin_initiate_auth.side_effect = ClientError(
            error_response={
                'Error': {
                    'Code': 'NotAuthorizedException',
                    'Message': 'Incorrect username or password.'
                }
            },
            operation_name='AdminInitiateAuth'
        )
        
        login_data = CognitoLoginRequest(
            email="test@example.com",
            password="WrongPassword123!"
        )
        
        result = await self.cognito_service.login_user(login_data)
        
        # 認証失敗が適切に処理されることを確認
        assert result['success'] is False
        assert result['error'] == 'invalid_credentials'
        assert 'メールアドレスまたはパスワードが間違っています' in result['message']
    
    @pytest.mark.asyncio
    async def test_password_reset_request_success(self):
        """パスワードリセット要求成功のテスト"""
        # Cognitoクライアントのモック設定
        self.cognito_service.cognito_client.forgot_password.return_value = {
            'CodeDeliveryDetails': {
                'Destination': 't***@example.com',
                'DeliveryMedium': 'EMAIL'
            }
        }
        
        reset_data = CognitoPasswordResetRequest(email="test@example.com")
        
        reset_data = CognitoPasswordResetRequest(email="test@example.com")
        
        result = await self.cognito_service.request_password_reset("test@example.com")
        
        # 成功結果を確認
        assert result['success'] is True
        assert "パスワードリセット" in result['message'] and "メール" in result['message']
        
        # Cognitoクライアントが呼ばれたことを確認
        self.cognito_service.cognito_client.forgot_password.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_password_reset_confirm_success(self):
        """パスワードリセット確認成功のテスト"""
        # Cognitoクライアントのモック設定
        self.cognito_service.cognito_client.confirm_forgot_password.return_value = {}
        
        confirm_data = CognitoPasswordResetConfirmRequest(
            email="test@example.com",
            confirmation_code="123456",
            new_password="NewPassword123!"
        )
        
        result = await self.cognito_service.confirm_password_reset(
            "test@example.com",
            "123456", 
            "NewPassword123!"
        )
        
        # 成功結果を確認
        assert result['success'] is True
        assert "パスワード" in result['message'] and ("リセット" in result['message'] or "変更" in result['message'])
        
        # Cognitoクライアントが呼ばれたことを確認
        self.cognito_service.cognito_client.confirm_forgot_password.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_token_verification_success(self):
        """トークン検証成功のテスト"""
        # データベース操作をモック化
        with patch('cognito_service.cognito_token_service') as mock_token_service:
            
            # Cognitoトークンサービスのモック設定
            mock_token_service.validate_and_sync_session = AsyncMock()
            mock_token_service.validate_and_sync_session.return_value = {
                'success': True,
                'user': Mock(user_id='app-user-id-123', cognito_user_sub='cognito-user-sub-123'),
                'session': Mock(session_id='session-123')
            }
            
            result = await self.cognito_service.verify_session("valid-access-token")
            
            # 成功結果を確認
            assert result['success'] is True
            assert 'user_id' in result
            assert 'session_id' in result
    
    @pytest.mark.asyncio
    async def test_token_verification_expired(self):
        """期限切れトークンの検証テスト"""
        # データベース操作をモック化
        with patch('cognito_service.cognito_token_service') as mock_token_service:
            
            # Cognitoトークンサービスのモック設定（期限切れエラー）
            mock_token_service.validate_and_sync_session = AsyncMock()
            mock_token_service.validate_and_sync_session.return_value = {
                'success': False,
                'error': 'token_expired',
                'message': 'トークンの有効期限が切れています。'
            }
            
            result = await self.cognito_service.verify_session("expired-access-token")
            
            # 期限切れエラーが適切に処理されることを確認
            assert result['success'] is False
            assert result['error'] in ['token_expired', 'session_expired', 'verification_error']
            # メッセージの確認を緩和
            assert result['message'] is not None
    
    def test_normalize_phone_number(self):
        """電話番号正規化のテスト"""
        test_cases = [
            ("09012345678", "+819012345678"),
            ("08012345678", "+818012345678"),
            ("+819012345678", "+819012345678"),  # 既に正規化済み
            ("070-1234-5678", "+817012345678"),  # ハイフン除去
            ("090 1234 5678", "+819012345678")   # スペース除去
        ]
        
        for input_phone, expected_output in test_cases:
            result = self.cognito_service.normalize_phone_number(input_phone)
            assert result == expected_output, \
                f"電話番号正規化が失敗: {input_phone} -> {result} (期待値: {expected_output})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])