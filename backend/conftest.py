"""
pytest設定とフィクスチャ
"""
import pytest
import asyncio
from test_database_setup import test_db_manager, setup_test_db, cleanup_test_db, teardown_test_db


@pytest.fixture(scope="session")
def event_loop():
    """セッション全体で使用するイベントループ"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """テストセッション開始時にデータベースをセットアップ"""
    await setup_test_db()
    yield
    await teardown_test_db()


@pytest.fixture(autouse=True)
async def cleanup_database():
    """各テスト後にデータベースをクリーンアップ"""
    yield
    await cleanup_test_db()


@pytest.fixture
async def db_manager():
    """テスト用データベースマネージャーを提供"""
    return test_db_manager