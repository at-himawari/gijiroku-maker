"""
Cognito統合セットアップ検証スクリプト
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def validate_setup():
    """セットアップの検証を実行"""
    print("🔍 Cognito統合セットアップ検証開始")
    print("=" * 50)
    
    # 1. 環境変数の確認
    print("\n1. 環境変数の確認:")
    required_vars = [
        'COGNITO_USER_POOL_ID',
        'COGNITO_CLIENT_ID', 
        'AWS_REGION',
        'DB_HOST',
        'DB_USER',
        'DB_PASSWORD',
        'DB_NAME'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var}: {value[:10]}..." if len(value) > 10 else f"   ✅ {var}: {value}")
        else:
            print(f"   ❌ {var}: 未設定")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n❌ 必須環境変数が不足しています: {missing_vars}")
        return False
    
    # 2. データベース接続テスト
    print("\n2. データベース接続テスト:")
    try:
        from database import db_manager
        await db_manager.init_pool()
        print("   ✅ データベース接続成功")
        
        # テーブル存在確認
        async with db_manager.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SHOW TABLES")
                tables = await cursor.fetchall()
                table_names = [table[0] for table in tables]
                
                required_tables = ['users', 'user_sessions', 'auth_logs']
                for table in required_tables:
                    if table in table_names:
                        print(f"   ✅ テーブル '{table}' 存在確認")
                    else:
                        print(f"   ❌ テーブル '{table}' が見つかりません")
        
        await db_manager.close_pool()
        
    except Exception as e:
        print(f"   ❌ データベース接続エラー: {e}")
        return False
    
    # 3. Cognitoサービスインポートテスト
    print("\n3. Cognitoサービステスト:")
    try:
        from cognito_service import CognitoService
        print("   ✅ CognitoService import成功")
        
        # サービスインスタンス作成テスト
        service = CognitoService()
        print("   ✅ CognitoServiceインスタンス作成成功")
        
    except Exception as e:
        print(f"   ❌ CognitoServiceエラー: {e}")
        return False
    
    # 4. モデルインポートテスト
    print("\n4. モデルインポートテスト:")
    try:
        from models import (
            User, UserSession, AuthLog, 
            UserCreate, SessionCreate, AuthLogCreate,
            CognitoRegisterRequest, CognitoLoginRequest,
            CognitoPasswordResetRequest, CognitoPasswordResetConfirmRequest
        )
        print("   ✅ 全モデルimport成功")
        
        # モデル作成テスト
        user = User(
            cognito_user_sub="test-sub",
            cognito_username="test@example.com",
            email="test@example.com",
            phone_number="+81901234567",
            given_name="テスト",
            family_name="ユーザー"
        )
        print("   ✅ Userモデル作成成功")
        
    except Exception as e:
        print(f"   ❌ モデルエラー: {e}")
        return False
    
    # 5. 設定要件確認
    print("\n5. 設定要件確認:")
    
    # User Pool ID形式確認
    user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
    if user_pool_id and user_pool_id.startswith(os.getenv('AWS_REGION', 'ap-northeast-1')):
        print("   ✅ User Pool ID形式正常")
    else:
        print("   ⚠️  User Pool ID形式を確認してください")
    
    # Client ID形式確認
    client_id = os.getenv('COGNITO_CLIENT_ID')
    if client_id and len(client_id) > 20:
        print("   ✅ Client ID形式正常")
    else:
        print("   ⚠️  Client ID形式を確認してください")
    
    print("\n" + "=" * 50)
    print("🎉 Cognito統合セットアップ検証完了")
    print("\n📋 次のステップ:")
    print("   1. AWS Consoleでユーザープール設定を確認")
    print("   2. メールアドレス認証とパスワードポリシーを設定")
    print("   3. 必須属性（email, phone_number, given_name, family_name）を設定")
    print("   4. App Client認証フローを設定")
    print("   5. 一意性制約が自動的に適用されることを確認")
    
    return True

if __name__ == "__main__":
    asyncio.run(validate_setup())