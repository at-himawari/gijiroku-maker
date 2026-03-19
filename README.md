# 議事録メーカー
Google-speech-to-textと Azure OpenAI Whisper,GPT-4o miniを利用した文字起こし＆議事録作成アプリです。
## 前提
- Google Cloud Platform（以降、GCP）とAzureに登録済みであることを前提とします。
- 動作確認端末は、Mac Book Air M2 2022(macOS Sonoma 14.4)です。

## 注意事項
- 想定読者は、ある程度クラウドサービスを触ったことのある方（AzureとGoogle Cloud Platform）を考えています。
- クラウドサービスは、従量課金制のため予め利用料金が予算の範囲内で収まるかの見積もりを行ってください。

## デモ
2024年3月27日午前の参議院･予算委員会の文字起こしデモです。  
![demo](/img/demo.gif)

## 環境変数
- ローカルで起動する際は、.envファイルを作成してください。その他のオプションとして、Google Cloud Runにデプロイするオプションがあります。（記載予定は未定）
- GCPのサービス アカウント キー（取得方法は後述（①））をダウンロードしてパスをGOOGLE_APPLICATION_CREDENTIALSに設定します。

backend/.env
```
GOOGLE_APPLICATION_CREDENTIALS=GCPのサービス アカウント キーのパス（例：./gijiroku-maker-******-************.json）
AZURE_WHISPER_ENDPOINT=AZURE_OPEN_AIのエンドポイント
（例：https://**********.openai.azure.com/openai/deployments/whisper/audio/transcriptions?api-version=2024-06-01
AZURE_GPT_ENDPOINT=AZURE_OPEN_AIのエンドポイント
https://**********.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-02-15-preview
AZURE_API_KEY=AZURE_OPEN_AIのキー（取得方法は後述（②））

```
frontend/.env
```
NEXT_PUBLIC_HOST=ホストのURL（例：localhost:8000）
```

### ①、②の取得方法
#### ①の取得方法
##### サービスアカウントの作成
GCP>コンソール>IAMと管理>サービスアカウント>サービスアカウントの作成（画像A）  

画像A.  

![画像A](/img/gcp/01.png)
- サービスアカウント名を入力します。
- 作成して続行を選択します。  (画像B)
  

画像B.
![画像B](/img/gcp/02.png)

- ロールにCloud Speech クライアントを割り当てます。(画像C)
- 続行を選択します。

画像C.    

![画像C](/img/gcp/03.png)  

- 完了を選択します。（画像D）  
  
画像D.
![画像D](/img/gcp/04.png)

##### 鍵の作成
- サービスアカウントの作成で、作成したアカウントのメニューから｢鍵を作成｣を選択します（画像E）  

画像E.
![画像E](/img/gcp/05.png)

- ｢鍵を追加｣を選択します。（画像F）  
- ｢新しい鍵を追加｣を選択します。

画像F.
![画像F](/img/gcp/06.png)

- キーのタイプ｢JSON｣を選択します。（画像G）  
- ｢作成｣を選択します。

画像G.
![画像G](/img/gcp/07.png)

- キーをローカルに保存します。パスは、このプロジェクトのbackendに配置してください。
- __この保存したファイル名が①となります。__


#### ②の取得方法
- Azure PortalのWebサイトを開きます。
##### リソースグループの作成
（既存のリソースグループにAzure OpenAIを作成する場合には、この手順はスキップしてください。）
- Azure Portalの検索窓に、リソースグループを入力し、リソースグループのページへアクセスします。
- ｢作成｣を選択します。（画像H）  

画像H.
![画像H](/img/azure/01.png)
- リソースグループ名とリージョンを入力します。（ここでは例として、リソースグループにgijiroku-maker-test、リージョンをJapan Eastとしています）（画像I）  
- ｢確認および作成｣を選択します。

画像I.
![画像I](/img/azure/02.png)  

- ｢作成｣を選択します（画像J）  

画像J.
![画像J](/img/azure/03.png)

##### Azure OpenAI リソースの作成
- Azure Portalの検索窓に、Azure OpenAIと入力し、Azure Open AIのページへアクセスします。
- ｢作成｣を選択します。（画像K）

画像K.
![画像K](/img/azure/04.png)

- 以下の必要事項を記入します。（画像L）
  - ｢リソースグループ｣：｢gijiroku-maker-test｣（リソースグループの作成手順で作成したもの）
  - ｢リージョン｣：｢East US 2｣ ※一部Whisperが使えないリージョンがあるので、East US 2を選択することを推奨します。
  - ｢名前｣：｢gijiroku-maker-test｣（任意の名前で構いません）
  - ｢価格レベル｣：｢Standard 0｣

画像L.
![画像L](/img/azure/05.png)

- ｢次へ｣を選択します。
- ｢インターネットを含むすべてのネットワークがこのリソースにアクセスできます。｣を選択します。（画像M）

画像M.
![画像M](/img/azure/06.png)
- ｢次へ｣を選択します。
- ｢次へ｣を選択します。（画像N）

画像N.
![画像N](/img/azure/07.png)

- ｢作成｣を選択します（画像O）

画像O.
![画像O](/img/azure/08.png)

- ｢リソースに移動｣を選択します。（画像P）

画像P.
![画像P](/img/azure/09.png)

- 左側のメニューから｢キーとエンドポイント｣を選択します。（画像Q）
- ｢キーを表示｣を選択します。（画像Q）
- __キー１が②です__（画像Q）
- また、環境変数 __AZURE_WHISPER_ENDPOINT__ と __AZURE_GPT_ENDPOINT__ には、ご自身のWEBページの画像Qの位置にあるエンドポイントを指定してください。

画像Q.
![画像Q](/img/azure/10.png)

##### GPTモデルデプロイ
- 左側のメニューから｢モデルデプロイ｣を選択します。（画像R）
- ｢展開の管理｣を選択します。（画像R）

画像R.
![画像R](/img/azure/11.png)

- 左側のメニューから｢デプロイ｣を選択します。（画像S）
- ｢モデルのデプロイ｣を選択します。（画像S）
- ｢基本モデルをデプロイする｣を選択します。（画像S）

画像S.
![画像S](/img/azure/12.png)

- ｢gpt-4o-mini｣を選択し、｢確認｣を選択します。（画像T）

画像T.
![画像T](/img/azure/13.png)

- ｢デプロイ｣を選択します（画像U）

画像U.
![画像U](/img/azure/14.png)

##### Whisperモデルデプロイ
画像R.
![画像R](/img/azure/11.png)

- 左側のメニューから｢デプロイ｣を選択します。（画像S）
- ｢モデルのデプロイ｣を選択します。（画像S）
- ｢基本モデルをデプロイ｣するを選択します。（画像S）

画像S.
![画像S](/img/azure/12.png)

- ｢whisper｣を選択し、｢確認｣を選択します。（画像V）

画像W.
![画像W](/img/azure/15.png)

- ｢選択したリソースにデプロイする｣を選択します（画像U）

画像U.
![画像U](/img/azure/16.png)


## 起動手順
### backend起動手順
- ディレクトリを移動します。`cd backend`
- `pip install -r requirements.txt`を実行します。
- `uvicorn app:app --reload`を実行します。

### frontend起動手順
- `npm run dev`を実行します。※本番用の手順は用意していません。

### アプリへアクセス
`http://localhost:3000`へWebブラウザでアクセスします。

## backendデプロイ
` gcloud run deploy gijiroku-backend --source . --region asia-northeast1 `