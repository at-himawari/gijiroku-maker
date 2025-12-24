# 議事録メーカー インフラストラクチャ

AWS CDK を使用した議事録メーカーのインフラストラクチャ定義です。

## 前提条件

- Node.js 18 以上
- AWS CLI 設定済み
- AWS CDK CLI インストール済み

## セットアップ

```bash
# 依存関係のインストール
npm install

# CDKのブートストラップ（初回のみ）
npx cdk bootstrap

# スタックのデプロイ
npm run deploy
```

## デプロイされるリソース

### AWS Cognito

- **User Pool**: ユーザー認証管理
  - メールアドレス + パスワード認証
  - SMS MFA（必須）
  - パスワードポリシー（8 文字以上、英数字記号必須）
- **User Pool Client**: アプリケーション連携
  - OAuth 2.0 フロー対応
  - トークン有効期限設定
- **Identity Pool**: AWS リソースアクセス用

### Systems Manager Parameter Store

- `/gijiroku-maker/cognito/user-pool-id`
- `/gijiroku-maker/cognito/client-id`
- `/gijiroku-maker/cognito/identity-pool-id`

## 環境変数の取得

デプロイ後、以下のコマンドで環境変数を取得できます：

```bash
# User Pool ID
aws ssm get-parameter --name "/gijiroku-maker/cognito/user-pool-id" --query "Parameter.Value" --output text

# Client ID
aws ssm get-parameter --name "/gijiroku-maker/cognito/client-id" --query "Parameter.Value" --output text
```

## コマンド

```bash
# ビルド
npm run build

# デプロイ
npm run deploy

# スタック削除
npm run destroy

# CloudFormation テンプレート生成
npm run synth
```
