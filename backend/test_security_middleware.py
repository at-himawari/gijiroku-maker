"""
セキュリティミドルウェアのテスト
"""
import pytest
import asyncio
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from security_middleware import SecurityMiddleware
from unittest.mock import AsyncMock, MagicMock


class TestSecurityMiddleware:
    """セキュリティミドルウェアのテストクラス"""
    
    def setup_method(self):
        """テストセットアップ"""
        self.app = FastAPI()
        self.middleware = SecurityMiddleware(
            self.app, 
            allowed_origins=['http://localhost:3000']
        )
    
    def test_sanitize_input(self):
        """入力サニタイゼーションのテスト"""
        # 正常な入力
        normal_input = "Hello World"
        result = self.middleware.sanitize_input(normal_input)
        assert result == "Hello World"
        
        # XSS攻撃パターン
        xss_input = "<script>alert('xss')</script>"
        result = self.middleware.sanitize_input(xss_input)
        assert "<script>" not in result
        assert "</script>" not in result
        # エスケープされていることを確認
        assert "&lt;script&gt;" in result
        
        # HTMLエスケープ
        html_input = "<div>test</div>"
        result = self.middleware.sanitize_input(html_input)
        assert "&lt;div&gt;" in result
    
    def test_detect_sql_injection(self):
        """SQLインジェクション検出のテスト"""
        # 正常な入力
        normal_input = "user@example.com"
        result = self.middleware.detect_sql_injection(normal_input)
        assert not result['detected']
        
        # SQLインジェクション攻撃
        sql_injection = "'; DROP TABLE users; --"
        result = self.middleware.detect_sql_injection(sql_injection)
        assert result['detected']
        assert len(result['patterns']) > 0
        
        # UNION SELECT攻撃
        union_attack = "1 UNION SELECT * FROM users"
        result = self.middleware.detect_sql_injection(union_attack)
        assert result['detected']
    
    def test_detect_xss_attack(self):
        """XSS攻撃検出のテスト"""
        # 正常な入力
        normal_input = "Hello World"
        result = self.middleware.detect_xss_attack(normal_input)
        assert not result['detected']
        
        # XSS攻撃パターン
        xss_patterns = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<iframe src='javascript:alert(1)'></iframe>"
        ]
        
        for pattern in xss_patterns:
            result = self.middleware.detect_xss_attack(pattern)
            assert result['detected'], f"XSS pattern not detected: {pattern}"
    
    def test_validate_csrf_token(self):
        """CSRF検証のテスト"""
        # モックリクエストを作成
        mock_request = MagicMock()
        
        # 有効なOriginヘッダー
        mock_request.headers.get.side_effect = lambda key: {
            'Origin': 'http://localhost:3000',
            'Referer': None,
            'Host': 'localhost:8000'
        }.get(key)
        
        result = self.middleware.validate_csrf_token(mock_request)
        assert result['valid']
        assert result['method'] == 'origin_header'
        
        # 無効なOriginヘッダー
        mock_request.headers.get.side_effect = lambda key: {
            'Origin': 'http://malicious-site.com',
            'Referer': None,
            'Host': 'localhost:8000'
        }.get(key)
        
        result = self.middleware.validate_csrf_token(mock_request)
        assert not result['valid']
        assert result['method'] == 'origin_header'
    
    @pytest.mark.asyncio
    async def test_record_security_event(self):
        """セキュリティイベント記録のテスト"""
        # logging_serviceをモック
        self.middleware.logging_service = AsyncMock()
        
        await self.middleware.record_security_event(
            "sql_injection", 
            "192.168.1.1", 
            {"test": "data"}
        )
        
        # イベントがキャッシュに記録されているかチェック
        assert "192.168.1.1" in self.middleware.security_events_cache
        assert len(self.middleware.security_events_cache["192.168.1.1"]) == 1
        
        event = self.middleware.security_events_cache["192.168.1.1"][0]
        assert event['event_type'] == "sql_injection"
        assert event['details'] == {"test": "data"}
    
    @pytest.mark.asyncio
    async def test_check_security_threshold(self):
        """セキュリティ閾値チェックのテスト"""
        client_ip = "192.168.1.1"
        
        # 正常な状態
        result = await self.middleware.check_security_threshold(client_ip)
        assert not result['blocked']
        assert result['events_count'] == 0
        
        # 閾値を超える状態をシミュレート
        from datetime import datetime
        current_time = datetime.utcnow()
        
        # 10回のセキュリティイベントを追加
        self.middleware.security_events_cache[client_ip] = [
            {
                'event_type': 'sql_injection',
                'timestamp': current_time,
                'details': {}
            }
        ] * 10
        
        result = await self.middleware.check_security_threshold(client_ip)
        assert result['blocked']
        assert result['events_count'] == 10
        assert result['threshold'] == 10
    
    @pytest.mark.asyncio
    async def test_sanitize_request_data(self):
        """リクエストデータサニタイズのテスト"""
        # モックリクエストを作成
        mock_request = MagicMock()
        
        # 正常なクエリパラメータ
        mock_request.query_params.items.return_value = [
            ('search', 'hello world'),
            ('page', '1')
        ]
        mock_request.headers.get.return_value = None
        
        result = await self.middleware.sanitize_request_data(mock_request)
        assert not result['has_issues']
        assert result['issues_count'] == 0
        
        # 危険なクエリパラメータ
        mock_request.query_params.items.return_value = [
            ('search', "'; DROP TABLE users; --"),
            ('xss', '<script>alert("xss")</script>')
        ]
        
        result = await self.middleware.sanitize_request_data(mock_request)
        assert result['has_issues']
        assert result['issues_count'] > 0
        
        # SQLインジェクションとXSSの両方が検出されることを確認
        issue_types = [issue['type'] for issue in result['issues']]
        assert 'sql_injection' in issue_types
        assert 'xss_attack' in issue_types


if __name__ == "__main__":
    # 簡単なテスト実行
    test_instance = TestSecurityMiddleware()
    test_instance.setup_method()
    
    # 基本的なテストを実行
    test_instance.test_sanitize_input()
    test_instance.test_detect_sql_injection()
    test_instance.test_detect_xss_attack()
    test_instance.test_validate_csrf_token()
    
    print("✅ セキュリティミドルウェアの基本テストが完了しました")