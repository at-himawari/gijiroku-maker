# app.py
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AzureOpenAI
import json
import logging
from typing import List, Dict, Any
import io
import wave
import time
from pydantic import BaseModel
from google.cloud.speech_v2.services.speech import SpeechAsyncClient
from google.cloud.speech_v2 import types
from starlette.websockets import WebSocketState
from dotenv import load_dotenv

BUFFER_TIME_SECONDS = 30

app = FastAPI()

# dotenvを読み込む
load_dotenv()

# Google Cloud の認証情報のパスを環境変数から取得
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GOOGLE_REGION="asia-northeast1"

audio_buffer = bytearray()

# CORS設定
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Geminiに修正
gpt_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT_ENDPOINT"),
    api_version="2024-02-15-preview",
    api_key=os.getenv("AZURE_API_KEY")
)

# Google Speech-to-Text 非同期クライアントの初期化
speech_client = SpeechAsyncClient(
    client_options={"api_endpoint": f"{GOOGLE_REGION}-speech.googleapis.com"}
)
# ログの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 接続管理クラス
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New connection. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Connection closed. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        try:
            await websocket.send_json(message)
            logger.debug(f"Sent message: {json.dumps(message)}")
        except WebSocketDisconnect:
            logger.warning("WebSocket disconnected while sending message")
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections.copy():
            try:
                await connection.send_json(message)
                logger.debug(f"Broadcasted message: {json.dumps(message)}")
            except WebSocketDisconnect:
                logger.warning("WebSocket disconnected during broadcast")
                self.disconnect(connection)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info("INFO:app:New connection. Total connections: 1")
    last_send_time = time.time()

    try:
        # Speech-to-Text の設定
        # 1. 認識の設定
        recognition_config = types.RecognitionConfig(
            explicit_decoding_config=types.ExplicitDecodingConfig(
                encoding=types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                audio_channel_count=1,
            ),
            language_codes=["ja-JP"],
            model="long", # V2の汎用モデル (latest_long なども可)
        )
        # 2. ストリーミング機能の設定 (中間結果など)
        streaming_features = types.StreamingRecognitionFeatures(
            interim_results=True
        )

        # 3. ストリーミング設定全体
        streaming_config = types.StreamingRecognitionConfig(
            config=recognition_config,
            streaming_features=streaming_features
        )

        # 4. Recognizerのリソースパス
        # ここではデフォルト設定("_")を使用。必要に応じて作成したRecognizer IDを指定
        recognizer_resource = f"projects/{GOOGLE_PROJECT_ID}/locations/{GOOGLE_REGION}/recognizers/_"

        # 非同期ジェネレータ関数
        async def request_generator():
            nonlocal last_send_time
            yield types.StreamingRecognizeRequest(
                    recognizer=recognizer_resource,
                    streaming_config=streaming_config
                )

            try:
                while True:
                    try:
                        data = await asyncio.wait_for(websocket.receive_bytes(), timeout=5)
                    except asyncio.TimeoutError:
                        logger.warning("No audio data received for 5 seconds.")
                        # 必要に応じて無音データを送信
                        silent_data = b'\x00' * 3200  # 0.1秒分の無音データ（16kHz, 16bit）
                        audio_buffer.extend(silent_data)
                        yield types.StreamingRecognizeRequest(audio=silent_data)
                        continue

                    logger.debug(f"Received audio data of size: {len(data)} bytes")

                    # 音声データをバッファに追加
                    audio_buffer.extend(data)

                    # Google Speech-to-Textにストリーミングリクエストを送信
                    yield types.StreamingRecognizeRequest(audio=data)

            except WebSocketDisconnect:
                logger.info("WebSocket disconnected during data reception.")
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                raise e
        try:
            responses = await speech_client.streaming_recognize(requests=request_generator())

            async for response in responses:
                if not response.results:
                    continue

                for result in response.results:
                    if not result.alternatives:
                        continue

                    transcript = result.alternatives[0].transcript

                    if result.is_final:
                        logger.info(f"Final transcript: {transcript}")
                        await manager.send_personal_message({"type": "transcription", "text": transcript}, websocket)
                    else:
                        logger.info(f"Interim transcript: {transcript}")
                        await manager.send_personal_message({"type": "immediate", "text": transcript}, websocket)
        
        except asyncio.CancelledError:
            # タスクがキャンセルされた場合（ブラウザ切断時など）
            logger.info("Stream processing cancelled (Client disconnected).")
            # ここでは何もしなくて良い（ループを抜けるだけでOK）
            
        except Exception as e:
            # その他のAPIエラーなど
            logger.error(f"Error in speech recognition loop: {e}")
            await manager.send_personal_message({"type": "error", "message": str(e)}, websocket)


    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in websocket_endpoint: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        manager.disconnect(websocket)

async def transcribe_audio(audio_data: bytes) -> str:
    try:
        sample_rate = 16000
        channels = 1
        wav_file = pcm_to_wav(audio_data, sample_rate, channels)
        wav_file.name = "audio.wav"

        return response.text
    except Exception as e:
        logger.error(f"Error in transcribe_audio: {e}")
        raise HTTPException(status_code=500, detail="音声認識中にエラーが発生しました。")

# TranscriptRequest モデル
class TranscriptRequest(BaseModel):
    transcript: str

# 議事録生成関数
async def generate_minutes(transcript: str):
    prompt = f"以下は会議の文字起こしです。これを基に議事録を作成してください：\n\n{transcript}"
    format = """ 以下のフォーマットに従って議事録を作成してください。わからない部分は、曖昧に回答せず、不明と記述するようにしてください。
                # 議題
                議題を簡潔に入力します。
                # 参加者
                参加者を入力します。不明な場合は不明と明記してください。
                # 依頼事項
                依頼事項を入力します。他部署の関係者に依頼すべきことはここに記入してください。
                # 決定事項
                決定事項を入力します。誰が何をいつまでにするか明記してください。締切や誰がが不明な場合は、不明と明記してください。
                # 議事内容
                議事詳細を入力します。誰が発言したかを（）内に示してください。不明な場合は、不明と明記してください。
            """
    try:
        response = gpt_client.chat.completions.create(
            model=None,
            messages=[
                {"role": "system", "content": "あなたは金融業界のITシステムに関する議事録作成者です。"},
                {"role": "assistant", "content": format},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            top_p=0.8,
            presence_penalty=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating minutes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="議事録の生成中にエラーが発生しました。")

# 議事録生成エンドポイント
@app.post("/generate_minutes")
async def generate_minutes_endpoint(request: TranscriptRequest):
    logger.info("Generating minutes")
    try:
        minutes = await generate_minutes(request.transcript)
        await manager.broadcast({"type": "minutes", "text": minutes})
        return {"minutes": minutes}
    except HTTPException as e:
        logger.error(f"Error in generate_minutes_endpoint: {e}", exc_info=True)
        return {"error": str(e.detail)}

def pcm_to_wav(pcm_data: bytes, sample_rate: int, num_channels: int) -> io.BytesIO:
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    wav_io.seek(0)
    return wav_io
