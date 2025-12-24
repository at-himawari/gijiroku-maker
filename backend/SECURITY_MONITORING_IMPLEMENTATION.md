# セキュリティ監視とログ実装サマリー

## 実装概要

AWS Cognito メールアドレス + パスワード認証システムの監査ログとセキュリティイベントログ機能を実装しました。

## 実装内容

### 1. Cognito 認証操作ログ（タスク 8.1）

以下の認証操作ログが既に実装されており、すべての認証フローに統合されています：

#### ユーザー登録ログ

- **関数**: `log_cognito_user_registration()`
- **記録内容**: メールアドレス、氏名、電話番号、Cognito User Sub、登録結果
- **統合場所**: `cognito_service.py` の `register_user()` メソッド

#### ユーザーログインログ

- **関数**: `log_cognito_user_login()`
- **記録内容**: メールアドレス、セッション ID、ログイン結果、IP アドレス
- **統合場所**: `cognito_service.py` の `login_user()` メソッド

#### ユーザーログアウトログ

- **関数**: `log_cognito_user_logout()`
- **記録内容**: メールアドレス、セッション ID、ログアウト理由、IP アドレス
- **統合場所**: `cognito_service.py` の `logout()` メソッド

#### 認証失敗ログ

- **関数**: `log_cognito_authentication_failure()`
- **記録内容**: メールアドレス、失敗タイプ、失敗理由、試行回数、IP アドレス
- **統合場所**: `cognito_service.py` の認証エラーハンドリング

#### パスワードリセットログ

- **関数**: `log_cognito_password_reset()`
- **記録内容**: メールアドレス、操作タイプ（request/confirm）、リセット結果
- **統合場所**: `cognito_service.py` の `request_password_reset()` と `confirm_password_reset()` メソッド

#### セッション操作ログ

- **関数**: `log_cognito_session_operation()`
- **記録内容**: メールアドレス、操作タイプ（created/refreshed/invalidated）、セッション ID、有効期限
- **統合場所**: `cognito_service.py` と `session_manager.py`

### 2. セキュリティイベントログ（タスク 8.2）

新しいセキュリティ監視サービス（`security_monitoring_service.py`）を実装し、以下の機能を追加しました：

#### ブルートフォース攻撃検出

- **関数**: `monitor_cognito_authentication_failure()`
- **検出条件**: 15 分間に 10 回以上の認証失敗
- **記録内容**: 攻撃タイプ、試行回数、時間範囲、IP アドレス
- **アクション**: `log_cognito_brute_force_attack()` でログ記録

#### クレデンシャルスタッフィング攻撃検出

- **関数**: `_detect_suspicious_ip_patterns()`
- **検出条件**: 同一 IP から 30 分間に 5 つ以上の異なるアカウントへの攻撃
- **記録内容**: 対象アカウント数、総試行回数、攻撃パターン
- **アクション**: `log_cognito_security_error()` でログ記録

#### 不正アクセス試行検出

- **関数**: `monitor_unauthorized_access_attempt()`
- **検出条件**: 30 分間に 5 回以上の不正アクセス試行
- **記録内容**: アクセスタイプ、エンドポイント、試行回数
- **アクション**: `log_cognito_unauthorized_access()` でログ記録

#### 課金サービス実行ログ

- **関数**: `monitor_billing_service_execution()`
- **記録内容**: ユーザー ID、サービス名、課金金額、実行結果、処理時刻
- **異常検出**:
  - 1 時間に 10 回以上の課金実行
  - 高額課金（1000 円以上）のアラート
- **統合場所**: `app.py` の `generate_minutes_endpoint()`

#### アカウントロック監視

- **関数**: `_monitor_account_lockout()`
- **監視内容**: 30 分間の失敗試行回数を監視
- **リスクレベル**: low/medium/high の 3 段階
- **アクション**: リスクレベルに応じたログ記録

### 3. セキュリティ監視エンドポイント

管理者用のセキュリティ監視エンドポイントを追加しました：

#### セキュリティサマリー取得

- **エンドポイント**: `GET /security/monitoring/summary`
- **パラメータ**: `time_window_hours` (デフォルト: 24 時間)
- **返却内容**:
  - ブルートフォース攻撃数
  - クレデンシャルスタッフィング攻撃数
  - 不正アクセス試行数
  - 高額課金アラート数
  - 異常課金パターン数
  - セキュリティ推奨事項

#### セキュリティキャッシュクリーンアップ

- **エンドポイント**: `POST /security/monitoring/cleanup`
- **機能**: 24 時間より古いセキュリティイベントキャッシュを削除

### 4. 自動クリーンアップタスク

アプリケーション起動時に以下のバックグラウンドタスクを開始：

