# app.py
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
import json
import logging
from typing import List, Dict, Any, Optional
import io
import wave
import time
from datetime import datetime
from pydantic import BaseModel
from models import UserCreate, SessionCreate, AuthLogCreate, CognitoRegisterRequest, CognitoLoginRequest, CognitoRefreshTokenRequest, CognitoLogoutRequest, CognitoPasswordResetRequest, CognitoPasswordResetConfirmRequest, CognitoPhoneVerificationRequest, CognitoResendVerificationRequest, UserProfileUpdateRequest, UserPreferencesUpdateRequest
from google.cloud import speech
from starlette.websockets import WebSocketState
from dotenv import load_dotenv
from database import db_manager
from auth_service import AuthService
from cognito_service import CognitoService
from auth_middleware import auth_middleware, require_auth, optional_auth, get_current_user
from security_middleware import SecurityMiddleware
from logging_service import logging_service
from session_manager import session_manager
from migration_middleware import migration_middleware
from security_monitoring_service import security_monitoring_service
from contextlib import asynccontextmanager
import stripe
from models import CheckoutSessionRequest

BUFFER_TIME_SECONDS = 30



# ログの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# dotenvを読み込む
load_dotenv()

# Stripe設定
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
stripe.api_key = STRIPE_API_KEY

# セキュリティミドルウェアを追加
allowed_origins = [
    "https://gijiroku-maker.at-himawari.com",
]

# アプリケーション起動時にデータベース接続を初期化
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup 処理 ---
    await db_manager.init_pool()
    # セッションマネージャーのクリーンアップタスクを開始
    await session_manager.start_cleanup_task()
    # セキュリティ監視クリーンアップタスクを開始
    asyncio.create_task(cleanup_security_monitoring())
    logger.info("アプリケーションが開始されました")
    
    yield
    
    # --- Shutdown 処理 ---
    await session_manager.stop_cleanup_task()
    await db_manager.close_pool()
    logger.info("アプリケーションが終了されました")

app = FastAPI(lifespan=lifespan)

# セキュリティミドルウェアを追加
app.add_middleware(SecurityMiddleware, allowed_origins=allowed_origins)

# 認証サービスのインスタンス
auth_service = AuthService()
cognito_service = CognitoService()

# セッションクリーンアップタスク
async def cleanup_sessions():
    """期限切れセッションを定期的にクリーンアップ"""
    while True:
        try:
            await asyncio.sleep(3600)  # 1時間ごとに実行
            result = await session_manager.cleanup_expired_sessions()
            if result['total_cleaned'] > 0:
                logger.info(f"期限切れセッションをクリーンアップしました: {result['total_cleaned']}件")
        except Exception as e:
            logger.error(f"セッションクリーンアップエラー: {e}")

# セキュリティ監視クリーンアップタスク
async def cleanup_security_monitoring():
    """セキュリティ監視キャッシュを定期的にクリーンアップ"""
    while True:
        try:
            await asyncio.sleep(7200)  # 2時間ごとに実行
            await security_monitoring_service.cleanup_security_cache()
            await rate_limiting_service.cleanup_expired_entries()
            logger.info("セキュリティ監視キャッシュをクリーンアップしました")
        except Exception as e:
            logger.error(f"セキュリティ監視クリーンアップエラー: {e}")



# Google Cloud の認証情報のパスを環境変数から取得
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if GOOGLE_CREDENTIALS_PATH:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS_PATH
    logger.info(f"Google Cloud 認証情報パス設定済み: {GOOGLE_CREDENTIALS_PATH}")
else:
    logger.warning("GOOGLE_APPLICATION_CREDENTIALS が設定されていません")

GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GOOGLE_REGION="asia-northeast1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 新しいGoogle Genai クライアントを初期化
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
あなたは企業の議事録作成担当者です。与えられたフォーマットに従って議事録を作成してください。
不明な部分は曖昧に回答せず、｢不明｣と明言してください。
"""

audio_buffer = bytearray()

# CORS設定
origins = [
    "https://gijiroku-maker.at-himawari.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# 接続管理クラス
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        # クライアントが要求しているサブプロトコルを取得
        requested_protocols = websocket.scope.get("subprotocols", [])
        selected_protocol = None
        if "cognito-auth" in requested_protocols:
            selected_protocol = "cognito-auth"
        
        # サブプロトコルを明示的に指定して接続を承認（重要：これがないとブラウザ側で切断される）
        await websocket.accept(subprotocol=selected_protocol)
        self.active_connections.append(websocket)
        logger.info(f"New connection. Selected protocol: {selected_protocol}. Total connections: {len(self.active_connections)}")

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
# 議事録生成関数 (Gemini版)
async def generate_minutes(transcript: str):
    format_text = """ 以下のフォーマットに従って議事録を作成してください。わからない部分は、曖昧に回答せず、不明と記述するようにしてください。
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
    
    # プロンプトの組み立て
    # システムプロンプトはモデル初期化時に設定済みです
    prompt = f"{format_text}\n\n以下は会議の文字起こしです。これを基に議事録を作成してください：\n\n{transcript}"

    try:
        # 新しいGoogle Genai APIを使用
        full_prompt = f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
        
        response = await client.aio.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=full_prompt
        )
        
        # テキスト部分を取得
        return response.text
    except Exception as e:
        logger.error(f"Error generating minutes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="議事録の生成中にエラーが発生しました。")
    

@app.post("/payment/create-checkout-session")
async def create_checkout_session(request: CheckoutSessionRequest, auth_context: Dict = Depends(require_auth)):
    """Stripe Checkout Sessionを作成"""
    user = auth_context['user']
    try:
        # 30分 = 500円
        unit_amount = 500
        quantity = request.quantity
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'jpy',
                    'product_data': {
                        'name': '議事録作成クレジット (30分)',
                        'description': '音声認識と議事録作成のための追加時間（30分単位）',
                    },
                    'unit_amount': unit_amount,
                },
                'quantity': quantity,
            }],
            mode='payment',
            success_url=f"{allowed_origins[0]}/?payment=success",
            cancel_url=f"{allowed_origins[0]}/?payment=cancel",
            client_reference_id=user.cognito_user_sub,
            metadata={
                'user_id': user.user_id,
                'cognito_sub': user.cognito_user_sub,
                'add_seconds': str(1800 * quantity) # 30分 * 60秒 * 個数
            }
        )
        return {"url": checkout_session.url}
    except Exception as e:
        logger.error(f"Stripe session creation error: {e}")
        raise HTTPException(status_code=500, detail="決済セッションの作成に失敗しました")

