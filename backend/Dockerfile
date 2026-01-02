# backend/Dockerfile

# Python 3.11 (またはローカル環境に合わせたバージョン) の軽量イメージを使用
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# 音声処理ライブラリ(librosa等)に必要なシステム依存関係をインストール
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# Cloud Run は環境変数 PORT (デフォルト8080) を提供するため、それを使用
ENV PORT=8080

# uvicornサーバーを起動
# exec を使うことでシグナルハンドリングを適切に行います
CMD exec uvicorn app:app --host 0.0.0.0 --port $PORT