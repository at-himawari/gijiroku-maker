# 監査ログとセキュリティ機能実装サマリー

## 概要

このドキュメントは、タスク 10「監査ログとセキュリティ機能強化」の実装内容をまとめたものです。要件 8.1-8.5 に対応する包括的なログ記録とセキュリティ監視機能を実装しました。

## 実装内容

### 1. 認証操作ログ記録の完全実装（要件 8.1）

#### 実装済み機能

- **認証試行ログ**: `log_auth_attempt()` - 電話番号認証の試行結果を記録
- **Cognito 認証ログ**:
  - `log_cognito_user_login()` - ログイン成功/失敗を記録
  - `log_cognito_user_logout()` - ログアウト操作を記録
  - `log_cognito_authentication_failure()` - 認証失敗の詳細を記録
  - `log_cognito_password_reset()` - パスワードリセット操作を記録
  - `log_cognito_session_operation()` - セッション作成/更新/無効化を記録
  - `log_cognito_sms_verification()` - SMS 認証コード送信/検証を記録

#### ログ記録内容

- ユーザー ID
- メールアドレス/電話番号
- 操作タイプ（login, logout, password_reset, etc.）
- 結果（success, failure, error）
- 詳細情報（失敗理由、セッション ID、IP アドレスなど）
- タイムスタンプ

### 2. 新規ユーザー登録ログ記録（要件 8.2）

#### 実装済み機能

- **Cognito ユーザー登録ログ**: `log_cognito_user_registration()`
  - 登録日時の記録
  - メールアドレスの記録
  - 氏名の記録（詳細情報内）
  - 電話番号の記録（詳細情報内）
  - 登録結果（成功/失敗）の記録

#### ログ記録内容

```json
{
  "user_id": "ユーザーID",
  "email": "メールアドレス",
  "event_type": "cognito_user_registration",
  "result": "success",
  "details": {
    "name": "氏名",
    "phone_number": "電話番号",
    "operation": "user_registration",
    "cognito_service": true,
    "processed_at": "2024-01-01T00:00:00Z"
  },
  "ip_address": "IPアドレス"
}
```

### 3. セッション操作ログ記録（要件 8.3）

#### 実装済み機能

- **セッション操作ログ**: `log_session_operation()` / `log_cognito_session_operation()`
  - セッション作成時のログ記録
  - セッション更新時のログ記録
  - セッション無効化時のログ記録
  - セッション有効期限の記録

#### ログ記録内容

- セッション ID
- ユーザー ID
- 操作タイプ（created, refreshed, invalidated, expired）
- 有効期限
- IP アドレス
- タイムスタンプ

### 4. 課金サービス実行ログ記録（要件 8.4）

#### 実装済み機能

- **課金サービス実行ログ**: `log_billing_service_execution()`
  - ユーザー ID
  - 課金金額
  - 処理時刻
  - 処理結果（started, success, failure, error）
  - サービス名（generate_minutes, transcription, etc.）
  - トランザクション詳細

#### ログ記録内容

```json
{
  "user_id": "ユーザーID",
  "email": "ユーザー識別子",
  "event_type": "billing_service_execution",
  "result": "success",
  "details": {
    "service_name": "generate_minutes",
    "amount": 0.0,
    "currency": "JPY",
    "processed_at": "2024-01-01T00:00:00Z",
    "billing_service": true,
    "transcript_length": 1000,
    "minutes_length": 500
  },
  "ip_address": "IPアドレス"
}
```

#### 課金ログの特徴

- 課金処理の開始・完了・失敗を全て記録
- 金額、通貨、処理時刻を必ず含める
- CloudWatch Logs に優先的に送信（重要度が高いため）

### 5. セキュリティイベントログ記録（要件 8.5）

#### 実装済み機能

##### セキュリティエラーログ

- **一般セキュリティエラー**: `log_security_error()`
- **Cognito セキュリティエラー**: `log_cognito_security_error()`
- **ブルートフォース攻撃**: `log_cognito_brute_force_attack()`
- **不正アクセス試行**: `log_cognito_unauthorized_access()`

##### セキュリティ監視機能

- **ブルートフォース攻撃検出**: `_detect_brute_force_attack()`

  - 15 分間に 10 回以上の認証失敗を検出
  - メールアドレスベースの攻撃パターン分析
  - 自動アラート生成

- **クレデンシャルスタッフィング攻撃検出**: `_detect_suspicious_ip_patterns()`

  - 1 時間に複数アカウント（5 件以上）への攻撃を検出
  - IP アドレスベースの攻撃パターン分析
  - 自動アラート生成

- **アカウントロック監視**: `_monitor_account_lockout()`

  - 30 分間に 5 回以上の失敗試行を監視
  - リスクレベル判定（low, medium, high）
  - アカウントロック警告

- **異常課金パターン検出**: `_detect_abnormal_billing_patterns()`

  - 1 時間に 10 回以上の課金実行を検出
  - 高頻度課金パターンの分析
  - 自動アラート生成

- **高額課金監視**: `_monitor_high_amount_billing()`
  - 1000 円以上の課金を監視
  - 2000 円以上は高危険度アラート
  - 自動アラート生成

#### セキュリティログの危険度レベル

- **high**: SQL injection, XSS, brute force, credential stuffing
- **medium**: CSRF, rate limit exceeded, invalid token
- **low**: その他のセキュリティイベント

### 6. CloudWatch Logs 統合の最適化

#### 実装済み機能