@app.post("/payment/webhook")
async def stripe_webhook(request: Request):
    """Stripe Webhook ハンドラ"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 決済完了イベントの処理
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # メタデータからユーザー情報と追加時間を取得
        cognito_sub = session.get('client_reference_id')
        metadata = session.get('metadata', {})
        add_seconds = float(metadata.get('add_seconds', 1800))
        
        if cognito_sub:
            success = await db_manager.add_balance(cognito_sub, add_seconds)
            if success:
                logger.info(f"Payment successful for {cognito_sub}: Added {add_seconds} seconds")
            else:
                logger.error(f"Failed to add balance for {cognito_sub}")

    return {"status": "success"}

# 議事録生成エンドポイント（認証必須）
@app.post("/generate_minutes")
async def generate_minutes_endpoint(request: TranscriptRequest, auth_context: Dict = Depends(require_auth), http_request: Request = None):
    user = auth_context['user']
    client_ip = http_request.client.host if http_request and http_request.client else None
    
    logger.info(f"Generating minutes for user: {user.user_id}")
    
    # 課金処理開始ログ
    user_identifier = getattr(user, 'email', None) or getattr(user, 'phone_number', None) or user.user_id
    await logging_service.log_billing_service_execution(
        user.user_id, user_identifier, "generate_minutes", 0.0, "started", 
        {"service": "generate_minutes", "transcript_length": len(request.transcript)}, 
        client_ip
    )
    
    # セキュリティ監視: 課金サービス実行を監視
    await security_monitoring_service.monitor_billing_service_execution(
        user.user_id, user_identifier, "generate_minutes", 0.0, "started",
        {"service": "generate_minutes", "transcript_length": len(request.transcript)},
        client_ip
    )
    
    try:
        minutes = await generate_minutes(request.transcript)
        await manager.broadcast({"type": "minutes", "text": minutes})
        
        # 使用回数をインクリメント
        await db_manager.increment_usage_count(user.cognito_user_sub, 1)
        
        # 課金処理成功ログ（実際の課金額は0円だが、将来の拡張のため）
        await logging_service.log_billing_service_execution(
            user.user_id, user_identifier, "generate_minutes", 0.0, "success", 
            {"service": "generate_minutes", "transcript_length": len(request.transcript), "minutes_length": len(minutes)}, 
            client_ip
        )
        
        # セキュリティ監視: 課金サービス成功を監視
        await security_monitoring_service.monitor_billing_service_execution(
            user.user_id, user_identifier, "generate_minutes", 0.0, "success",
            {"service": "generate_minutes", "transcript_length": len(request.transcript), "minutes_length": len(minutes)},
            client_ip
        )
        
        # レスポンス作成
        response_data = {
            "minutes": minutes,
            "user_id": user.user_id
        }
        
        # トークンがリフレッシュされた場合、新しいトークンを含める
        if auth_context.get('token_refreshed'):
            response_data['token_refreshed'] = True
            response_data['new_access_token'] = auth_context.get('new_access_token')
            response_data['new_id_token'] = auth_context.get('new_id_token')
        
        return response_data
        
    except HTTPException as e:
        logger.error(f"Error in generate_minutes_endpoint: {e}", exc_info=True)
        
        # 課金処理失敗ログ
        await logging_service.log_billing_service_execution(
            user.user_id, user_identifier, "generate_minutes", 0.0, "failure", 
            {"service": "generate_minutes", "error": str(e.detail)}, 
            client_ip
        )
        
        # セキュリティ監視: 課金サービス失敗を監視
        await security_monitoring_service.monitor_billing_service_execution(
            user.user_id, user_identifier, "generate_minutes", 0.0, "failure",
            {"service": "generate_minutes", "error": str(e.detail)},
            client_ip
        )
        
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

# 認証関連のリクエストモデル
class PhoneAuthRequest(BaseModel):
    phone_number: str

class VerifyCodeRequest(BaseModel):
    phone_number: str
    code: str
    session: str

class LogoutRequest(BaseModel):
    access_token: str

# 認証API エンドポイント

@app.post("/auth/signup/initiate")
async def initiate_signup(request: PhoneAuthRequest, http_request: Request):
    """新規登録のSMS認証を開始"""
    try:
        # 移行チェック - 電話番号認証が無効化されているかチェック
        migration_error = await migration_middleware.check_phone_auth_endpoint(http_request)
        if migration_error:
            raise migration_error
        
        client_ip = http_request.client.host if http_request.client else None
        result = await auth_service.initiate_signup(request.phone_number, client_ip)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"登録開始エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/signup/verify")
async def verify_signup(request: VerifyCodeRequest, http_request: Request):
    """新規登録のSMS認証コードを検証"""
    try:
        # 移行チェック - 電話番号認証が無効化されているかチェック
        migration_error = await migration_middleware.check_phone_auth_endpoint(http_request)
        if migration_error:
            raise migration_error
        
        client_ip = http_request.client.host if http_request.client else None
        result = await auth_service.verify_signup_code(
            request.phone_number, 
            request.code, 
            request.session, 
            client_ip
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"登録検証エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/signin/initiate")
async def initiate_signin(request: PhoneAuthRequest, http_request: Request):
    """サインインのSMS認証を開始"""
    try:
        # 移行チェック - 電話番号認証が無効化されているかチェック
        migration_error = await migration_middleware.check_phone_auth_endpoint(http_request)
        if migration_error:
            raise migration_error
        
        client_ip = http_request.client.host if http_request.client else None
        result = await auth_service.initiate_signin(request.phone_number, client_ip)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"サインイン開始エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/signin/verify")
async def verify_signin(request: VerifyCodeRequest, http_request: Request):
    """サインインのSMS認証コードを検証"""
    try:
        # 移行チェック - 電話番号認証が無効化されているかチェック
        migration_error = await migration_middleware.check_phone_auth_endpoint(http_request)
        if migration_error:
            raise migration_error
        
        client_ip = http_request.client.host if http_request.client else None
        result = await auth_service.verify_signin_code(
            request.phone_number, 
            request.code, 
            request.session, 
            client_ip
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"サインイン検証エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/verify-session")
async def verify_session_endpoint(request: LogoutRequest):
    """セッションを検証"""
    try:
        result = await auth_service.verify_session(request.access_token)
        return result
    except Exception as e:
        logger.error(f"セッション検証エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/logout")
async def logout_endpoint(request: LogoutRequest, http_request: Request):
    """ログアウト"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await auth_service.logout(request.access_token, client_ip)
        return result
    except Exception as e:
        logger.error(f"ログアウトエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

# トークン検証エンドポイント
@app.get("/auth/validate")
async def validate_token(auth_context: Dict = Depends(require_auth)):
    """トークンの有効性を検証"""
    try:
        user = auth_context['user']
        return {
            'success': True,
            'valid': True,
            'user_id': user.user_id
        }
    except Exception as e:
        logger.error(f"トークン検証エラー: {e}")
        raise HTTPException(status_code=401, detail="無効なトークンです。")

# 保護されたエンドポイントの例

@app.get("/protected/profile")
async def get_user_profile(auth_context: Dict = Depends(require_auth)):
    """ユーザープロフィール取得（認証必須）"""
    try:
        user = auth_context['user']
        return {
            'success': True,
            'user': {
                'user_id': user.user_id,
                'phone_number': user.phone_number,
                'created_at': user.created_at.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'is_active': user.is_active
            }
        }
    except Exception as e:
        logger.error(f"プロフィール取得エラー: {e}")
        raise HTTPException(status_code=500, detail="プロフィール取得に失敗しました。")

@app.get("/protected/session-info")
async def get_session_info(auth_context: Dict = Depends(require_auth)):
    """セッション情報取得（認証必須）"""
    try:
        session = auth_context['session']
        return {
            'success': True,
            'session': {
                'session_id': session.session_id,
                'expires_at': session.expires_at.isoformat(),
                'created_at': session.created_at.isoformat(),
                'last_activity': session.last_activity.isoformat(),
                'is_active': session.is_active
            }
        }
    except Exception as e:
        logger.error(f"セッション情報取得エラー: {e}")
        raise HTTPException(status_code=500, detail="セッション情報取得に失敗しました。")

@app.get("/public/status")
async def get_public_status(http_request: Request):
    """パブリックステータス（認証不要）"""
    try:
        # オプショナル認証を使用 - 認証されていなくてもアクセス可能
        auth_context = await optional_auth(http_request)
        
        return {
            'success': True,
            'status': 'サービスは正常に動作しています',
            'authenticated': auth_context.get('authenticated', False),
            'user_id': auth_context['user'].user_id if auth_context.get('user') else None,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"パブリックステータス取得エラー: {e}")
        return {
            'success': False,
            'error': 'status_error',
            'message': 'ステータス取得に失敗しました。'
        }

# Cognito メールアドレス + パスワード認証 API エンドポイント

@app.post("/auth/cognito/register")
async def cognito_register(request: CognitoRegisterRequest, http_request: Request):
    """Cognito 新規ユーザー登録（SMS認証付き）"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.register_user(request, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognito登録エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/verify-phone")
async def cognito_verify_phone(request: CognitoPhoneVerificationRequest, http_request: Request):
    """Cognito SMS認証コード検証"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        
        result = await cognito_service.verify_phone_verification_code(
            request.email, 
            request.verification_code, 
            request.session, 
            client_ip
        )
        return result
    except Exception as e:
        logger.error(f"Cognito SMS認証検証エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/resend-verification")
async def cognito_resend_verification(request: CognitoResendVerificationRequest, http_request: Request):
    """Cognito SMS認証コード再送信"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        
        result = await cognito_service.resend_phone_verification_code(
            request.email, 
            client_ip
        )
        return result
    except Exception as e:
        logger.error(f"Cognito SMS認証再送信エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/send-phone-verification")
async def cognito_send_phone_verification(request: CognitoResendVerificationRequest, http_request: Request):
    """Cognito SMS認証コード送信（独立エンドポイント）"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        
        result = await cognito_service.send_phone_verification_code(
            request.email, 
            client_ip
        )
        return result
    except Exception as e:
        logger.error(f"Cognito SMS認証コード送信エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/cognito/phone-verification-status/{email}")
async def cognito_phone_verification_status(email: str, http_request: Request):
    """Cognito 電話番号認証状態確認"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        
        result = await cognito_service.get_phone_verification_status(email, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognito 電話番号認証状態確認エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/login")
async def cognito_login(request: CognitoLoginRequest, http_request: Request):
    """Cognito ユーザーログイン"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.login_user(request, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognitoログインエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/refresh")
