# 電話番号認証 API 仕様書

## 概要

このドキュメントは、Cognito メールアドレス + パスワード認証システムにおける電話番号認証機能の API 仕様を説明します。

## 電話番号認証フロー

```
1. ユーザー登録 → 2. SMS認証コード送信 → 3. SMS認証コード検証 → 4. 登録完了
```

## API エンドポイント

### 1. SMS 認証コード送信

**エンドポイント:** `POST /auth/cognito/send-phone-verification`

**説明:** 指定されたメールアドレスのユーザーに対して SMS 認証コードを送信します。

**リクエスト:**

```json
{
  "email": "user@example.com"
}
```

**レスポンス（成功）:**

```json
{
  "success": true,
  "session": "AYABeA...",
  "message": "SMS認証コードを送信しました。電話番号に届いたコードを入力してください。"
}
```

**レスポンス（失敗）:**

```json
{
  "success": false,
  "error": "user_not_found",
  "message": "ユーザーが見つかりません。"
}
```

### 2. SMS 認証コード検証

**エンドポイント:** `POST /auth/cognito/verify-phone`

**説明:** SMS 認証コードを検証し、電話番号認証を完了します。

**リクエスト:**

```json
{
  "email": "user@example.com",
  "verification_code": "123456",
  "session": "AYABeA..."
}
```

**レスポンス（成功）:**

```json
{
  "success": true,
  "user_id": "uuid-string",
  "cognito_user_sub": "cognito-sub-string",
  "phone_verified": true,
  "message": "電話番号認証が完了しました。"
}
```

**レスポンス（失敗）:**

```json
{
  "success": false,
  "error": "invalid_code",
  "message": "SMS認証コードが正しくありません。正しいコードを入力してください。"
}
```

### 3. SMS 認証コード再送信

**エンドポイント:** `POST /auth/cognito/resend-verification`

**説明:** SMS 認証コードを再送信します。

**リクエスト:**

```json
{
  "email": "user@example.com"
}
```

**レスポンス（成功）:**

```json
{
  "success": true,
  "session": "AYABeA...",
  "message": "SMS認証コードを送信しました。電話番号に届いたコードを入力してください。"
}
```

### 4. 電話番号認証状態確認

**エンドポイント:** `GET /auth/cognito/phone-verification-status/{email}`

**説明:** 指定されたメールアドレスのユーザーの電話番号認証状態を確認します。

**レスポンス（成功）:**

```json
{
  "success": true,
  "email": "user@example.com",
  "phone_number": "+819012345678",
  "phone_verified": true,
  "user_status": "CONFIRMED",
  "enabled": true,
  "message": "電話番号認証状態: 認証済み"
}
```

## エラーコード一覧

| エラーコード                | 説明                         |
| --------------------------- | ---------------------------- |
| `invalid_email_format`      | メールアドレスの形式が無効   |
| `user_not_found`            | ユーザーが見つからない       |
| `missing_verification_code` | 認証コードが入力されていない |
| `missing_session`           | セッション情報が不正         |
| `invalid_code`              | SMS 認証コードが正しくない   |
| `expired_code`              | SMS 認証コードの有効期限切れ |
| `invalid_session`           | セッションが無効             |
| `rate_limit_exceeded`       | レート制限に達した           |
| `too_many_requests`         | リクエストが多すぎる         |
| `sms_send_failed`           | SMS 送信に失敗               |
| `cognito_error`             | Cognito サービスエラー       |
| `unexpected_error`          | システムエラー               |

## レート制限

- **SMS 送信:** 10 分間に 3 回まで
- **SMS 検証:** 10 分間に 5 回まで
- **SMS 再送信:** 10 分間に 3 回まで

## セキュリティ機能

1. **入力検証:** すべての入力データを厳格に検証
2. **レート制限:** 悪用を防ぐためのレート制限
3. **ログ記録:** すべての認証操作をログに記録
4. **セッション管理:** 安全なセッション管理
5. **エラーハンドリング:** 適切なエラーメッセージ

## 使用例

### JavaScript (fetch API)

```javascript
// SMS認証コード送信
async function sendVerificationCode(email) {
  const response = await fetch("/auth/cognito/send-phone-verification", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email }),
  });

  return await response.json();
}

// SMS認証コード検証
async function verifyCode(email, verificationCode, session) {
  const response = await fetch("/auth/cognito/verify-phone", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      verification_code: verificationCode,
      session,
    }),
  });

  return await response.json();
}

// 使用例
try {
  // 1. SMS認証コード送信
  const sendResult = await sendVerificationCode("user@example.com");
  if (sendResult.success) {
    console.log("SMS送信成功:", sendResult.message);

    // 2. ユーザーからコード入力を受け取る
    const userCode = prompt("SMS認証コードを入力してください:");

    // 3. SMS認証コード検証
    const verifyResult = await verifyCode(
      "user@example.com",
      userCode,
      sendResult.session
    );

    if (verifyResult.success) {
      console.log("認証成功:", verifyResult.message);
    } else {
      console.error("認証失敗:", verifyResult.message);
    }
  } else {
    console.error("SMS送信失敗:", sendResult.message);
  }
} catch (error) {
  console.error("エラー:", error);
}
```

## 注意事項

1. **SMS 認証コードの有効期限:** Cognito の設定により、通常 5 分間有効です。
2. **セッション管理:** SMS 送信時に取得したセッション ID は、認証コード検証時に必要です。
3. **レート制限:** 短時間での大量リクエストは制限されます。
4. **エラーハンドリング:** 適切なエラーハンドリングを実装してください。
5. **セキュリティ:** 認証コードは機密情報として扱ってください。

## トラブルシューティング

### よくある問題

1. **SMS 認証コードが届かない**

   - 電話番号が正しく登録されているか確認
   - 携帯電話の受信設定を確認
   - レート制限に達していないか確認

2. **認証コードが無効**

   - コードの有効期限（5 分）を確認
   - 入力したコードに誤りがないか確認
   - セッション ID が正しいか確認

3. **レート制限エラー**

   - 指定された時間待ってから再試行
   - 異なる IP アドレスからの試行を確認

4. **ユーザーが見つからない**
   - メールアドレスが正しく登録されているか確認
   - Cognito ユーザープールの設定を確認