- **セッションクリーンアップ**: 1 時間ごとに期限切れセッションを削除
- **セキュリティ監視クリーンアップ**: 2 時間ごとにセキュリティキャッシュを削除

## ログ記録の統合状況

### 既存の統合

1. **Cognito 認証サービス** (`cognito_service.py`)

   - ユーザー登録、ログイン、ログアウト
   - 認証失敗、パスワードリセット
   - セッション操作

2. **認証ミドルウェア** (`auth_middleware.py`)

   - トークン検証失敗
   - CSRF 検証失敗
   - SQL インジェクション試行
   - WebSocket 認証失敗

3. **レート制限サービス** (`rate_limiting_service.py`)
   - レート制限超過
   - ブルートフォース攻撃検出
   - IP ベース攻撃検出

### 新規統合

1. **セキュリティ監視サービス** (`security_monitoring_service.py`)

   - 包括的なセキュリティイベント監視
   - 異常パターン検出
   - リアルタイムアラート

2. **メインアプリケーション** (`app.py`)
   - 課金サービス実行監視
   - セキュリティサマリーエンドポイント

## セキュリティ閾値設定

```python
security_thresholds = {
    'brute_force_attempts': 10,              # 15分間での失敗試行回数
    'brute_force_window_minutes': 15,
    'suspicious_login_count': 5,             # 1時間での異常ログイン回数
    'suspicious_login_window_minutes': 60,
    'ip_ban_threshold': 50,                  # 1時間でのIP制限閾値
    'ip_ban_window_minutes': 60,
    'account_lockout_threshold': 5,          # アカウントロック閾値
    'account_lockout_window_minutes': 30
}
```

## データベーステーブル

すべてのログは `auth_logs` テーブルに記録されます：

```sql
CREATE TABLE auth_logs (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(36),
    email VARCHAR(255),
    event_type VARCHAR(50) NOT NULL,
    result VARCHAR(20) NOT NULL,
    details JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_email (email),
    INDEX idx_event_type (event_type),
    INDEX idx_result (result),
    INDEX idx_timestamp (timestamp)
);
```

## 使用方法

### セキュリティサマリーの取得

```bash
curl -X GET "http://localhost:8000/security/monitoring/summary?time_window_hours=24" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### セキュリティキャッシュのクリーンアップ

```bash
curl -X POST "http://localhost:8000/security/monitoring/cleanup" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 監視対象イベント

### 認証関連

- ✅ ユーザー登録（成功/失敗）
- ✅ ユーザーログイン（成功/失敗）
- ✅ ユーザーログアウト
- ✅ 認証失敗とアカウントロック
- ✅ パスワードリセット操作
- ✅ セッション作成・無効化

### セキュリティ関連

- ✅ ブルートフォース攻撃
- ✅ クレデンシャルスタッフィング攻撃
- ✅ 不正アクセス試行
- ✅ トークン検証失敗
- ✅ CSRF 検証失敗
- ✅ SQL インジェクション試行
- ✅ WebSocket 認証失敗

### 課金関連

- ✅ 課金サービス実行（開始/成功/失敗）
- ✅ 異常な課金パターン
- ✅ 高額課金アラート

## 要件との対応

### 要件 8.1（Cognito 認証操作ログ）

- ✅ Cognito ユーザー登録、ログイン、ログアウトのログ記録
- ✅ Cognito 認証失敗とアカウントロックのログ記録
- ✅ Cognito パスワードリセット操作のログ記録
- ✅ Cognito セッション作成・無効化のログ記録

### 要件 8.2（セキュリティイベントログ）

- ✅ Cognito ブルートフォース攻撃の検出とログ記録
- ✅ Cognito 不正アクセス試行のログ記録
- ✅ Cognito セキュリティエラーの詳細ログ記録
- ✅ 課金サービス実行時のログ記録

### 要件 8.3（監査ログ）

- ✅ ユーザー認証試行のログ記録（成功・失敗・理由）
- ✅ 新規ユーザー登録のログ記録（登録日時、メールアドレス、氏名）
- ✅ セッション操作の詳細ログ記録

### 要件 8.4（課金ログ）

- ✅ 課金サービス実行の詳細ログ記録
- ✅ ユーザー ID、課金金額、処理時刻、処理結果の記録

### 要件 8.5（セキュリティエラーログ）

- ✅ ブルートフォース攻撃などの攻撃可能性を含む詳細情報のログ記録
- ✅ セキュリティ関連エラーの包括的なログ記録

## まとめ

Cognito 認証システムの監査ログとセキュリティイベントログ機能が完全に実装され、すべての認証フローに統合されました。セキュリティ監視サービスにより、リアルタイムでセキュリティ脅威を検出し、適切にログ記録することができます。