async def cognito_refresh_token(request: CognitoRefreshTokenRequest, http_request: Request):
    """Cognito トークンリフレッシュ"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.refresh_token(request.refresh_token, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognitoトークンリフレッシュエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/logout")
async def cognito_logout(request: CognitoLogoutRequest, http_request: Request):
    """Cognito ログアウト"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.logout(request.access_token, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognitoログアウトエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/password-reset/request")
async def cognito_request_password_reset(request: CognitoPasswordResetRequest, http_request: Request):
    """Cognito パスワードリセット要求"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.request_password_reset(request.email, client_ip)
        return result
    except Exception as e:
        logger.error(f"Cognitoパスワードリセット要求エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/password-reset/confirm")
async def cognito_confirm_password_reset(request: CognitoPasswordResetConfirmRequest, http_request: Request):
    """Cognito パスワードリセット実行"""
    try:
        client_ip = http_request.client.host if http_request.client else None
        result = await cognito_service.confirm_password_reset(
            request.email, 
            request.confirmation_code, 
            request.new_password, 
            client_ip
        )
        return result
    except Exception as e:
        logger.error(f"Cognitoパスワードリセット実行エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/cognito/validate")
async def cognito_validate_session(request: Request):
    """Cognito セッション検証"""
    try:
        # Authorization ヘッダーからトークンを取得
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {
                'success': False,
                'error': 'missing_token',
                'message': 'アクセストークンが必要です。'
            }
        
        access_token = auth_header.split(' ')[1]
        result = await cognito_service.verify_session(access_token)
        return result
    except Exception as e:
        logger.error(f"Cognitoセッション検証エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/cognito/token-info")
async def cognito_token_info(request: Request):
    """Cognito トークン有効期限情報取得"""
    try:
        from cognito_token_service import cognito_token_service
        
        # Authorization ヘッダーからトークンを取得
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {
                'success': False,
                'error': 'missing_token',
                'message': 'アクセストークンが必要です。'
            }
        
        access_token = auth_header.split(' ')[1]
        result = await cognito_token_service.get_token_expiry_info(access_token)
        return result
    except Exception as e:
        logger.error(f"Cognitoトークン情報取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/cognito/auto-refresh")
async def cognito_auto_refresh(http_request: Request):
    """Cognito 自動トークンリフレッシュ"""
    try:
        from cognito_token_service import cognito_token_service
        
        # Authorization ヘッダーからトークンを取得
        auth_header = http_request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {
                'success': False,
                'error': 'missing_token',
                'message': 'アクセストークンが必要です。'
            }
        
        access_token = auth_header.split(' ')[1]
        client_ip = http_request.client.host if http_request.client else None
        
        # トークン検証と自動リフレッシュを実行
        result = await cognito_token_service.validate_and_sync_session(access_token, client_ip)
        
        if result['success']:
            response_data = {
                'success': True,
                'user_id': result['user'].user_id,
                'message': 'トークン検証成功'
            }
            
            # トークンがリフレッシュされた場合、新しいトークンを返す
            if result.get('token_refreshed'):
                response_data.update({
                    'token_refreshed': True,
                    'new_access_token': result.get('new_access_token'),
                    'new_id_token': result.get('new_id_token'),
                    'message': 'トークンを自動リフレッシュしました。'
                })
            
            return response_data
        else:
            return {
                'success': False,
                'error': result['error'],
                'message': result['message']
            }
            
    except Exception as e:
        logger.error(f"Cognito自動リフレッシュエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/session/info")
async def get_session_info(auth_context: Dict = Depends(require_auth)):
    """現在のセッション情報を取得"""
    try:
        session = auth_context['session']
        session_info = await session_manager.get_session_info(session.session_id)
        
        if session_info:
            return {
                'success': True,
                'session': session_info
            }
        else:
            return {
                'success': False,
                'error': 'session_not_found',
                'message': 'セッション情報が見つかりません。'
            }
    except Exception as e:
        logger.error(f"セッション情報取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/session/list")
async def list_user_sessions(auth_context: Dict = Depends(require_auth)):
    """ユーザーのアクティブセッション一覧を取得"""
    try:
        user = auth_context['user']
        sessions = await session_manager.get_user_active_sessions(user.user_id)
        
        return {
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        }
    except Exception as e:
        logger.error(f"セッション一覧取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/session/invalidate")
async def invalidate_session(auth_context: Dict = Depends(require_auth), http_request: Request = None):
    """現在のセッションを無効化（ログアウト）"""
    try:
        session = auth_context['session']
        client_ip = http_request.client.host if http_request and http_request.client else None
        
        success = await session_manager.invalidate_session(session.session_id, "user_logout", client_ip)
        
        if success:
            return {
                'success': True,
                'message': 'セッションを無効化しました。'
            }
        else:
            return {
                'success': False,
                'error': 'invalidation_failed',
                'message': 'セッション無効化に失敗しました。'
            }
    except Exception as e:
        logger.error(f"セッション無効化エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/session/invalidate-all")
async def invalidate_all_sessions(auth_context: Dict = Depends(require_auth), http_request: Request = None):
    """ユーザーの全セッションを無効化"""
    try:
        user = auth_context['user']
        client_ip = http_request.client.host if http_request and http_request.client else None
        
        count = await session_manager.invalidate_user_sessions(user.user_id, "user_logout_all", client_ip)
        
        return {
            'success': True,
            'invalidated_count': count,
            'message': f'{count}件のセッションを無効化しました。'
        }
    except Exception as e:
        logger.error(f"全セッション無効化エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/auth/session/extend")
async def extend_session_endpoint(auth_context: Dict = Depends(require_auth), http_request: Request = None):
    """セッションの有効期限を延長"""
    try:
        session = auth_context['session']
        client_ip = http_request.client.host if http_request and http_request.client else None
        
        # セッションを24時間延長
        from session_manager import session_manager
        result = await session_manager.extend_session(session.session_id, 24)
        
        if result['success']:
            return {
                'success': True,
                'expires_at': result['expires_at'],
                'extension_hours': result['extension_hours'],
                'message': result['message']
            }
        else:
            return {
                'success': False,
                'error': result['error'],
                'message': result['message']
            }
            
    except Exception as e:
        logger.error(f"セッション延長エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/auth/session/statistics")
async def get_session_statistics(auth_context: Dict = Depends(require_auth)):
    """セッション統計情報を取得（管理者用）"""
    try:
        stats = await session_manager.get_session_statistics()
        
        return {
            'success': True,
            'statistics': stats
        }
    except Exception as e:
        logger.error(f"セッション統計取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.get("/security/monitoring/summary")
async def get_security_monitoring_summary(auth_context: Dict = Depends(require_auth), time_window_hours: int = 24):
    """セキュリティ監視サマリーを取得（管理者用）"""
    try:
        # 管理者権限チェック（簡易実装）
        user = auth_context['user']
        
        # セキュリティサマリーを取得
        summary = await security_monitoring_service.get_security_summary(time_window_hours)
        
        return {
            'success': True,
            'security_summary': summary,
            'requested_by': user.user_id
        }
    except Exception as e:
        logger.error(f"セキュリティ監視サマリー取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.post("/security/monitoring/cleanup")
async def cleanup_security_monitoring_cache(auth_context: Dict = Depends(require_auth)):
    """セキュリティ監視キャッシュをクリーンアップ（管理者用）"""
    try:
        # 管理者権限チェック（簡易実装）
        user = auth_context['user']
        
        # セキュリティキャッシュをクリーンアップ
        await security_monitoring_service.cleanup_security_cache()
        
        return {
            'success': True,
            'message': 'セキュリティ監視キャッシュをクリーンアップしました。',
            'cleaned_by': user.user_id
        }
    except Exception as e:
        logger.error(f"セキュリティ監視キャッシュクリーンアップエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket エンドポイント（キューベース音声処理）"""
    logger.info(f"=== WebSocket ハンドシェイク開始 ===")
    client_ip = websocket.client.host if websocket.client else None
    
    # 接続を承認
    await manager.connect(websocket)
    
    # 音声データ用キュー
    audio_queue = asyncio.Queue()
    user_context = {"user": None, "balance": 0.0, "session_usage": 0.0}

    # 【修正】クライアントをエンドポイント内で初期化
    async with speech.SpeechAsyncClient() as speech_client:
        
        async def request_generator():
            # Google STT への初期設定リクエスト
            streaming_config = speech.StreamingRecognitionConfig(
                config=speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    language_code="ja-JP",
                    enable_automatic_punctuation=True,
                    # model="default", # モデル指定を削除して自動選択に任せる
                ),
                interim_results=True
            )

            logger.info("STT: 設定を送信します")
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

            while True:
                # キューから音声データを取り出す
                audio_data = await audio_queue.get()
                if audio_data is None: # 終了合図
                    break

                # --- 課金ロジック: 残高チェック ---
                # 16kHz, 16bit(2bytes) -> 32000 bytes/sec
                chunk_seconds = len(audio_data) / 32000.0
                
                # バランスが不足している場合は停止
                if user_context["balance"] - (user_context["session_usage"] + chunk_seconds) < 0:
                    logger.warning(f"User {user_context['user'].user_id} run out of balance")
                    await manager.send_personal_message({
                        "type": "error", 
                        "message": "利用可能時間を使い切りました。クレジットを購入してください。"
                    }, websocket)
                    await websocket.close(code=4002) # 4002: Insufficient Balance
                    break

                user_context["session_usage"] += chunk_seconds
                yield speech.StreamingRecognizeRequest(audio_content=audio_data)
                
                yield speech.StreamingRecognizeRequest(audio_content=audio_data)
        async def stt_processor():
            """Google STTからのレスポンスを処理してクライアントに送るタスク"""
            logger.info("STT: プロセッサ起動")
            try:
                responses = await speech_client.streaming_recognize(requests=request_generator())
                
                async for response in responses:
                    if not response.results: continue
                    
                    for result in response.results:
                        if not result.alternatives: continue
                        transcript = result.alternatives[0].transcript
                        is_final = result.is_final
                        
                        await manager.send_personal_message({
                            "type": "transcription" if is_final else "immediate",
                            "text": transcript
                        }, websocket)
            except asyncio.CancelledError:
                logger.info("STTプロセッサキャンセル")
            except Exception as e:
                logger.error(f"STTプロセッサエラー: {e}", exc_info=True)
            finally:
                logger.info("STT: プロセッサ終了")
        # STT処理を別タスクで開始
        stt_task = asyncio.create_task(stt_processor())
        try:
            while True:
                message = await websocket.receive()
                
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        data = json.loads(message["text"])
                        if data.get("type") == "auth":
                            token = data.get("token")
                            auth_result = await auth_middleware.verify_websocket_auth(token, client_ip)
                            if auth_result['success']:
                                user = auth_result['user']
                                user_context["user"] = user
                                # DBから最新の残高を取得
                                app_data = await db_manager.get_app_user_data_by_cognito_sub(user.cognito_user_sub)
                                
                                if not app_data:
                                    logger.info(f"WebSocket: Creating initial data for {user.user_id}")
                                    app_data = await db_manager.create_app_user_data(user.cognito_user_sub)

                                user_context["balance"] = app_data.get("seconds_balance", 0.0) if app_data else 0.0
                                
                                logger.info(f"WebSocket認証成功: {user.user_id}, Balance: {user_context['balance']}s")
                                
                                # 残高情報をクライアントに送信
                                await manager.send_personal_message({
                                    "type": "balance_info",
                                    "balance": user_context["balance"]
                                }, websocket)
                            else:
                                await websocket.close(code=4001)
                                break
                    elif "bytes" in message:
                        if user_context["user"]:
                            await audio_queue.put(message["bytes"])
                            
                elif message["type"] == "websocket.disconnect":
                    break

        except WebSocketDisconnect:
            logger.info("WebSocket切断")
        finally:
            await audio_queue.put(None)
            try:
                # タイムアウト付きでタスク終了待ち
                await asyncio.wait_for(stt_task, timeout=1.0)
            except Exception:
                stt_task.cancel()
            
            # --- 最終的な使用量をDBから差し引く ---
            if user_context["user"] and user_context["session_usage"] > 0:
                used = user_context["session_usage"]
                await db_manager.deduct_balance(user_context["user"].cognito_user_sub, used)
                logger.info(f"Session closed. Deducted {used:.2f} seconds.")
            
            manager.disconnect(websocket)
                
