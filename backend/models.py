"""
データベースモデル定義
"""
from datetime import datetime, timedelta
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


class User(BaseModel):
    """ユーザーモデル（Cognito中心管理）"""
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # アプリケーション内部ID
    cognito_user_sub: str  # Cognito User Sub (一意識別子)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = True


class UserSession(BaseModel):
    """ユーザーセッションモデル（Cognito統合）"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # アプリケーション内部ユーザーID
    cognito_user_sub: str  # Cognito User Sub
    access_token: str  # Cognitoアクセストークン
    id_token: Optional[str] = None  # CognitoIDトークン
    refresh_token: Optional[str] = None  # Cognitoリフレッシュトークン
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


class AuthLog(BaseModel):
    """認証ログモデル（Cognito統合）"""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    email: Optional[str] = None  # phone_numberからemailに変更
    event_type: str  # "login_attempt", "register_attempt", "password_reset", etc.
    result: str      # "success", "failure", "error"
    # JSON文字列と辞書型の両方を許容（データベースからの読み込み時は辞書、保存直前はJSON文字列になる場合があるため）
    details: Any = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None


# データベース操作用のクラス
class UserCreate(BaseModel):
    """ユーザー作成用モデル（Cognito中心管理）"""
    cognito_user_sub: str  # Cognito User Sub のみ保存


class SessionCreate(BaseModel):
    """セッション作成用モデル（Cognito統合）"""
    user_id: str  # アプリケーション内部ユーザーID
    cognito_user_sub: str  # Cognito User Sub
    access_token: str  # Cognitoアクセストークン
    id_token: Optional[str] = None  # CognitoIDトークン
    refresh_token: Optional[str] = None  # Cognitoリフレッシュトークン
    expires_in: int = 3600  # 1時間（秒）
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


class AuthLogCreate(BaseModel):
    """認証ログ作成用モデル"""
    user_id: Optional[str] = None
    email: Optional[str] = None  # メールアドレス追加
    event_type: str
    result: str
    details: Any = Field(default_factory=dict)
    ip_address: Optional[str] = None


class CognitoRegisterRequest(BaseModel):
    """Cognito新規登録用モデル"""
    email: str
    password: str
    phone_number: str
    given_name: str
    family_name: str


class CognitoLoginRequest(BaseModel):
    """Cognitoログイン用モデル"""
    email: str
    password: str


class CognitoPasswordResetRequest(BaseModel):
    """Cognitoパスワードリセット要求用モデル"""
    email: str


class CognitoPasswordResetConfirmRequest(BaseModel):
    """Cognitoパスワードリセット確認用モデル"""
    email: str
    confirmation_code: str
    new_password: str


class CognitoRefreshTokenRequest(BaseModel):
    """Cognitoトークンリフレッシュ用モデル"""
    refresh_token: str


class CognitoLogoutRequest(BaseModel):
    """Cognitoログアウト用モデル"""
    access_token: str


class CognitoPhoneVerificationRequest(BaseModel):
    """Cognito電話番号認証コード検証用モデル"""
    email: str
    verification_code: str
    session: str


class CognitoResendVerificationRequest(BaseModel):
    """Cognito SMS認証コード再送信用モデル"""
    email: str


class AppUserData(BaseModel):
    """アプリケーションユーザーデータモデル"""
    app_user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cognito_sub: str
    subscription_status: str = "free"  # "free" or "premium"
    usage_count: int = 0
    monthly_usage_count: int = 0
    last_usage_reset: datetime = Field(default_factory=datetime.utcnow)
    preferences: dict = Field(default_factory=dict)
    profile_data: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserProfileUpdateRequest(BaseModel):
    """ユーザープロフィール更新用モデル"""
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None


class UserPreferencesUpdateRequest(BaseModel):
    """ユーザー設定更新用モデル"""
    language: Optional[str] = None
    theme: Optional[str] = None
    notifications: Optional[bool] = None


class AppUserDataCreate(BaseModel):
    """アプリケーションユーザーデータ作成用モデル"""
    cognito_sub: str
    preferences: Optional[dict] = None
    profile_data: Optional[dict] = None

class CheckoutSessionRequest(BaseModel):
    """Stripe決済セッション作成リクエスト"""
    price_id: Optional[str] = None # 特定の商品IDを指定する場合
    quantity: int = 1 # 30分単位の個数