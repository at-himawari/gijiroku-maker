"""
AWS Cognito User Pool設定スクリプト
メールアドレス + パスワード認証システム用のCognito User Pool設定
"""
import os
import boto3
import json
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()


def setup_cognito_user_pool():
    """
    Cognito User Poolの設定を確認・更新
    
    このスクリプトは既存のUser Poolの設定を確認し、
    必要に応じて設定を更新します。
    """
    
    # 環境変数から設定を取得
    region = os.getenv('AWS_REGION', 'ap-northeast-1')
    user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
    client_id = os.getenv('COGNITO_CLIENT_ID')
    
    if not user_pool_id or not client_id:
        print("エラー: COGNITO_USER_POOL_ID と COGNITO_CLIENT_ID が設定されていません")
        return False
    
    try:
        # Cognitoクライアントを初期化
        cognito_client = boto3.client('cognito-idp', region_name=region)
        
        print(f"Cognito User Pool設定確認中: {user_pool_id}")
        
        # User Pool設定を取得
        user_pool = cognito_client.describe_user_pool(UserPoolId=user_pool_id)
        pool_config = user_pool['UserPool']
        
        print("\n=== 現在のUser Pool設定 ===")
        print(f"User Pool名: {pool_config.get('Name', 'N/A')}")
        print(f"作成日: {pool_config.get('CreationDate', 'N/A')}")
        
        # エイリアス設定確認
        aliases = pool_config.get('AliasAttributes', [])
        print(f"エイリアス属性: {aliases}")
        
        # パスワードポリシー確認
        password_policy = pool_config.get('Policies', {}).get('PasswordPolicy', {})
        print(f"\n=== パスワードポリシー ===")
        print(f"最小長: {password_policy.get('MinimumLength', 'N/A')}")
        print(f"大文字必須: {password_policy.get('RequireUppercase', 'N/A')}")
        print(f"小文字必須: {password_policy.get('RequireLowercase', 'N/A')}")
        print(f"数字必須: {password_policy.get('RequireNumbers', 'N/A')}")
        print(f"記号必須: {password_policy.get('RequireSymbols', 'N/A')}")
        
        # カスタム属性確認
        schema = pool_config.get('Schema', [])
        custom_attributes = [attr for attr in schema if attr.get('Name', '').startswith('custom:')]
        print(f"\n=== カスタム属性 ===")
        for attr in custom_attributes:
            print(f"- {attr.get('Name', 'N/A')}: {attr.get('AttributeDataType', 'N/A')}")
        
        # 標準属性確認
        standard_attributes = [attr for attr in schema if not attr.get('Name', '').startswith('custom:')]
        print(f"\n=== 標準属性 ===")
        required_attrs = []
        for attr in standard_attributes:
            name = attr.get('Name', 'N/A')
            required = attr.get('Required', False)
            if required:
                required_attrs.append(name)
            print(f"- {name}: 必須={required}")
        
        # App Client設定を取得
        print(f"\n=== App Client設定確認 ===")
        client_details = cognito_client.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        client_config = client_details['UserPoolClient']
        
        print(f"Client名: {client_config.get('ClientName', 'N/A')}")
        print(f"認証フロー: {client_config.get('ExplicitAuthFlows', [])}")
        print(f"読み取り属性: {client_config.get('ReadAttributes', [])}")
        print(f"書き込み属性: {client_config.get('WriteAttributes', [])}")
        
        # トークン有効期限
        print(f"\n=== トークン有効期限 ===")
        print(f"Access Token: {client_config.get('AccessTokenValidity', 'N/A')} 時間")
        print(f"ID Token: {client_config.get('IdTokenValidity', 'N/A')} 時間")
        print(f"Refresh Token: {client_config.get('RefreshTokenValidity', 'N/A')} 日")
        
        # 推奨設定との比較
        print(f"\n=== 推奨設定との比較 ===")
        
        # メールアドレス認証の確認
        if 'email' not in aliases:
            print("⚠️  推奨: メールアドレスをエイリアス属性として設定してください")
        else:
            print("✅ メールアドレス認証が有効です")
        
        # パスワードポリシーの確認
        if password_policy.get('MinimumLength', 0) < 8:
            print("⚠️  推奨: パスワード最小長を8文字以上に設定してください")
        else:
            print("✅ パスワード最小長が適切です")
        
        if not password_policy.get('RequireNumbers', False):
            print("⚠️  推奨: パスワードに数字を必須にしてください")
        else:
            print("✅ パスワードに数字が必須です")
        
        if not password_policy.get('RequireSymbols', False):
            print("⚠️  推奨: パスワードに記号を必須にしてください")
        else:
            print("✅ パスワードに記号が必須です")
        
        # 必須属性の確認
        required_standard_attrs = ['email', 'phone_number', 'given_name', 'family_name']
        for attr in required_standard_attrs:
            if attr not in required_attrs:
                print(f"⚠️  推奨: {attr}を必須属性として設定してください")
            else:
                print(f"✅ {attr}が必須属性です")
        
        # 認証フローの確認
        required_flows = ['ALLOW_USER_PASSWORD_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH']
        current_flows = client_config.get('ExplicitAuthFlows', [])
        for flow in required_flows:
            if flow not in current_flows:
                print(f"⚠️  推奨: {flow}認証フローを有効にしてください")
            else:
                print(f"✅ {flow}認証フローが有効です")
        
        print(f"\n=== 設定確認完了 ===")
        print("Cognito User Poolの設定確認が完了しました。")
        print("⚠️  マークの項目については、AWS Consoleで手動設定を推奨します。")
        
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"エラー: Cognito設定確認に失敗しました")
        print(f"エラーコード: {error_code}")
        print(f"エラーメッセージ: {error_message}")
        return False
        
    except Exception as e:
        print(f"予期しないエラー: {e}")
        return False


def print_cognito_setup_guide():
    """
    Cognito User Pool手動設定ガイドを表示
    """
    print("\n" + "="*60)
    print("AWS Cognito User Pool 手動設定ガイド")
    print("="*60)
    
    print("\n1. AWS Consoleでの基本設定:")
    print("   - サインイン方式: メールアドレス")
    print("   - パスワードポリシー:")
    print("     * 最小長: 8文字")
    print("     * 大文字、小文字、数字、記号を必須")
    
    print("\n2. 属性設定:")
    print("   - 必須属性:")
    print("     * email (メールアドレス)")
    print("     * phone_number (電話番号)")
    print("     * given_name (名前)")
    print("     * family_name (姓)")
    print("   - エイリアス属性: email")
    
    print("\n3. App Client設定:")
    print("   - 認証フロー:")
    print("     * ALLOW_USER_PASSWORD_AUTH")
    print("     * ALLOW_REFRESH_TOKEN_AUTH")
    print("   - トークン有効期限:")
    print("     * Access Token: 1時間")
    print("     * ID Token: 24時間")
    print("     * Refresh Token: 30日")
    
    print("\n4. 属性権限:")
    print("   - 読み取り権限: email, phone_number, given_name, family_name")
    print("   - 書き込み権限: phone_number, given_name, family_name")
    
    print("\n5. 一意性制約:")
    print("   - メールアドレス: 自動的に一意性が保証される")
    print("   - 電話番号: 自動的に一意性が保証される")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    print("AWS Cognito User Pool設定確認スクリプト")
    print("="*50)
    
    # 設定確認を実行
    success = setup_cognito_user_pool()
    
    if success:
        print("\n設定確認が正常に完了しました。")
    else:
        print("\n設定確認中にエラーが発生しました。")
    
    # 手動設定ガイドを表示
    print_cognito_setup_guide()