@app.get("/auth/migration/status")
async def get_migration_status():
    """移行状態を取得"""
    try:
        status_info = await migration_middleware.get_migration_status()
        is_phone_disabled = await migration_middleware.is_phone_auth_disabled()
        
        return {
            'success': True,
            'phone_auth_disabled': is_phone_disabled,
            'migration_details': status_info,
            'available_auth_methods': {
                'cognito_email_password': True,
                'phone_sms': not is_phone_disabled
            }
        }
    except Exception as e:
        logger.error(f"移行状態取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'サーバーエラーが発生しました。'
        }

# ユーザープロフィール・データ管理 API エンドポイント

@app.get("/users/profile")
async def get_user_profile(auth_context: Dict = Depends(require_auth)):
    """ユーザープロフィール取得（Cognito属性 + アプリケーションデータ）"""
    try:
        user = auth_context['user']

        # ★修正: Cognito取得エラーを無視して続行するように try-except で囲む
        cognito_profile = {}
        try:
            cognito_profile = await cognito_service.get_user_profile(user.cognito_user_sub)
        except Exception as e:
            logger.warning(f"Cognitoプロフィール取得失敗（無視して続行）: {e}")
            # エラー時は最低限の情報をセット
            cognito_profile = {
                'email': getattr(user, 'email', None),
                'name': 'User'
            }
        
        # アプリケーションデータを取得
        app_data = await db_manager.get_app_user_data_by_cognito_sub(user.cognito_user_sub)
        
        # データが存在しない場合は作成
        if not app_data:
            app_data = await db_manager.create_app_user_data(user.cognito_user_sub)
        
        # 統合プロフィールを作成
        profile = {
            'user_id': user.user_id,
            'cognito_sub': user.cognito_user_sub,
            'email': cognito_profile.get('email') if cognito_profile else None,
            'name': cognito_profile.get('name') if cognito_profile else None,
            'phone_number': cognito_profile.get('phone_number') if cognito_profile else None,
            'email_verified': cognito_profile.get('email_verified', False) if cognito_profile else False,
            'phone_number_verified': cognito_profile.get('phone_number_verified', False) if cognito_profile else False,
            'subscription_status': app_data.get('subscription_status', 'free') if app_data else 'free',
            'seconds_balance': app_data.get('seconds_balance', 0.0) if app_data else 0.0,
            'usage_count': app_data.get('usage_count', 0) if app_data else 0,
            'monthly_usage_count': app_data.get('monthly_usage_count', 0) if app_data else 0,
            'preferences': app_data.get('preferences', {}) if app_data else {},
            'profile_data': app_data.get('profile_data', {}) if app_data else {},
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'is_active': user.is_active
        }
        
        return {
            'success': True,
            'profile': profile
        }
        
    except Exception as e:
        logger.error(f"ユーザープロフィール取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'プロフィール取得に失敗しました。'
        }

