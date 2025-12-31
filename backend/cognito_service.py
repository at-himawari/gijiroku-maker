"""
AWS Cognito メールアドレス + パスワード認証サービス
"""
import re
import boto3
import logging
import json
import aiomysql
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from database import db_manager
from models import UserCreate, SessionCreate, AuthLogCreate, CognitoRegisterRequest, CognitoLoginRequest, UserSession
from logging_service import logging_service
from cognito_token_service import cognito_token_service
from session_manager import session_manager
from rate_limiting_service import rate_limiting_service
from security_monitoring_service import security_monitoring_service

load_dotenv()

logger = logging.getLogger(__name__)

class CognitoService:
    """AWS Cognito メールアドレス + パスワード認証サービス"""
    
    def __init__(self):
        """CognitoService を初期化"""
        self.region = os.getenv('AWS_REGION', 'ap-northeast-1')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('COGNITO_CLIENT_ID')
        
        if not self.user_pool_id or not self.client_id:
            raise ValueError("Cognito 設定が不完全です。環境変数を確認してください。")
        
        # Cognito クライアントを初期化
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        
    def validate_email(self, email: str) -> bool:
        """
        メールアドレス形式を検証
        
        Args:
            email: 検証するメールアドレス
            
        Returns:
            bool: 有効な場合 True、無効な場合 False
        """
        if not email:
            return False
            
        # RFC 5322 準拠の基本的なメールアドレスパターン
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        return re.match(pattern, email) is not None
    
    def validate_password(self, password: str) -> Dict[str, Any]:
        """
        パスワード強度を検証
        
        Args:
            password: 検証するパスワード
            
        Returns:
            Dict: 検証結果
        """
        if not password:
            return {
                'valid': False,
                'message': 'パスワードは必須です。'
            }
        
        if len(password) < 8:
            return {
                'valid': False,
                'message': 'パスワードは8文字以上である必要があります。'
            }
        
        # 英数字と記号を含むかチェック
        has_letter = re.search(r'[a-zA-Z]', password)
        has_digit = re.search(r'\d', password)
        has_symbol = re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
        
        if not (has_letter and has_digit and has_symbol):
            return {
                'valid': False,
                'message': 'パスワードは英字、数字、記号をすべて含む必要があります。'
            }
        
        return {
            'valid': True,
            'message': 'パスワードは有効です。'
        }
    
    def validate_phone_number(self, phone_number: str) -> bool:
        """
        日本の電話番号形式を検証
        
        Args:
            phone_number: 検証する電話番号
            
        Returns:
            bool: 有効な場合 True、無効な場合 False
        """
        if not phone_number:
            return False
            
        # 日本の電話番号パターン（+81 または 0 で始まる）
        patterns = [
            r'^\+81[789]0\d{8}$',                    # +81 90/80/70 XXXXXXXX (携帯)
            r'^0[789]0\d{8}$',                       # 090/080/070 XXXXXXXX (携帯)
            r'^\+8150\d{8}$',                        # +81 50 XXXXXXXX (IP電話)
            r'^050\d{8}$',                           # 050 XXXXXXXX (IP電話)
            r'^\+81[1-6]\d{8}$',                     # +81 1-6XXXXXXXX (固定電話 10桁)
            r'^0[1-6]\d{8}$',                        # 01-06XXXXXXXX (固定電話 10桁)
            r'^\+81[1-9][1-9]\d{7}$',                # +81 XX-XXXX-XXXX (固定電話 11桁)
            r'^0[1-9][1-9]\d{7}$'                    # 0XX-XXXX-XXXX (固定電話 11桁)
        ]
        
        # ハイフンやスペースを除去
        clean_number = re.sub(r'[-\s]', '', phone_number)
        
        for pattern in patterns:
            if re.match(pattern, clean_number):
                return True
                
        return False
    
    def normalize_phone_number(self, phone_number: str) -> str:
        """
        電話番号を国際形式に正規化
        
        Args:
            phone_number: 正規化する電話番号
            
        Returns:
            str: 国際形式の電話番号 (+81XXXXXXXXX)
        """
        # ハイフンやスペースを除去
        clean_number = re.sub(r'[-\s]', '', phone_number)
        
        # 既に+81で始まっている場合はそのまま返す
        if clean_number.startswith('+81'):
            return clean_number
            
        # 0で始まる場合は+81に変換
        if clean_number.startswith('0'):
            return '+81' + clean_number[1:]
            
        # その他の場合はそのまま返す（エラーハンドリングは呼び出し元で）
        return clean_number
    
    def validate_registration_data(self, registration_data: CognitoRegisterRequest) -> Dict[str, Any]:
        """
        登録データの包括的な検証
        
        Args:
            registration_data: 登録データ
            
        Returns:
            Dict: 検証結果
        """
        errors = []
        
        # メールアドレス検証
        if not self.validate_email(registration_data.email):
            errors.append("有効なメールアドレスを入力してください")
        
        # パスワード検証
        password_result = self.validate_password(registration_data.password)
        if not password_result['valid']:
            errors.append(password_result['message'])
        
        # 電話番号検証
        if not self.validate_phone_number(registration_data.phone_number):
            errors.append("有効な電話番号を入力してください")
        
        # 名前検証
        if not registration_data.given_name or not registration_data.given_name.strip():
            errors.append("名前を入力してください")
        
        if not registration_data.family_name or not registration_data.family_name.strip():
            errors.append("姓を入力してください")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'message': '登録データは有効です' if len(errors) == 0 else f"入力エラー: {', '.join(errors)}"
        }
    
    async def check_email_exists(self, email: str) -> bool:
        """
        メールアドレスが既に登録されているかチェック
        
        Args:
            email: チェックするメールアドレス
            
        Returns:
            bool: 存在する場合 True
        """
        try:
            # Cognito でユーザーを検索
            response = self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=email
            )
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'UserNotFoundException':
                return False
            else:
                # その他のエラーの場合は存在すると仮定（安全側に倒す）
                logger.error(f"メールアドレス存在チェックエラー: {e}")
                return True
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return True
    
    async def check_phone_exists(self, phone_number: str) -> bool:
        """
        電話番号が既に登録されているかチェック
        
        Args:
            phone_number: チェックする電話番号
            
        Returns:
            bool: 存在する場合 True
        """
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # Cognito でカスタム属性 phone_number を検索
            response = self.cognito_client.list_users(
                UserPoolId=self.user_pool_id,
                Filter=f'phone_number = "{normalized_phone}"'
            )
            
            return len(response.get('Users', [])) > 0
            
        except Exception as e:
            logger.error(f"電話番号存在チェックエラー: {e}")
            return True  # 安全側に倒す
    
    async def register_user(self, register_data: CognitoRegisterRequest, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        新規ユーザーを登録（SMS認証付き）
        
        Args:
            register_data: 登録データ
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 登録結果（SMS認証が必要な場合はsms_verification_requiredフラグを含む）
        """
        try:
            # レート制限チェック（メールアドレスベース）
            rate_limit_result = await rate_limiting_service.check_cognito_rate_limit(
                register_data.email, "register", max_attempts=3, window_minutes=60
            )
            
            if not rate_limit_result['allowed']:
                return {
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': rate_limit_result['message'],
                    'reset_time': rate_limit_result['reset_time']
                }
            
            # IPアドレスベースのレート制限チェック
            if ip_address:
                ip_rate_result = await rate_limiting_service.check_ip_rate_limit(
                    ip_address, "cognito_register", max_requests=10, window_minutes=60
                )
                
                if not ip_rate_result['allowed']:
                    return {
                        'success': False,
                        'error': 'ip_rate_limit_exceeded',
                        'message': ip_rate_result['message'],
                        'reset_time': ip_rate_result['reset_time']
                    }
            
            # 包括的な入力検証
            validation_result = self.validate_registration_data(register_data)
            if not validation_result['valid']:
                await rate_limiting_service.record_cognito_attempt(
                    register_data.email, "register", success=False, ip_address=ip_address
                )
                await logging_service.log_cognito_user_registration(
                    register_data.email, "failure", 
                    {"error": "validation_failed", "validation_errors": validation_result['errors']}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'validation_failed',
                    'message': validation_result['message'],
                    'validation_errors': validation_result['errors']
                }
            
            # 重複チェック
            if await self.check_email_exists(register_data.email):
                await rate_limiting_service.record_cognito_attempt(
                    register_data.email, "register", success=False, ip_address=ip_address
                )
                await logging_service.log_cognito_user_registration(
                    register_data.email, "failure", 
                    {"error": "email_exists", "email": register_data.email}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'email_exists',
                    'message': 'このメールアドレスは既に登録されています。'
                }
            
            if await self.check_phone_exists(register_data.phone_number):
                await rate_limiting_service.record_cognito_attempt(
                    register_data.email, "register", success=False, ip_address=ip_address
                )
                await logging_service.log_cognito_user_registration(
                    register_data.email, "failure", 
                    {"error": "phone_exists", "phone_number": register_data.phone_number}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'phone_exists',
                    'message': 'この電話番号は既に登録されています。'
                }
            
            normalized_phone = self.normalize_phone_number(register_data.phone_number)
            
            # Cognito でユーザーを作成（電話番号未検証状態）
            response = self.cognito_client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=register_data.email,
                UserAttributes=[
                    {
                        'Name': 'email',
                        'Value': register_data.email
                    },
                    {
                        'Name': 'email_verified',
                        'Value': 'true'
                    },
                    {
                        'Name': 'phone_number',
                        'Value': normalized_phone
                    },
                    {
                        'Name': 'phone_number_verified',
                        'Value': 'false'  # 電話番号は未検証状態で作成
                    },
                    {
                        'Name': 'given_name',
                        'Value': register_data.given_name
                    },
                    {
                        'Name': 'family_name',
                        'Value': register_data.family_name
                    }
                ],
                TemporaryPassword=register_data.password,
                MessageAction='SUPPRESS'  # ウェルカムメッセージを送信しない
            )
            
            # パスワードを永続化（一時パスワードから変更）
            self.cognito_client.admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=register_data.email,
                Password=register_data.password,
                Permanent=True
            )
            
            # Cognito User Sub を取得
            cognito_user_sub = response['User']['Username']
            for attr in response['User']['Attributes']:
                if attr['Name'] == 'sub':
                    cognito_user_sub = attr['Value']
                    break
            
            # SMS認証コードを送信
            sms_result = await self.send_phone_verification_code(register_data.email, ip_address)
            
            if not sms_result['success']:
                # SMS送信に失敗した場合、作成したユーザーを削除
                try:
                    self.cognito_client.admin_delete_user(
                        UserPoolId=self.user_pool_id,
                        Username=register_data.email
                    )
                except Exception as cleanup_error:
                    logger.error(f"ユーザークリーンアップエラー: {cleanup_error}")
                
                await logging_service.log_cognito_user_registration(
                    register_data.email, "failure", 
                    {"error": "sms_send_failed", "sms_error": sms_result.get('message')}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'sms_send_failed',
                    'message': 'SMS認証コードの送信に失敗しました。しばらく待ってから再試行してください。'
                }
            
            # 成功した試行を記録
            await rate_limiting_service.record_cognito_attempt(
                register_data.email, "register", success=True, ip_address=ip_address
            )
            
            await logging_service.log_cognito_user_registration(
                register_data.email, "pending_verification", 
                {
                    "cognito_user_sub": cognito_user_sub,
                    "given_name": register_data.given_name,
                    "family_name": register_data.family_name,
                    "phone_number": normalized_phone,
                    "sms_sent": True
                }, 
                None, ip_address
            )
            
            logger.info(f"新規ユーザー登録開始（SMS認証待ち）: {register_data.email}")
            
            return {
                'success': True,
                'sms_verification_required': True,
                'email': register_data.email,
                'phone_number': normalized_phone,
                'message': 'SMS認証コードを送信しました。電話番号に届いたコードを入力してください。'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognito登録エラー: {error_code} - {e}")
            
            await logging_service.log_cognito_user_registration(
                register_data.email, "failure", 
                {"error": error_code, "cognito_error": True}, 
                None, ip_address
            )
            
            if error_code == 'UsernameExistsException':
                return {
                    'success': False,
                    'error': 'email_exists',
                    'message': 'このメールアドレスは既に登録されています。'
                }
            elif error_code == 'InvalidPasswordException':
                return {
                    'success': False,
                    'error': 'invalid_password',
                    'message': 'パスワードがポリシーに適合していません。8文字以上で英数字と記号を含む必要があります。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': '登録サービスでエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            await logging_service.log_cognito_user_registration(
                register_data.email, "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def send_phone_verification_code(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        電話番号認証用のSMSコードを送信
        
        Args:
            email: ユーザーのメールアドレス（Cognitoユーザー名）
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: SMS送信結果
        """
        try:
            # レート制限チェック（SMS送信）
            rate_limit_result = await rate_limiting_service.check_cognito_rate_limit(
                email, "sms_send", max_attempts=3, window_minutes=10
            )
            
            if not rate_limit_result['allowed']:
                return {
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': rate_limit_result['message'],
                    'reset_time': rate_limit_result['reset_time']
                }
            
            # ユーザーが存在するかチェック
            if not await self.check_email_exists(email):
                await logging_service.log_cognito_sms_verification(
                    email, "code_send_failed", "failure", 
                    {"error": "user_not_found"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            
            # Cognito でSMS認証を開始
            # まずMFA設定を有効化
            try:
                self.cognito_client.admin_set_user_mfa_preference(
                    UserPoolId=self.user_pool_id,
                    Username=email,
                    SMSMfaSettings={
                        'Enabled': True,
                        'PreferredMfa': True
                    }
                )
            except ClientError as mfa_error:
                logger.warning(f"MFA設定エラー（継続）: {mfa_error}")
            
            # 認証フローを開始してSMSチャレンジを発生させる
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': 'temp_password_for_sms_trigger'  # 一時的なパスワード
                }
            )
            
            # MFA チャレンジが必要な場合
            if response.get('ChallengeName') == 'SMS_MFA':
                session = response.get('Session')
                
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_send", success=True, ip_address=ip_address
                )
                
                await logging_service.log_cognito_sms_verification(
                    email, "code_sent", "success", 
                    {"session_id": session[:10] + "..." if session else None}, 
                    None, ip_address
                )
                
                logger.info(f"SMS認証コード送信成功: {email}")
                
                return {
                    'success': True,
                    'session': session,
                    'message': 'SMS認証コードを送信しました。電話番号に届いたコードを入力してください。'
                }
            else:
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_send", success=False, ip_address=ip_address
                )
                
                await logging_service.log_cognito_sms_verification(
                    email, "code_send_failed", "failure", 
                    {"error": "no_sms_challenge", "response": str(response)}, 
                    None, ip_address
                )
                
                return {
                    'success': False,
                    'error': 'sms_setup_failed',
                    'message': 'SMS認証の設定に失敗しました。管理者にお問い合わせください。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"SMS送信エラー: {error_code} - {e}")
            
            await rate_limiting_service.record_cognito_attempt(
                email, "sms_send", success=False, ip_address=ip_address
            )
            
            await logging_service.log_cognito_sms_verification(
                email, "code_send_failed", "failure", 
                {"error": error_code, "cognito_error": True}, 
                None, ip_address
            )
            
            if error_code == 'UserNotFoundException':
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            elif error_code == 'TooManyRequestsException':
                return {
                    'success': False,
                    'error': 'too_many_requests',
                    'message': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
                }
            elif error_code == 'NotAuthorizedException':
                return {
                    'success': False,
                    'error': 'not_authorized',
                    'message': '認証に失敗しました。ユーザーアカウントを確認してください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'sms_send_failed',
                    'message': 'SMS認証コードの送信に失敗しました。しばらく待ってから再試行してください。'
                }
            
        except Exception as e:
            logger.error(f"予期しないSMS送信エラー: {e}")
            await logging_service.log_cognito_sms_verification(
                email, "code_send_failed", "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def verify_phone_verification_code(self, email: str, verification_code: str, session: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        電話番号認証用のSMSコードを検証し、ユーザー登録を完了
        
        Args:
            email: ユーザーのメールアドレス
            verification_code: SMS認証コード
            session: Cognitoセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 検証結果
        """
        try:
            # レート制限チェック（SMS検証）
            rate_limit_result = await rate_limiting_service.check_cognito_rate_limit(
                email, "sms_verify", max_attempts=5, window_minutes=10
            )
            
            if not rate_limit_result['allowed']:
                return {
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': rate_limit_result['message'],
                    'reset_time': rate_limit_result['reset_time']
                }
            
            # 入力検証
            if not verification_code or not verification_code.strip():
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_verify", success=False, ip_address=ip_address
                )
                return {
                    'success': False,
                    'error': 'missing_verification_code',
                    'message': '認証コードを入力してください。'
                }
            
            if not session or not session.strip():
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_verify", success=False, ip_address=ip_address
                )
                return {
                    'success': False,
                    'error': 'missing_session',
                    'message': 'セッション情報が不正です。最初からやり直してください。'
                }
            
            # SMS認証コードを検証
            response = self.cognito_client.admin_respond_to_auth_challenge(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                ChallengeName='SMS_MFA',
                ChallengeResponses={
                    'SMS_MFA_CODE': verification_code.strip(),
                    'USERNAME': email
                },
                Session=session
            )
            
            if 'AuthenticationResult' in response:
                # 認証成功 - 電話番号を検証済みに設定
                try:
                    self.cognito_client.admin_update_user_attributes(
                        UserPoolId=self.user_pool_id,
                        Username=email,
                        UserAttributes=[
                            {
                                'Name': 'phone_number_verified',
                                'Value': 'true'
                            }
                        ]
                    )
                except ClientError as update_error:
                    logger.warning(f"電話番号検証済み設定エラー: {update_error}")
                
                # Cognito User Sub を取得
                id_token = response['AuthenticationResult'].get('IdToken')
                cognito_user_sub = None
                
                if id_token:
                    import jwt
                    decoded_token = jwt.decode(id_token, options={"verify_signature": False})
                    cognito_user_sub = decoded_token.get('sub')
                
                # ローカルデータベースにユーザーを作成（まだ存在しない場合）
                if cognito_user_sub:
                    # 既存ユーザーをチェック
                    existing_user = await db_manager.get_user_by_cognito_sub(cognito_user_sub)
                    
                    if not existing_user:
                        user_data = UserCreate(cognito_user_sub=cognito_user_sub)
                        user = await db_manager.create_user(user_data)
                        
                        if user:
                            # アプリケーションユーザーデータも作成
                            app_data = await db_manager.create_app_user_data(cognito_user_sub)
                            if app_data:
                                logger.info(f"アプリケーションユーザーデータも作成しました: {cognito_user_sub}")
                            
                            await rate_limiting_service.record_cognito_attempt(
                                email, "sms_verify", success=True, ip_address=ip_address
                            )
                            
                            await logging_service.log_cognito_user_registration(
                                email, "success", 
                                {
                                    "user_id": user.user_id, 
                                    "cognito_user_sub": cognito_user_sub,
                                    "phone_verified": True,
                                    "registration_completed": True
                                }, 
                                user.user_id, ip_address
                            )
                            
                            await logging_service.log_cognito_sms_verification(
                                email, "code_verified", "success", 
                                {"user_id": user.user_id, "registration_completed": True}, 
                                user.user_id, ip_address
                            )
                            
                            logger.info(f"SMS認証完了、ユーザー登録成功: {email} (User ID: {user.user_id})")
                            
                            return {
                                'success': True,
                                'user_id': user.user_id,
                                'cognito_user_sub': cognito_user_sub,
                                'registration_completed': True,
                                'message': 'ユーザー登録が完了しました。ログインしてください。'
                            }
                        else:
                            await logging_service.log_cognito_user_registration(
                                email, "failure", 
                                {"error": "db_user_creation_failed", "cognito_user_sub": cognito_user_sub}, 
                                None, ip_address
                            )
                            return {
                                'success': False,
                                'error': 'user_creation_failed',
                                'message': 'ユーザー作成に失敗しました。管理者にお問い合わせください。'
                            }
                    else:
                        # 既存ユーザーの場合（電話番号認証のみ）
                        await rate_limiting_service.record_cognito_attempt(
                            email, "sms_verify", success=True, ip_address=ip_address
                        )
                        
                        await logging_service.log_cognito_sms_verification(
                            email, "code_verified", "success", 
                            {"user_id": existing_user.user_id, "existing_user": True}, 
                            existing_user.user_id, ip_address
                        )
                        
                        logger.info(f"SMS認証完了（既存ユーザー）: {email} (User ID: {existing_user.user_id})")
                        
                        return {
                            'success': True,
                            'user_id': existing_user.user_id,
                            'cognito_user_sub': cognito_user_sub,
                            'phone_verified': True,
                            'message': '電話番号認証が完了しました。'
                        }
                else:
                    await logging_service.log_cognito_sms_verification(
                        email, "code_verified", "failure", 
                        {"error": "cognito_sub_not_found"}, 
                        None, ip_address
                    )
                    return {
                        'success': False,
                        'error': 'user_info_error',
                        'message': 'ユーザー情報の取得に失敗しました。管理者にお問い合わせください。'
                    }
            else:
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_verify", success=False, ip_address=ip_address
                )
                
                await logging_service.log_cognito_sms_verification(
                    email, "code_verification_failed", "failure", 
                    {"error": "no_authentication_result"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'verification_failed',
                    'message': 'SMS認証コードの検証に失敗しました。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"SMS認証コード検証エラー: {error_code} - {e}")
            
            await rate_limiting_service.record_cognito_attempt(
                email, "sms_verify", success=False, ip_address=ip_address
            )
            
            await logging_service.log_cognito_sms_verification(
                email, "code_verification_failed", "failure", 
                {"error": error_code, "cognito_error": True}, 
                None, ip_address
            )
            
            if error_code == 'CodeMismatchException':
                return {
                    'success': False,
                    'error': 'invalid_code',
                    'message': 'SMS認証コードが正しくありません。正しいコードを入力してください。'
                }
            elif error_code == 'ExpiredCodeException':
                return {
                    'success': False,
                    'error': 'expired_code',
                    'message': 'SMS認証コードの有効期限が切れています。再送信してください。'
                }
            elif error_code == 'NotAuthorizedException':
                return {
                    'success': False,
                    'error': 'invalid_session',
                    'message': 'セッションが無効です。最初からやり直してください。'
                }
            elif error_code == 'TooManyRequestsException':
                return {
                    'success': False,
                    'error': 'too_many_requests',
                    'message': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': 'SMS認証でエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないSMS検証エラー: {e}")
            await logging_service.log_cognito_sms_verification(
                email, "code_verification_failed", "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def resend_phone_verification_code(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        電話番号認証用のSMSコードを再送信
        
        Args:
            email: ユーザーのメールアドレス
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 再送信結果
        """
        try:
            # レート制限チェック（SMS再送信）
            rate_limit_result = await rate_limiting_service.check_cognito_rate_limit(
                email, "sms_resend", max_attempts=3, window_minutes=10
            )
            
            if not rate_limit_result['allowed']:
                return {
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': rate_limit_result['message'],
                    'reset_time': rate_limit_result['reset_time']
                }
            
            # SMS認証コードを再送信
            sms_result = await self.send_phone_verification_code(email, ip_address)
            
            if sms_result['success']:
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_resend", success=True, ip_address=ip_address
                )
            else:
                await rate_limiting_service.record_cognito_attempt(
                    email, "sms_resend", success=False, ip_address=ip_address
                )
            
            return sms_result
            
        except Exception as e:
            logger.error(f"SMS再送信エラー: {e}")
            await logging_service.log_cognito_sms_verification(
                email, "code_resend_failed", "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def get_phone_verification_status(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        電話番号認証状態を確認
        
        Args:
            email: ユーザーのメールアドレス
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 認証状態
        """
        try:
            # 入力検証
            if not self.validate_email(email):
                return {
                    'success': False,
                    'error': 'invalid_email_format',
                    'message': '有効なメールアドレスを入力してください。'
                }
            
            # Cognito でユーザー情報を取得
            response = self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=email
            )
            
            # 電話番号認証状態を確認
            phone_verified = False
            phone_number = None
            
            for attr in response.get('UserAttributes', []):
                if attr['Name'] == 'phone_number_verified':
                    phone_verified = attr['Value'].lower() == 'true'
                elif attr['Name'] == 'phone_number':
                    phone_number = attr['Value']
            
            user_status = response.get('UserStatus', 'UNKNOWN')
            enabled = response.get('Enabled', False)
            
            await logging_service.log_cognito_sms_verification(
                email, "status_check", "success", 
                {
                    "phone_verified": phone_verified,
                    "user_status": user_status,
                    "enabled": enabled
                }, 
                None, ip_address
            )
            
            return {
                'success': True,
                'email': email,
                'phone_number': phone_number,
                'phone_verified': phone_verified,
                'user_status': user_status,
                'enabled': enabled,
                'message': f'電話番号認証状態: {"認証済み" if phone_verified else "未認証"}'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"電話番号認証状態確認エラー: {error_code} - {e}")
            
            if error_code == 'UserNotFoundException':
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': '認証状態の確認でエラーが発生しました。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def login_user(self, login_data: CognitoLoginRequest, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        ユーザーログイン
        
        Args:
            login_data: ログインデータ
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: ログイン結果
        """
        try:
            # レート制限チェック（メールアドレスベース）
            rate_limit_result = await rate_limiting_service.check_cognito_rate_limit(
                login_data.email, "login", max_attempts=5, window_minutes=30
            )
            
            if not rate_limit_result['allowed']:
                return {
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': rate_limit_result['message'],
                    'reset_time': rate_limit_result['reset_time']
                }
            
            # IPアドレスベースのレート制限チェック
            if ip_address:
                ip_rate_result = await rate_limiting_service.check_ip_rate_limit(
                    ip_address, "cognito_login", max_requests=20, window_minutes=60
                )
                
                if not ip_rate_result['allowed']:
                    return {
                        'success': False,
                        'error': 'ip_rate_limit_exceeded',
                        'message': ip_rate_result['message'],
                        'reset_time': ip_rate_result['reset_time']
                    }
            
            # 入力検証
            if not self.validate_email(login_data.email):
                await rate_limiting_service.record_cognito_attempt(
                    login_data.email, "login", success=False, ip_address=ip_address
                )
                await logging_service.log_cognito_user_login(
                    login_data.email, "failure", 
                    {"error": "invalid_email_format", "email": login_data.email}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_email_format',
                    'message': '有効なメールアドレスを入力してください。'
                }
            
            if not login_data.password:
                await rate_limiting_service.record_cognito_attempt(
                    login_data.email, "login", success=False, ip_address=ip_address
                )
                await logging_service.log_cognito_user_login(
                    login_data.email, "failure", 
                    {"error": "missing_password"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'missing_password',
                    'message': 'パスワードは必須です。'
                }
            
            # Cognito で認証
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': login_data.email,
                    'PASSWORD': login_data.password
                }
            )
            
            # 認証成功
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                # Cognito User Sub を取得
                id_token = auth_result.get('IdToken')
                cognito_user_sub = None
                
                if id_token:
                    import jwt
                    # JWT トークンをデコード（検証なし、情報取得のみ）
                    decoded_token = jwt.decode(id_token, options={"verify_signature": False})
                    cognito_user_sub = decoded_token.get('sub')
                
                # ローカルデータベースでユーザーを取得
                user = await db_manager.get_user_by_cognito_sub(cognito_user_sub) if cognito_user_sub else None
                
                if not user:
                    await rate_limiting_service.record_cognito_attempt(
                        login_data.email, "login", success=False, ip_address=ip_address
                    )
                    await logging_service.log_cognito_user_login(
                        login_data.email, "failure", 
                        {"error": "user_not_found_in_db", "cognito_user_sub": cognito_user_sub}, 
                        None, ip_address
                    )
                    return {
                        'success': False,
                        'error': 'user_not_found',
                        'message': 'ユーザーが見つかりません。'
                    }
                
                # アプリケーションユーザーデータが存在しない場合は作成
                app_data = await db_manager.get_app_user_data_by_cognito_sub(cognito_user_sub)
                if not app_data:
                    app_data = await db_manager.create_app_user_data(cognito_user_sub)
                    if app_data:
                        logger.info(f"ログイン時にアプリケーションユーザーデータを作成しました: {cognito_user_sub}")
                
                # 成功した試行を記録
                await rate_limiting_service.record_cognito_attempt(
                    login_data.email, "login", success=True, ip_address=ip_address
                )
                
                # 成功したログインを記録（パターン検出用）
                await rate_limiting_service.record_successful_login(
                    login_data.email, ip_address
                )
                
                if ip_address:
                    await rate_limiting_service.record_ip_request(ip_address, "cognito_login")
                
                # セッションを作成
                session_data = SessionCreate(
                    user_id=user.user_id,
                    cognito_user_sub=cognito_user_sub,
                    access_token=auth_result.get('AccessToken'),
                    id_token=auth_result.get('IdToken'),
                    refresh_token=auth_result.get('RefreshToken'),
                    expires_in=auth_result.get('ExpiresIn', 3600),  # 1時間
                    client_ip=ip_address
                )
                
                # セッションマネージャーでセッションを永続化
                db_session = await session_manager.persist_session(session_data)
                if not db_session:
                    await logging_service.log_cognito_session_operation(
                        login_data.email, "created", "failure", 
                        {"error": "session_creation_failed", "user_id": user.user_id}, 
                        user.user_id, ip_address
                    )
                    return {
                        'success': False,
                        'error': 'session_creation_failed',
                        'message': 'セッション作成に失敗しました。'
                    }
                
                # ユーザーのログイン情報を更新
                await db_manager.update_user_login(user.user_id)
                
                await logging_service.log_cognito_user_login(
                    login_data.email, "success", 
                    {
                        "session_id": db_session.session_id, 
                        "user_id": user.user_id,
                        "cognito_user_sub": cognito_user_sub,
                        "expires_in": auth_result.get('ExpiresIn', 3600)
                    }, 
                    user.user_id, ip_address
                )
                
                # セッション作成ログも記録
                await logging_service.log_cognito_session_operation(
                    login_data.email, "created", "success", 
                    {
                        "session_id": db_session.session_id,
                        "expires_in": auth_result.get('ExpiresIn', 3600),
                        "user_id": user.user_id
                    }, 
                    user.user_id, ip_address
                )
                
                logger.info(f"ログイン成功: {login_data.email} (User ID: {user.user_id})")
                
                return {
                    'success': True,
                    'access_token': auth_result.get('AccessToken'),
                    'refresh_token': auth_result.get('RefreshToken'),
                    'id_token': auth_result.get('IdToken'),
                    'expires_in': auth_result.get('ExpiresIn', 3600),
                    'session_id': db_session.session_id,
                    'user_id': user.user_id,
                    'message': 'ログインが完了しました。'
                }
            else:
                await logging_service.log_cognito_authentication_failure(
                    login_data.email, "authentication_failed", 
                    {"error": "no_authentication_result", "cognito_response": "missing_auth_result"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'authentication_failed',
                    'message': 'メールアドレスまたはパスワードが間違っています。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognitoログインエラー: {error_code} - {e}")
            
            await logging_service.log_cognito_authentication_failure(
                login_data.email, error_code, 
                {"cognito_error": True, "error_message": str(e)}, 
                None, ip_address
            )
            
            # セキュリティ監視: 認証失敗を監視
            await security_monitoring_service.monitor_cognito_authentication_failure(
                login_data.email, error_code,
                {"cognito_error": True, "error_message": str(e)},
                None, ip_address
            )
            
            if error_code == 'NotAuthorizedException':
                return {
                    'success': False,
                    'error': 'invalid_credentials',
                    'message': 'メールアドレスまたはパスワードが間違っています。'
                }
            elif error_code == 'UserNotFoundException':
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'メールアドレスまたはパスワードが間違っています。'
                }
            elif error_code == 'TooManyRequestsException':
                return {
                    'success': False,
                    'error': 'too_many_requests',
                    'message': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
                }
            elif error_code == 'UserNotConfirmedException':
                return {
                    'success': False,
                    'error': 'user_not_confirmed',
                    'message': 'アカウントが確認されていません。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': '認証サービスでエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            await logging_service.log_cognito_user_login(
                login_data.email, "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }

    
    async def refresh_token(self, refresh_token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        リフレッシュトークンを使用してアクセストークンを更新し、セッションを同期
        
        Args:
            refresh_token: リフレッシュトークン
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: トークン更新結果
        """
        try:
            # Cognitoトークンサービスでトークンをリフレッシュ
            refresh_result = await cognito_token_service.refresh_tokens(refresh_token, ip_address)
            
            if not refresh_result['success']:
                return refresh_result
            
            # 新しいトークンを取得
            new_access_token = refresh_result['access_token']
            new_id_token = refresh_result.get('id_token')
            new_refresh_token = refresh_result.get('refresh_token', refresh_token)
            expires_in = refresh_result.get('expires_in', 3600)
            
            # 既存のセッションを検索（リフレッシュトークンで）
            session = await self._find_session_by_refresh_token(refresh_token)
            
            if session:
                # セッションのトークンを更新
                update_result = await cognito_token_service.update_session_tokens(
                    session.session_id,
                    new_access_token,
                    new_id_token,
                    new_refresh_token,
                    expires_in
                )
                
                if update_result['success']:
                    logger.info(f"セッショントークンを更新しました: {session.session_id}")
                else:
                    logger.warning(f"セッショントークン更新に失敗: {update_result.get('message')}")
            
            return {
                'success': True,
                'access_token': new_access_token,
                'id_token': new_id_token,
                'refresh_token': new_refresh_token,
                'expires_in': expires_in,
                'message': 'トークンを更新しました。'
            }
            
        except Exception as e:
            logger.error(f"トークンリフレッシュエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def _find_session_by_refresh_token(self, refresh_token: str) -> Optional[UserSession]:
        """
        リフレッシュトークンでセッションを検索
        
        Args:
            refresh_token: リフレッシュトークン
            
        Returns:
            Optional[UserSession]: セッション
        """
        try:
            import hashlib
            
            refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("""
                        SELECT * FROM user_sessions 
                        WHERE refresh_token_hash = %s AND is_active = TRUE
                    """, (refresh_token_hash,))
                    
                    row = await cursor.fetchone()
                    if row:
                        # トークンを復元（実際のトークンは保存していないので、引数のトークンを使用）
                        session_dict = dict(row)
                        session_dict['refresh_token'] = refresh_token
                        return UserSession(**session_dict)
                    return None
                    
        except Exception as e:
            logger.error(f"リフレッシュトークンセッション検索エラー: {e}")
            return None
    
    async def logout(self, access_token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        ログアウト処理
        
        Args:
            access_token: アクセストークン
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: ログアウト結果
        """
        try:
            # セッションを取得
            session = await db_manager.get_session_by_token(access_token)
            if session:
                # Cognito でグローバルサインアウト
                try:
                    self.cognito_client.global_sign_out(
                        AccessToken=access_token
                    )
                except ClientError as e:
                    # トークンが既に無効な場合でもローカルセッションは無効化する
                    logger.warning(f"Cognitoグローバルサインアウトエラー: {e}")
                
                # セッションマネージャーでセッションを無効化
                await session_manager.invalidate_session(session.session_id, "user_logout", ip_address)
                
                # ユーザー情報を取得してログに記録
                user = await db_manager.get_user_by_id(session.user_id)
                if user:
                    await logging_service.log_cognito_user_logout(
                        "cognito_user", "success", 
                        {"session_id": session.session_id, "user_id": user.user_id}, 
                        user.user_id, ip_address
                    )
                    
                    # セッション無効化ログも記録
                    await logging_service.log_cognito_session_operation(
                        "cognito_user", "invalidated", "success", 
                        {"session_id": session.session_id, "reason": "user_logout"}, 
                        user.user_id, ip_address
                    )
                
                logger.info(f"ログアウト成功: セッション {session.session_id}")
            
            return {
                'success': True,
                'message': 'ログアウトしました。'
            }
            
        except Exception as e:
            logger.error(f"ログアウトエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'ログアウト処理でエラーが発生しました。'
            }
    
    async def verify_session(self, access_token: str) -> Dict[str, Any]:
        """
        セッションを検証（Cognitoトークンサービス使用）
        
        Args:
            access_token: アクセストークン
            
        Returns:
            Dict: 検証結果
        """
        try:
            # Cognitoトークンサービスで検証・同期
            validation_result = await cognito_token_service.validate_and_sync_session(access_token)
            
            if not validation_result['success']:
                return validation_result
            
            user = validation_result['user']
            session = validation_result['session']
            
            return {
                'success': True,
                'user_id': user.user_id,
                'cognito_user_sub': user.cognito_user_sub,
                'session_id': session.session_id,
                'message': 'セッションが有効です。'
            }
            
        except Exception as e:
            logger.error(f"セッション検証エラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def request_password_reset(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Cognito パスワードリセット要求処理
        
        Args:
            email: パスワードリセットを要求するメールアドレス
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: パスワードリセット要求結果
        """
        try:
            # 入力検証
            if not self.validate_email(email):
                await logging_service.log_cognito_password_reset(
                    email, "request", "failure", 
                    {"error": "invalid_email_format", "email": email}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_email_format',
                    'message': '有効なメールアドレスを入力してください。'
                }
            
            # セキュリティ考慮: 存在しないメールでも成功メッセージを返す
            # ただし、実際のリセットコードは送信されない
            user_exists = await self.check_email_exists(email)
            
            if user_exists:
                try:
                    # Cognito でパスワードリセットを開始
                    response = self.cognito_client.forgot_password(
                        ClientId=self.client_id,
                        Username=email
                    )
                    
                    # 成功ログを記録
                    await logging_service.log_cognito_password_reset(
                        email, "request", "success", 
                        {
                            "delivery_medium": response.get('CodeDeliveryDetails', {}).get('DeliveryMedium', 'EMAIL'),
                            "destination": response.get('CodeDeliveryDetails', {}).get('Destination', 'masked'),
                            "user_exists": True
                        }, 
                        None, ip_address
                    )
                    
                    logger.info(f"パスワードリセット要求成功: {email}")
                    
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    logger.error(f"Cognitoパスワードリセット要求エラー: {error_code} - {e}")
                    
                    await logging_service.log_cognito_password_reset(
                        email, "request", "failure", 
                        {"error": error_code, "cognito_error": True}, 
                        None, ip_address
                    )
                    
                    if error_code == 'UserNotFoundException':
                        # ユーザーが見つからない場合でも成功メッセージを返す（セキュリティ考慮）
                        pass
                    elif error_code == 'TooManyRequestsException':
                        return {
                            'success': False,
                            'error': 'too_many_requests',
                            'message': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
                        }
                    elif error_code == 'LimitExceededException':
                        return {
                            'success': False,
                            'error': 'rate_limit_exceeded',
                            'message': 'パスワードリセット要求の制限に達しました。しばらく待ってから再試行してください。'
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'cognito_error',
                            'message': 'パスワードリセット要求でエラーが発生しました。しばらく待ってから再試行してください。'
                        }
            else:
                # ユーザーが存在しない場合のログ記録
                await logging_service.log_cognito_password_reset(
                    email, "request", "info", 
                    {"user_exists": False, "security_response": True}, 
                    None, ip_address
                )
                
                logger.info(f"存在しないメールアドレスでのパスワードリセット要求: {email}")
            
            # セキュリティ上、存在しないメールアドレスでも成功メッセージを返す
            return {
                'success': True,
                'message': 'パスワードリセット用のコードをメールアドレスに送信しました。メールをご確認ください。'
            }
            
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            await logging_service.log_cognito_password_reset(
                email, "request", "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def confirm_password_reset(self, email: str, confirmation_code: str, new_password: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Cognito パスワードリセット実行処理
        
        Args:
            email: メールアドレス
            confirmation_code: Cognitoから送信されたリセットコード
            new_password: 新しいパスワード
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: パスワードリセット実行結果
        """
        try:
            # 入力検証
            if not self.validate_email(email):
                await logging_service.log_cognito_password_reset(
                    email, "confirm", "failure", 
                    {"error": "invalid_email_format", "email": email}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_email_format',
                    'message': '有効なメールアドレスを入力してください。'
                }
            
            if not confirmation_code:
                await logging_service.log_cognito_password_reset(
                    email, "confirm", "failure", 
                    {"error": "missing_confirmation_code"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'missing_confirmation_code',
                    'message': '確認コードは必須です。'
                }
            
            # パスワード強度検証
            password_validation = self.validate_password(new_password)
            if not password_validation['valid']:
                await logging_service.log_cognito_password_reset(
                    email, "confirm", "failure", 
                    {"error": "invalid_password", "validation_message": password_validation['message']}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_password',
                    'message': password_validation['message']
                }
            
            # Cognito でパスワードリセットを確認・実行
            response = self.cognito_client.confirm_forgot_password(
                ClientId=self.client_id,
                Username=email,
                ConfirmationCode=confirmation_code,
                Password=new_password
            )
            
            # ユーザー情報を取得してログに記録
            user = await db_manager.get_user_by_email(email)
            user_id = user.user_id if user else None
            
            # パスワード変更成功ログを記録
            await logging_service.log_cognito_password_reset(
                email, "confirm", "success", 
                {
                    "user_id": user_id,
                    "password_changed": True,
                    "sessions_invalidated": invalidated_count if user else 0
                }, 
                user_id, ip_address
            )
            
            # 既存のセッションを無効化（セキュリティ強化）
            if user:
                invalidated_count = await session_manager.invalidate_user_sessions(
                    user.user_id, "password_reset", ip_address
                )
                logger.info(f"パスワード変更により{invalidated_count}件のセッションを無効化: {email}")
            
            logger.info(f"パスワードリセット完了: {email}")
            
            return {
                'success': True,
                'message': 'パスワードが正常に変更されました。新しいパスワードでログインしてください。'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognitoパスワードリセット確認エラー: {error_code} - {e}")
            
            await logging_service.log_cognito_password_reset(
                email, "confirm", "failure", 
                {"error": error_code, "cognito_error": True}, 
                None, ip_address
            )
            
            if error_code == 'CodeMismatchException':
                return {
                    'success': False,
                    'error': 'invalid_confirmation_code',
                    'message': '確認コードが正しくありません。'
                }
            elif error_code == 'ExpiredCodeException':
                return {
                    'success': False,
                    'error': 'expired_confirmation_code',
                    'message': '確認コードの有効期限が切れています。新しいリセット要求を行ってください。'
                }
            elif error_code == 'InvalidPasswordException':
                return {
                    'success': False,
                    'error': 'invalid_password',
                    'message': 'パスワードがポリシーに適合していません。'
                }
            elif error_code == 'UserNotFoundException':
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            elif error_code == 'TooManyRequestsException':
                return {
                    'success': False,
                    'error': 'too_many_requests',
                    'message': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': 'パスワードリセット処理でエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            await logging_service.log_cognito_password_reset(
                email, "confirm", "error", 
                {"error": str(e), "unexpected_error": True}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }

    async def get_user_profile(self, cognito_user_sub: str) -> Optional[Dict[str, Any]]:
        """
        Cognitoからユーザープロフィール情報を取得
        
        Args:
            cognito_user_sub: Cognito User Sub
            
        Returns:
            Optional[Dict]: ユーザープロフィール情報
        """
        try:
            # Cognito User Subからユーザー名（メールアドレス）を取得
            # まず、User Subでユーザーを検索
            response = self.cognito_client.list_users(
                UserPoolId=self.user_pool_id,
                Filter=f'sub = "{cognito_user_sub}"',
                Limit=1
            )
            
            if not response.get('Users'):
                logger.warning(f"Cognitoユーザーが見つかりません: {cognito_user_sub}")
                return None
            
            user_data = response['Users'][0]
            
            # ユーザー属性を辞書に変換
            profile = {}
            for attr in user_data.get('UserAttributes', []):
                attr_name = attr['Name']
                attr_value = attr['Value']
                
                # 属性名を正規化
                if attr_name == 'sub':
                    profile['cognito_sub'] = attr_value
                elif attr_name == 'email':
                    profile['email'] = attr_value
                elif attr_name == 'email_verified':
                    profile['email_verified'] = attr_value.lower() == 'true'
                elif attr_name == 'phone_number':
                    profile['phone_number'] = attr_value
                elif attr_name == 'phone_number_verified':
                    profile['phone_number_verified'] = attr_value.lower() == 'true'
                elif attr_name == 'given_name':
                    profile['given_name'] = attr_value
                elif attr_name == 'family_name':
                    profile['family_name'] = attr_value
                elif attr_name == 'name':
                    profile['name'] = attr_value
            
            # 名前を結合（given_name + family_nameがある場合）
            if 'given_name' in profile and 'family_name' in profile:
                profile['name'] = f"{profile['family_name']} {profile['given_name']}"
            
            # ユーザーステータス情報を追加
            profile['user_status'] = user_data.get('UserStatus', 'UNKNOWN')
            profile['enabled'] = user_data.get('Enabled', False)
            profile['user_create_date'] = user_data.get('UserCreateDate')
            profile['user_last_modified_date'] = user_data.get('UserLastModifiedDate')
            
            logger.info(f"Cognitoプロフィール取得成功: {cognito_user_sub}")
            return profile
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognitoプロフィール取得エラー: {error_code} - {e}")
            return None
            
        except Exception as e:
            logger.error(f"予期しないプロフィール取得エラー: {e}")
            return None
