# Cognito 移行ガイド

このガイドでは、既存の電話番号認証システムから Cognito メールアドレス+パスワード認証システムへの移行手順を説明します。

## 移行の概要

### 移行前の状態

- 電話番号 + SMS 認証コード
- ユーザーデータは`users`テーブルに`phone_number`で管理

### 移行後の状態

- メールアドレス + パスワード認証（Cognito）
- ユーザーデータは`users`テーブルに`cognito_username`で管理
- 既存のユーザー ID は保持される

## 前提条件

1. AWS Cognito ユーザープールが設定済みであること
2. 必要な環境変数が設定されていること
3. データベースに`system_settings`テーブルが作成されていること

## 移行手順

### 1. 事前準備

#### 1.1 system_settings テーブルの作成

```bash
mysql -u [username] -p [database_name] < create_system_settings_table.sql
```

#### 1.2 既存ユーザーの確認

```bash
python migrate_to_cognito.py --dry-run
```

### 2. 移行方法の選択

#### 方法 A: 対話式移行（推奨）

```bash
python migrate_to_cognito.py
```

この方法では：

- 既存ユーザーの一覧が表示されます
- 各ユーザーに対して Cognito メールアドレスを手動で入力します
- リアルタイムで移行状況を確認できます

#### 方法 B: CSV 一括移行

```bash
python migrate_to_cognito.py --csv migration_data.csv
```

CSV ファイルの形式：

```csv
phone_number,cognito_email
+81901234567,user1@example.com
+81901234568,user2@example.com
```

### 3. 移行プロセス

#### 3.1 各ユーザーの移行手順

1. **Cognito アカウントの事前作成**

   - 各ユーザーに対して Cognito アカウントを作成
   - メールアドレス、パスワード、氏名、電話番号を設定

2. **移行スクリプトの実行**

   - 電話番号ユーザーと Cognito ユーザーのマッピングを作成
   - 既存の user_id を保持してデータの整合性を確保

3. **移行ログの記録**
   - 移行操作はすべてログに記録されます
   - `cognito_migration_log_YYYYMMDD_HHMMSS.json`ファイルが生成されます

#### 3.2 移行状態の管理

移行中は以下の状態が管理されます：

- `not_started`: 移行未開始
- `in_progress`: 移行進行中
- `completed`: 移行完了
- `failed`: 移行失敗

### 4. 移行完了後の処理

#### 4.1 旧システムの無効化

全ユーザーの移行が完了した場合：

```bash
# 移行スクリプト内で自動的に提案されます
# または手動で実行：
UPDATE system_settings
SET setting_value = 'true'
WHERE setting_key = 'phone_auth_disabled';
```

#### 4.2 動作確認

1. **新しい認証エンドポイントの確認**

   ```bash
   curl -X POST http://localhost:8000/auth/cognito/login \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"password"}'
   ```

2. **旧エンドポイントの無効化確認**

   ```bash
   curl -X POST http://localhost:8000/auth/signin/initiate \
     -H "Content-Type: application/json" \
     -d '{"phone_number":"+81901234567"}'
   # 期待される応答: 410 Gone
   ```

3. **移行状態の確認**
   ```bash
   curl http://localhost:8000/auth/migration/status
   ```

## トラブルシューティング

### よくある問題

#### 1. Cognito ユーザーが見つからない

**エラー**: `Cognitoユーザー user@example.com が見つかりません`

**解決方法**:

- AWS Cognito コンソールでユーザーが作成されているか確認
- メールアドレスのスペルミスがないか確認
- Cognito ユーザープールの設定を確認

#### 2. データベース接続エラー

**エラー**: `データベース接続に失敗しました`

**解決方法**:

- `.env`ファイルのデータベース設定を確認
- データベースサーバーが起動しているか確認
- 接続権限を確認

#### 3. 移行の部分的失敗

**エラー**: 一部のユーザーの移行に失敗

**解決方法**:

- 移行ログファイルを確認して失敗原因を特定
- 失敗したユーザーのみ再実行
- 必要に応じて手動でデータを修正

### ログファイルの確認

#### 移行ログ

```bash
# 移行操作の詳細ログ
cat cognito_migration_log_YYYYMMDD_HHMMSS.json

# アプリケーションログ
tail -f cognito_migration.log
```

#### データベースログ

```sql
-- 認証ログの確認
SELECT * FROM auth_logs
WHERE details LIKE '%migration%'
ORDER BY created_at DESC;

-- システム設定の確認
SELECT * FROM system_settings
WHERE setting_key LIKE '%migration%' OR setting_key LIKE '%phone_auth%';
```

## ロールバック手順

移行に問題が発生した場合のロールバック：

### 1. 旧システムの再有効化

```sql
UPDATE system_settings
SET setting_value = 'false'
WHERE setting_key = 'phone_auth_disabled';
```

### 2. Cognito マッピングの削除

```sql
-- 注意: 実行前にバックアップを取得してください
UPDATE users
SET cognito_username = NULL
WHERE cognito_username IS NOT NULL;
```

### 3. 移行状態のリセット

```sql
UPDATE system_settings
SET setting_value = 'not_started'
WHERE setting_key = 'cognito_migration_status';
```

## セキュリティ考慮事項

1. **移行中のアクセス制御**

   - 移行中は両方の認証方式が有効
   - 移行完了まで旧システムへのアクセスを監視

2. **データの整合性**

   - 移行前後で user_id が変更されないことを確認
   - セッション情報の整合性を確認

3. **ログの管理**
   - 移行ログには機密情報が含まれる可能性があります
   - 適切なアクセス制御を設定してください

## サポート

移行に関する問題や質問がある場合は、以下の情報を含めてサポートに連絡してください：

1. 移行ログファイル
2. エラーメッセージ
3. 実行環境の詳細
4. 移行対象ユーザー数

## 参考資料

- [AWS Cognito ドキュメント](https://docs.aws.amazon.com/cognito/)
- [FastAPI ドキュメント](https://fastapi.tiangolo.com/)
- [MySQL ドキュメント](https://dev.mysql.com/doc/)