@app.put("/users/profile")
async def update_user_profile(request: UserProfileUpdateRequest, auth_context: Dict = Depends(require_auth)):
    """ユーザープロフィール更新（アプリケーションデータ）"""
    try:
        user = auth_context['user']
        
        # リクエストデータをフィルタリング（Noneでない値のみ）
        profile_updates = {}
        if request.display_name is not None:
            profile_updates['display_name'] = request.display_name
        if request.avatar_url is not None:
            profile_updates['avatar_url'] = request.avatar_url
        if request.timezone is not None:
            profile_updates['timezone'] = request.timezone
        
        # プロフィールを更新
        success = await db_manager.update_app_user_profile(user.cognito_user_sub, profile_updates)
        
        if success:
            # 更新後のプロフィールを取得
            updated_data = await db_manager.get_app_user_data_by_cognito_sub(user.cognito_user_sub)
            
            return {
                'success': True,
                'message': 'プロフィールを更新しました。',
                'profile_data': updated_data.get('profile_data', {}) if updated_data else {}
            }
        else:
            return {
                'success': False,
                'error': 'update_failed',
                'message': 'プロフィール更新に失敗しました。'
            }
        
    except Exception as e:
        logger.error(f"ユーザープロフィール更新エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'プロフィール更新に失敗しました。'
        }

