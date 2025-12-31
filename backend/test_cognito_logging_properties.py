"""
Cognito Email Authentication のログサービス プロパティベーステスト
"""
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, AsyncMock
from logging_service import LoggingService
from models import AuthLogCreate
from datetime import datetime


class TestCognitoLoggingServiceProperties:
    """Cognitoメール認証のログサービス プロパティテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.mock_db = Mock()
        self.mock_db.create_auth_log = AsyncMock()
        self.logging_service = LoggingService()
        # Mock the db_manager
        self.logging_service.db = self.mock_db
    
    def teardown_method(self):
        """各テストメソッドの後に実行"""
        # モックをリセット
        self.mock_db.reset_mock()

    @pytest.mark.asyncio
    @given(st.emails(), st.text(min_size=1, max_size=50))
    @settings(deadline=None)
    async def test_property_31_auth_attempt_logging(self, email, user_id):
        """
        **Feature: email-password-auth, Property 31: 認証試行ログの記録**
        **Validates: Requirements 8.1**
        
        任意の認証試行に対して、試行結果（成功・失敗・理由）がログに記録される
        """
        # モックをリセット
        self.mock_db.reset_mock()
        
        # モックの戻り値を設定
        self.mock_db.create_auth_log.return_value = True
        
        # Cognito認証試行ログを記録（Cognitoユーザーログインメソッドを使用）
        success = await self.logging_service.log_cognito_user_login(
            email, "success", {"attempt_type": "signin"}, user_id, "192.168.1.1"
        )
        
        # ログ記録が成功することを確認
        assert success is True
        
        # データベースの create_auth_log が呼ばれたことを確認
        self.mock_db.create_auth_log.assert_called_once()
        
        # 呼び出し引数を確認
        call_args = self.mock_db.create_auth_log.call_args[0][0]
        assert call_args.email == email
        assert call_args.event_type == "cognito_user_login"
        assert call_args.result == "success"
        assert call_args.user_id == user_id
        assert call_args.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    @given(st.emails(), st.text(min_size=1, max_size=50))
    @settings(deadline=None)
    async def test_property_32_password_reset_logging(self, email, user_id):
        """
        **Feature: email-password-auth, Property 32: パスワードリセットログの記録**
        **Validates: Requirements 9.1, 9.2**
        
        任意のパスワードリセット操作時に、操作詳細がログに記録される
        """
        # モックをリセット
        self.mock_db.reset_mock()
        
        # モックの戻り値を設定
        self.mock_db.create_auth_log.return_value = True
        
        # パスワードリセットログを記録（正しいメソッド名を使用）
        success = await self.logging_service.log_cognito_password_reset(
            email, "request", "success", {"reset_type": "request"}, user_id, "192.168.1.1"
        )
        
        # ログ記録が成功することを確認
        assert success is True
        
        # データベースの create_auth_log が呼ばれたことを確認
        self.mock_db.create_auth_log.assert_called_once()
        
        # 呼び出し引数を確認
        call_args = self.mock_db.create_auth_log.call_args[0][0]
        assert call_args.email == email
        assert call_args.event_type == "cognito_password_reset"
        assert call_args.result == "success"
        assert "operation" in call_args.details

    @pytest.mark.asyncio
    @given(st.emails(), st.text(min_size=1, max_size=50))
    @settings(deadline=None)
    async def test_property_33_session_operation_logging(self, email, user_id):
        """
        **Feature: email-password-auth, Property 33: セッション操作ログの記録**
        **Validates: Requirements 3.3, 3.4**
        
        任意のセッション作成・更新・無効化時に、セッション操作の詳細がログに記録される
        """
        # モックをリセット
        self.mock_db.reset_mock()
        
        # モックの戻り値を設定
        self.mock_db.create_auth_log.return_value = True
        
        # Cognitoセッション操作ログを記録
        success = await self.logging_service.log_cognito_session_operation(
            email, "created", "success", {"session_id": "session123"}, user_id, "192.168.1.1"
        )
        
        # ログ記録が成功することを確認
        assert success is True
        
        # データベースの create_auth_log が呼ばれたことを確認
        self.mock_db.create_auth_log.assert_called_once()
        
        # 呼び出し引数を確認
        call_args = self.mock_db.create_auth_log.call_args[0][0]
        assert call_args.email == email
        assert call_args.event_type == "cognito_session_operation"
        assert call_args.result == "success"
        assert "operation" in call_args.details
        assert "session_id" in call_args.details

    @pytest.mark.asyncio
    @given(st.text(min_size=1, max_size=50), st.emails(), st.floats(min_value=0.01, max_value=10000.0))
    @settings(deadline=None)
    async def test_property_34_billing_operation_logging(self, user_id, email, amount):
        """
        **Feature: email-password-auth, Property 34: 課金処理ログの記録**
        **Validates: Requirements 8.4**
        
        任意の課金サービス実行時に、ユーザーID、課金金額、処理時刻、処理結果を含む詳細ログが記録される
        """
        # モックをリセット
        self.mock_db.reset_mock()
        
        # モックの戻り値を設定
        self.mock_db.create_auth_log.return_value = True
        
        # 課金サービス実行ログを記録（Cognito用メソッドを使用）
        success = await self.logging_service.log_billing_service_execution(
            user_id, email, "generate_minutes", amount, "success", {"service": "generate_minutes"}, "192.168.1.1"
        )
        
        # ログ記録が成功することを確認
        assert success is True
        
        # データベースの create_auth_log が呼ばれたことを確認
        self.mock_db.create_auth_log.assert_called_once()
        
        # 呼び出し引数を確認
        call_args = self.mock_db.create_auth_log.call_args[0][0]
        assert call_args.email == email
        assert call_args.event_type == "billing_service_execution"
        assert call_args.result == "success"
        assert call_args.details["amount"] == amount
        assert call_args.details["currency"] == "JPY"
        assert "processed_at" in call_args.details

    @pytest.mark.asyncio
    @given(st.emails(), st.text(min_size=1, max_size=50))
    @settings(deadline=None)
    async def test_property_35_security_error_logging(self, email, user_id):
        """
        **Feature: email-password-auth, Property 35: セキュリティエラーログの記録**
        **Validates: Requirements 8.5**
        
        任意のセキュリティ関連エラー発生時に、攻撃の可能性を含む詳細情報がログに記録される
        """
        # モックをリセット
        self.mock_db.reset_mock()
        
        # モックの戻り値を設定
        self.mock_db.create_auth_log.return_value = True
        
        # セキュリティエラーログを記録
        success = await self.logging_service.log_security_error(
            email, "invalid_token", {"threat_level": "high"}, user_id, "192.168.1.1"
        )
        
        # ログ記録が成功することを確認
        assert success is True
        
        # データベースの create_auth_log が呼ばれたことを確認
        self.mock_db.create_auth_log.assert_called_once()
        
        # 呼び出し引数を確認
        call_args = self.mock_db.create_auth_log.call_args[0][0]
        assert call_args.email == email
        assert call_args.event_type == "security_error"
        assert call_args.result == "error"
        assert call_args.details["error_type"] == "invalid_token"
        assert "detected_at" in call_args.details


if __name__ == "__main__":
    pytest.main([__file__, "-v"])