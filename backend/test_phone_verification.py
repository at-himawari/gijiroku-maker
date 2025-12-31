#!/usr/bin/env python3
"""
電話番号認証機能のテストスクリプト
"""
import asyncio
import json
import os
from dotenv import load_dotenv
from cognito_service import CognitoService
from models import CognitoRegisterRequest

# 環境変数を読み込み
load_dotenv()

async def test_phone_verification():
    """電話番号認証機能をテスト"""
    
    # CognitoServiceを初期化
    try:
        cognito_service = CognitoService()
        print("✅ CognitoService初期化成功")
    except Exception as e:
        print(f"❌ CognitoService初期化失敗: {e}")
        return
    
    # テスト用データ
    test_email = "test@example.com"
    test_phone = "+819012345678"
    test_password = "TestPass123!"
    
    print(f"\n📱 電話番号認証機能テスト開始")
    print(f"テスト用メール: {test_email}")
    print(f"テスト用電話番号: {test_phone}")
    
    # 1. バリデーション機能のテスト
    print("\n1️⃣ バリデーション機能テスト")
    
    # メールアドレスバリデーション
    valid_emails = ["test@example.com", "user.name+tag@domain.co.jp"]
    invalid_emails = ["invalid-email", "@domain.com", "user@"]
    
    for email in valid_emails:
        result = cognito_service.validate_email(email)
        print(f"   📧 {email}: {'✅ 有効' if result else '❌ 無効'}")
    
    for email in invalid_emails:
        result = cognito_service.validate_email(email)
        print(f"   📧 {email}: {'✅ 有効' if result else '❌ 無効'}")
    
    # 電話番号バリデーション
    valid_phones = ["+819012345678", "09012345678", "+815012345678", "05012345678"]
    invalid_phones = ["123456789", "+1234567890", "abc123"]
    
    for phone in valid_phones:
        result = cognito_service.validate_phone_number(phone)
        print(f"   📞 {phone}: {'✅ 有効' if result else '❌ 無効'}")
    
    for phone in invalid_phones:
        result = cognito_service.validate_phone_number(phone)
        print(f"   📞 {phone}: {'✅ 有効' if result else '❌ 無効'}")
    
    # パスワードバリデーション
    valid_passwords = ["TestPass123!", "MySecure@Pass1", "Complex#Pass9"]
    invalid_passwords = ["weak", "12345678", "NoSymbol123", "nosymbol123!"]
    
    for password in valid_passwords:
        result = cognito_service.validate_password(password)
        print(f"   🔒 {password}: {'✅ 有効' if result['valid'] else '❌ 無効'} - {result['message']}")
    
    for password in invalid_passwords:
        result = cognito_service.validate_password(password)
        print(f"   🔒 {password}: {'✅ 有効' if result['valid'] else '❌ 無効'} - {result['message']}")
    
    # 2. 電話番号正規化テスト
    print("\n2️⃣ 電話番号正規化テスト")
    
    test_phones = ["09012345678", "090-1234-5678", "090 1234 5678", "+819012345678"]
    for phone in test_phones:
        normalized = cognito_service.normalize_phone_number(phone)
        print(f"   📞 {phone} → {normalized}")
    
    # 3. 登録データ検証テスト
    print("\n3️⃣ 登録データ検証テスト")
    
    # 有効な登録データ
    valid_registration = CognitoRegisterRequest(
        email="test@example.com",
        password="TestPass123!",
        phone_number="+819012345678",
        given_name="太郎",
        family_name="田中"
    )
    
    result = cognito_service.validate_registration_data(valid_registration)
    print(f"   ✅ 有効な登録データ: {'✅ 有効' if result['valid'] else '❌ 無効'} - {result['message']}")
    
    # 無効な登録データ
    invalid_registration = CognitoRegisterRequest(
        email="invalid-email",
        password="weak",
        phone_number="123",
        given_name="",
        family_name=""
    )
    
    result = cognito_service.validate_registration_data(invalid_registration)
    print(f"   ❌ 無効な登録データ: {'✅ 有効' if result['valid'] else '❌ 無効'} - {result['message']}")
    if result['errors']:
        for error in result['errors']:
            print(f"      - {error}")
    
    print("\n🎉 電話番号認証機能テスト完了")
    print("\n📝 注意: 実際のCognito操作（ユーザー作成、SMS送信など）はテストしていません。")
    print("   これらの機能をテストするには、有効なAWS Cognito設定が必要です。")

if __name__ == "__main__":
    asyncio.run(test_phone_verification())