@app.put("/users/preferences")
async def update_user_preferences(request: UserPreferencesUpdateRequest, auth_context: Dict = Depends(require_auth)):
    """ユーザー設定更新"""
    try:
        user = auth_context['user']
        
        # リクエストデータをフィルタリング（Noneでない値のみ）
        preferences_updates = {}
        if request.language is not None:
            preferences_updates['language'] = request.language
        if request.theme is not None:
            preferences_updates['theme'] = request.theme
        if request.notifications is not None:
            preferences_updates['notifications'] = request.notifications
        
        # 設定を更新
        success = await db_manager.update_app_user_preferences(user.cognito_user_sub, preferences_updates)
        
        if success:
            # 更新後の設定を取得
            updated_data = await db_manager.get_app_user_data_by_cognito_sub(user.cognito_user_sub)
            
            return {
                'success': True,
                'message': 'ユーザー設定を更新しました。',
                'preferences': updated_data.get('preferences', {}) if updated_data else {}
            }
        else:
            return {
                'success': False,
                'error': 'update_failed',
                'message': 'ユーザー設定更新に失敗しました。'
            }
        
    except Exception as e:
        logger.error(f"ユーザー設定更新エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'ユーザー設定更新に失敗しました。'
        }

@app.get("/users/usage-statistics")
async def get_user_usage_statistics(auth_context: Dict = Depends(require_auth)):
    """ユーザー使用統計取得"""
    try:
        user = auth_context['user']
        
        # 使用統計を取得
        stats = await db_manager.get_user_usage_statistics(user.cognito_user_sub)
        
        if stats:
            return {
                'success': True,
                'statistics': stats
            }
        else:
            return {
                'success': False,
                'error': 'stats_not_found',
                'message': '使用統計が見つかりません。'
            }
        
    except Exception as e:
        logger.error(f"使用統計取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': '使用統計取得に失敗しました。'
        }