- **CloudWatch Logs クライアント**: boto3 を使用した統合
- **自動ログ送信**: 重要なイベントを自動的に CloudWatch Logs に送信
- **環境変数設定**:
  - `ENABLE_CLOUDWATCH_LOGS`: CloudWatch Logs 統合の有効/無効
  - `CLOUDWATCH_LOG_GROUP`: ログ記録先のロググループ
  - `CLOUDWATCH_LOG_STREAM`: ログ記録先のログストリーム
  - `CLOUDWATCH_SECURITY_LOG_GROUP`: セキュリティログのロググループ
  - `CLOUDWATCH_SECURITY_LOG_STREAM`: セキュリティログのログストリーム

#### CloudWatch Logs に送信されるログ

1. **認証試行ログ**: 全ての認証試行
2. **課金サービス実行ログ**: 全ての課金処理（重要度が高い）
3. **セキュリティエラーログ**: 全てのセキュリティイベント（重要度が高い）
4. **ユーザー登録ログ**: 新規ユーザー登録
5. **セキュリティアラート**: ブルートフォース攻撃、クレデンシャルスタッフィング、異常課金パターン

#### CloudWatch Logs 統合の利点

- **集中管理**: 全てのログを一元管理
- **長期保存**: データベースとは別に長期保存可能
- **アラート設定**: CloudWatch Alarms と連携可能
- **分析機能**: CloudWatch Insights で高度な分析が可能
- **監査対応**: コンプライアンス要件に対応

## 使用方法

### CloudWatch Logs 統合の有効化

1. `.env`ファイルで設定を有効化:

```bash
ENABLE_CLOUDWATCH_LOGS=true
CLOUDWATCH_LOG_GROUP=/aws/application/gijiroku-maker
CLOUDWATCH_LOG_STREAM=authentication-logs
CLOUDWATCH_SECURITY_LOG_GROUP=/aws/application/gijiroku-maker/security
CLOUDWATCH_SECURITY_LOG_STREAM=security-monitoring
```

2. AWS 認証情報を設定（boto3 が使用）:

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=ap-northeast-1
```

3. boto3 をインストール:

```bash
pip install boto3
```

### ログの確認

#### データベースログの確認

```sql
-- 認証ログの確認
SELECT * FROM auth_logs
WHERE event_type = 'cognito_user_login'
ORDER BY created_at DESC
LIMIT 10;

-- 課金ログの確認
SELECT * FROM auth_logs
WHERE event_type = 'billing_service_execution'
ORDER BY created_at DESC
LIMIT 10;

-- セキュリティエラーログの確認
SELECT * FROM auth_logs
WHERE event_type IN ('security_error', 'cognito_security_error', 'cognito_brute_force_attack')
ORDER BY created_at DESC
LIMIT 10;
```

#### CloudWatch Logs の確認

AWS Management Console から以下のロググループを確認:

- `/aws/application/gijiroku-maker` - 認証・課金ログ
- `/aws/application/gijiroku-maker/security` - セキュリティ監視ログ

### セキュリティサマリーの取得

API エンドポイント経由でセキュリティサマリーを取得:

```bash
curl -X GET "http://localhost:8000/security/monitoring/summary?time_window_hours=24" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

レスポンス例:

```json
{
  "success": true,
  "security_summary": {
    "time_window_hours": 24,
    "summary_generated_at": "2024-01-01T00:00:00Z",
    "security_events": {
      "brute_force_attacks": 5,
      "credential_stuffing_attacks": 2,
      "unauthorized_access_attempts": 10,
      "high_amount_billing_alerts": 1,
      "abnormal_billing_patterns": 0
    },
    "active_threats": [],
    "recommendations": [
      "ブルートフォース攻撃が多発しています。レート制限の強化を検討してください。"
    ]
  }
}
```

## セキュリティ閾値設定

現在の閾値設定（`security_monitoring_service.py`）:

```python
self.security_thresholds = {
    'brute_force_attempts': 10,  # 15分間での失敗試行回数
    'brute_force_window_minutes': 15,
    'suspicious_login_count': 5,  # 1時間での異常ログイン回数
    'suspicious_login_window_minutes': 60,
    'ip_ban_threshold': 50,  # 1時間でのIP制限閾値
    'ip_ban_window_minutes': 60,
    'account_lockout_threshold': 5,  # アカウントロック閾値
    'account_lockout_window_minutes': 30
}
```

これらの閾値は、セキュリティ要件に応じて調整可能です。

## 要件対応状況

| 要件 | 内容                         | 実装状況 | 実装箇所                                               |
| ---- | ---------------------------- | -------- | ------------------------------------------------------ |
| 8.1  | 認証試行ログ記録             | ✅ 完了  | `logging_service.py`                                   |
| 8.2  | 新規ユーザー登録ログ記録     | ✅ 完了  | `logging_service.py`                                   |
| 8.3  | セッション操作ログ記録       | ✅ 完了  | `logging_service.py`                                   |
| 8.4  | 課金サービス実行ログ記録     | ✅ 完了  | `logging_service.py`                                   |
| 8.5  | セキュリティイベントログ記録 | ✅ 完了  | `logging_service.py`, `security_monitoring_service.py` |

## まとめ

本実装により、以下の機能が完全に実装されました:

1. **包括的なログ記録**: 認証、登録、セッション、課金、セキュリティの全てのイベントを記録
2. **セキュリティ監視**: リアルタイムでセキュリティ脅威を検出し、自動アラートを生成
3. **CloudWatch Logs 統合**: 重要なログを CloudWatch Logs に送信し、集中管理と長期保存を実現
4. **監査対応**: コンプライアンス要件に対応した詳細なログ記録

これにより、要件 8.1-8.5 が完全に満たされ、セキュリティとコンプライアンスの両面で強固なシステムが構築されました。