@app.post("/users/usage/increment")
async def increment_user_usage(auth_context: Dict = Depends(require_auth)):
    """使用回数をインクリメント（内部API）"""
    try:
        user = auth_context['user']
        
        # 使用回数をインクリメント
        success = await db_manager.increment_usage_count(user.cognito_user_sub, 1)
        
        if success:
            # 更新後の統計を取得
            stats = await db_manager.get_user_usage_statistics(user.cognito_user_sub)
            
            return {
                'success': True,
                'message': '使用回数を更新しました。',
                'statistics': stats
            }
        else:
            return {
                'success': False,
                'error': 'increment_failed',
                'message': '使用回数更新に失敗しました。'
            }
        
    except Exception as e:
        logger.error(f"使用回数インクリメントエラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': '使用回数更新に失敗しました。'
        }

@app.get("/users/app-data")
async def get_user_app_data(auth_context: Dict = Depends(require_auth)):
    """ユーザーのアプリケーションデータ取得"""
    try:
        user = auth_context['user']
        
        # アプリケーションデータを取得
        app_data = await db_manager.get_app_user_data_by_cognito_sub(user.cognito_user_sub)
        
        # データが存在しない場合は作成
        if not app_data:
            app_data = await db_manager.create_app_user_data(user.cognito_user_sub)
        
        if app_data:
            return {
                'success': True,
                'app_data': app_data
            }
        else:
            return {
                'success': False,
                'error': 'data_not_found',
                'message': 'アプリケーションデータが見つかりません。'
            }
        
    except Exception as e:
        logger.error(f"アプリケーションデータ取得エラー: {e}")
        return {
            'success': False,
            'error': 'server_error',
            'message': 'アプリケーションデータ取得に失敗しました。'
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
