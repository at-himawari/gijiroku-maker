"""
AWS Cognito を使用した電話番号認証サービス
"""
import re
import boto3
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from database import db_manager
from models import UserCreate, SessionCreate, AuthLogCreate
from logging_service import logging_service

load_dotenv()

logger = logging.getLogger(__name__)

class AuthService:
    """AWS Cognito を使用した電話番号認証サービス"""
    
    def __init__(self):
        """AuthService を初期化"""
        self.region = os.getenv('AWS_REGION', 'ap-northeast-1')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('COGNITO_CLIENT_ID')
        
        if not self.user_pool_id or not self.client_id:
            raise ValueError("Cognito 設定が不完全です。環境変数を確認してください。")
        
        # Cognito クライアントを初期化
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        
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
        # 携帯電話: 090, 080, 070 で始まる11桁
        # IP電話: 050 で始まる11桁
        # 固定電話: 市外局番で始まる10-11桁
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
    
    async def initiate_phone_auth(self, phone_number: str) -> Dict[str, Any]:
        """
        電話番号認証を開始し、SMS認証コードを送信
        
        Args:
            phone_number: 認証する電話番号
            
        Returns:
            Dict: 認証開始結果
        """
        try:
            # 電話番号形式を検証
            if not self.validate_phone_number(phone_number):
                return {
                    'success': False,
                    'error': 'invalid_phone_format',
                    'message': '有効な日本の電話番号を入力してください。例: 090-1234-5678'
                }
            
            # 電話番号を正規化
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # Cognito でSMS認証を開始
            response = self.cognito_client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='CUSTOM_AUTH',
                AuthParameters={
                    'USERNAME': normalized_phone,
                    'CHALLENGE_NAME': 'SMS_MFA'
                }
            )
            
            logger.info(f"SMS認証コードを送信しました: {normalized_phone}")
            
            return {
                'success': True,
                'session': response.get('Session'),
                'challenge_name': response.get('ChallengeName'),
                'message': 'SMS認証コードを送信しました。5分以内に入力してください。'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognito認証エラー: {error_code} - {e}")
            
            if error_code == 'UserNotFoundException':
                # 新規ユーザーの場合は登録フローに誘導
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'この電話番号は登録されていません。新規登録を行ってください。',
                    'redirect_to_signup': True
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
                    'message': '認証サービスでエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def verify_sms_code(self, phone_number: str, code: str, session: str) -> Dict[str, Any]:
        """
        SMS認証コードを検証し、アカウントを作成またはサインイン
        
        Args:
            phone_number: 認証する電話番号
            code: SMS認証コード
            session: Cognitoセッション
            
        Returns:
            Dict: 認証結果
        """
        try:
            # 電話番号を正規化
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # Cognito でSMS認証コードを検証
            response = self.cognito_client.respond_to_auth_challenge(
                ClientId=self.client_id,
                ChallengeName='SMS_MFA',
                Session=session,
                ChallengeResponses={
                    'SMS_MFA_CODE': code,
                    'USERNAME': normalized_phone
                }
            )
            
            # 認証成功
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                logger.info(f"SMS認証成功: {normalized_phone}")
                
                return {
                    'success': True,
                    'access_token': auth_result.get('AccessToken'),
                    'refresh_token': auth_result.get('RefreshToken'),
                    'id_token': auth_result.get('IdToken'),
                    'expires_in': auth_result.get('ExpiresIn', 3600),
                    'message': '認証が完了しました。'
                }
            else:
                return {
                    'success': False,
                    'error': 'verification_failed',
                    'message': '認証コードの検証に失敗しました。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"SMS認証エラー: {error_code} - {e}")
            
            if error_code == 'CodeMismatchException':
                return {
                    'success': False,
                    'error': 'invalid_code',
                    'message': '認証コードが正しくありません。再度入力してください。'
                }
            elif error_code == 'ExpiredCodeException':
                return {
                    'success': False,
                    'error': 'expired_code',
                    'message': '認証コードの有効期限が切れています。新しいコードを要求してください。'
                }
            elif error_code == 'TooManyFailedAttemptsException':
                return {
                    'success': False,
                    'error': 'account_locked',
                    'message': '認証の試行回数が上限に達しました。15分後に再試行してください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': '認証サービスでエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def create_user_account(self, phone_number: str) -> Dict[str, Any]:
        """
        新しいユーザーアカウントを作成
        
        Args:
            phone_number: 登録する電話番号
            
        Returns:
            Dict: アカウント作成結果
        """
        try:
            # 電話番号を正規化
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # Cognito でユーザーを作成
            response = self.cognito_client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=normalized_phone,
                UserAttributes=[
                    {
                        'Name': 'phone_number',
                        'Value': normalized_phone
                    },
                    {
                        'Name': 'phone_number_verified',
                        'Value': 'true'
                    }
                ],
                MessageAction='SUPPRESS',  # ウェルカムメッセージを送信しない
                TemporaryPassword=None
            )
            
            logger.info(f"ユーザーアカウント作成成功: {normalized_phone}")
            
            return {
                'success': True,
                'user_id': response['User']['Username'],
                'message': 'アカウントが正常に作成されました。'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"アカウント作成エラー: {error_code} - {e}")
            
            if error_code == 'UsernameExistsException':
                return {
                    'success': False,
                    'error': 'user_exists',
                    'message': 'この電話番号は既に登録されています。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': 'アカウント作成でエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def check_user_exists(self, phone_number: str) -> bool:
        """
        ユーザーが既に存在するかチェック（データベースとCognitoの両方）
        
        Args:
            phone_number: チェックする電話番号
            
        Returns:
            bool: ユーザーが存在する場合 True
        """
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # まずデータベースをチェック
            db_user = await db_manager.get_user_by_phone(normalized_phone)
            if db_user:
                return True
            
            # Cognitoもチェック
            self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=normalized_phone
            )
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'UserNotFoundException':
                return False
            else:
                # その他のエラーの場合は存在すると仮定（安全側に倒す）
                logger.error(f"ユーザー存在チェックエラー: {e}")
                return True
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return True
    
    async def initiate_signin(self, phone_number: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        既存ユーザーのサインインを開始
        
        Args:
            phone_number: サインインする電話番号
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: サインイン開始結果
        """
        try:
            # 電話番号形式を検証
            if not self.validate_phone_number(phone_number):
                await logging_service.log_auth_attempt(
                    phone_number, "failure", 
                    {"attempt_type": "signin_attempt", "error": "invalid_phone_format"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_phone_format',
                    'message': '有効な日本の電話番号を入力してください。例: 090-1234-5678'
                }
            
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # データベースでユーザーを確認
            user = await db_manager.get_user_by_phone(normalized_phone)
            if not user:
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signin_attempt", "error": "user_not_found"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'この電話番号は登録されていません。新規登録を行ってください。',
                    'redirect_to_signup': True
                }
            
            # アカウントロック状態をチェック
            if await db_manager.is_user_locked(user.user_id):
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signin_attempt", "error": "account_locked"}, 
                    user.user_id, ip_address
                )
                await logging_service.log_security_error(
                    normalized_phone, "account_locked", 
                    {"reason": "too_many_failed_attempts", "locked_until": "15_minutes"}, 
                    user.user_id, ip_address
                )
                return {
                    'success': False,
                    'error': 'account_locked',
                    'message': 'アカウントが一時的にロックされています。15分後に再試行してください。'
                }
            
            # SMS認証を開始
            result = await self.initiate_phone_auth(phone_number)
            
            if result['success']:
                await logging_service.log_sms_sent(
                    normalized_phone, "success", 
                    {"session": result.get('session'), "sent_at": datetime.utcnow().isoformat()}, 
                    user.user_id, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "success", 
                    {"attempt_type": "signin_sms_sent", "session": result.get('session')}, 
                    user.user_id, ip_address
                )
            else:
                await logging_service.log_sms_sent(
                    normalized_phone, "failure", 
                    {"error": result.get('error'), "attempted_at": datetime.utcnow().isoformat()}, 
                    user.user_id, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signin_sms_failed", "error": result.get('error')}, 
                    user.user_id, ip_address
                )
            
            return result
            
        except Exception as e:
            logger.error(f"サインイン開始エラー: {e}")
            await logging_service.log_auth_attempt(
                phone_number, "error", 
                {"attempt_type": "signin_attempt", "error": str(e)}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def verify_signin_code(self, phone_number: str, code: str, session: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        サインイン用SMS認証コードを検証し、セッションを作成
        
        Args:
            phone_number: 認証する電話番号
            code: SMS認証コード
            session: Cognitoセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 認証結果
        """
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            user = await db_manager.get_user_by_phone(normalized_phone)
            
            if not user:
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signin_verification", "error": "user_not_found"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            
            # Cognito でSMS認証コードを検証
            response = self.cognito_client.respond_to_auth_challenge(
                ClientId=self.client_id,
                ChallengeName='SMS_MFA',
                Session=session,
                ChallengeResponses={
                    'SMS_MFA_CODE': code,
                    'USERNAME': normalized_phone
                }
            )
            
            # 認証成功
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                # データベースでセッションを作成
                session_data = SessionCreate(
                    user_id=user.user_id,
                    access_token=auth_result.get('AccessToken'),
                    refresh_token=auth_result.get('RefreshToken'),
                    expires_in=auth_result.get('ExpiresIn', 86400)  # 24時間
                )
                
                db_session = await db_manager.create_session(session_data)
                if not db_session:
                    await logging_service.log_session_operation(
                        normalized_phone, "created", "failure", 
                        {"error": "session_creation_failed"}, 
                        user.user_id, ip_address
                    )
                    return {
                        'success': False,
                        'error': 'session_creation_failed',
                        'message': 'セッション作成に失敗しました。'
                    }
                
                # ユーザーのログイン情報を更新
                await db_manager.update_user_login(user.user_id)
                
                await logging_service.log_auth_attempt(
                    normalized_phone, "success", 
                    {"attempt_type": "signin_success", "session_id": db_session.session_id}, 
                    user.user_id, ip_address
                )
                await logging_service.log_session_operation(
                    normalized_phone, "created", "success", 
                    {"session_id": db_session.session_id, "expires_at": db_session.expires_at.isoformat()}, 
                    user.user_id, ip_address
                )
                
                logger.info(f"サインイン成功: {normalized_phone}")
                
                return {
                    'success': True,
                    'access_token': auth_result.get('AccessToken'),
                    'refresh_token': auth_result.get('RefreshToken'),
                    'id_token': auth_result.get('IdToken'),
                    'expires_in': auth_result.get('ExpiresIn', 86400),
                    'session_id': db_session.session_id,
                    'user_id': user.user_id,
                    'message': 'サインインが完了しました。'
                }
            else:
                # 認証失敗時の処理
                await db_manager.increment_failed_attempts(user.user_id)
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signin_verification", "error": "verification_failed"}, 
                    user.user_id, ip_address
                )
                return {
                    'success': False,
                    'error': 'verification_failed',
                    'message': '認証コードの検証に失敗しました。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"サインイン認証エラー: {error_code} - {e}")
            
            if user:
                await db_manager.increment_failed_attempts(user.user_id)
            
            await logging_service.log_auth_attempt(
                normalized_phone, "failure", 
                {"attempt_type": "signin_verification", "error": error_code}, 
                user.user_id if user else None, ip_address
            )
            
            if error_code == 'CodeMismatchException':
                return {
                    'success': False,
                    'error': 'invalid_code',
                    'message': '認証コードが正しくありません。再度入力してください。'
                }
            elif error_code == 'ExpiredCodeException':
                return {
                    'success': False,
                    'error': 'expired_code',
                    'message': '認証コードの有効期限が切れています。新しいコードを要求してください。'
                }
            elif error_code == 'TooManyFailedAttemptsException':
                return {
                    'success': False,
                    'error': 'account_locked',
                    'message': '認証の試行回数が上限に達しました。15分後に再試行してください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': '認証サービスでエラーが発生しました。しばらく待ってから再試行してください。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            if user:
                await logging_service.log_auth_attempt(
                    normalized_phone, "error", 
                    {"attempt_type": "signin_verification", "error": str(e)}, 
                    user.user_id, ip_address
                )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def initiate_signup(self, phone_number: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        新規ユーザーの登録を開始
        
        Args:
            phone_number: 登録する電話番号
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 登録開始結果
        """
        try:
            # 電話番号形式を検証
            if not self.validate_phone_number(phone_number):
                await logging_service.log_auth_attempt(
                    phone_number, "failure", 
                    {"attempt_type": "signup_attempt", "error": "invalid_phone_format"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_phone_format',
                    'message': '有効な日本の電話番号を入力してください。例: 090-1234-5678'
                }
            
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # 重複チェック
            if await self.check_user_exists(normalized_phone):
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_attempt", "error": "user_exists"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_exists',
                    'message': 'この電話番号は既に登録されています。サインインを行ってください。'
                }
            
            # SMS認証を開始
            result = await self.initiate_phone_auth(phone_number)
            
            if result['success']:
                await logging_service.log_sms_sent(
                    normalized_phone, "success", 
                    {"session": result.get('session'), "sent_at": datetime.utcnow().isoformat()}, 
                    None, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "success", 
                    {"attempt_type": "signup_sms_sent", "session": result.get('session')}, 
                    None, ip_address
                )
            else:
                await logging_service.log_sms_sent(
                    normalized_phone, "failure", 
                    {"error": result.get('error'), "attempted_at": datetime.utcnow().isoformat()}, 
                    None, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_sms_failed", "error": result.get('error')}, 
                    None, ip_address
                )
            
            return result
            
        except Exception as e:
            logger.error(f"登録開始エラー: {e}")
            await logging_service.log_auth_attempt(
                phone_number, "error", 
                {"attempt_type": "signup_attempt", "error": str(e)}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def verify_signup_code(self, phone_number: str, code: str, session: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        登録用SMS認証コードを検証し、アカウントとセッションを作成
        
        Args:
            phone_number: 認証する電話番号
            code: SMS認証コード
            session: Cognitoセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 認証結果
        """
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # 重複チェック（再度確認）
            if await self.check_user_exists(normalized_phone):
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_verification", "error": "user_exists"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_exists',
                    'message': 'この電話番号は既に登録されています。'
                }
            
            # Cognitoでアカウントを作成
            cognito_result = await self.create_user_account(normalized_phone)
            if not cognito_result['success']:
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_verification", "error": cognito_result.get('error')}, 
                    None, ip_address
                )
                return cognito_result
            
            # データベースでユーザーを作成
            user_data = UserCreate(phone_number=normalized_phone)
            user = await db_manager.create_user(user_data)
            if not user:
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_verification", "error": "db_user_creation_failed"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'user_creation_failed',
                    'message': 'ユーザー作成に失敗しました。'
                }
            
            # SMS認証コードを検証してトークンを取得
            auth_result = await self.verify_sms_code(normalized_phone, code, session)
            if not auth_result['success']:
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "signup_verification", "error": auth_result.get('error')}, 
                    user.user_id, ip_address
                )
                return auth_result
            
            # セッションを作成
            session_data = SessionCreate(
                user_id=user.user_id,
                access_token=auth_result.get('access_token'),
                refresh_token=auth_result.get('refresh_token'),
                expires_in=auth_result.get('expires_in', 86400)
            )
            
            db_session = await db_manager.create_session(session_data)
            if not db_session:
                await logging_service.log_session_operation(
                    normalized_phone, "created", "failure", 
                    {"error": "session_creation_failed"}, 
                    user.user_id, ip_address
                )
                return {
                    'success': False,
                    'error': 'session_creation_failed',
                    'message': 'セッション作成に失敗しました。'
                }
            
            # ユーザーのログイン情報を更新
            await db_manager.update_user_login(user.user_id)
            
            await logging_service.log_auth_attempt(
                normalized_phone, "success", 
                {"attempt_type": "signup_success", "session_id": db_session.session_id}, 
                user.user_id, ip_address
            )
            await logging_service.log_session_operation(
                normalized_phone, "created", "success", 
                {"session_id": db_session.session_id, "expires_at": db_session.expires_at.isoformat()}, 
                user.user_id, ip_address
            )
            
            logger.info(f"新規登録成功: {normalized_phone}")
            
            return {
                'success': True,
                'access_token': auth_result.get('access_token'),
                'refresh_token': auth_result.get('refresh_token'),
                'id_token': auth_result.get('id_token'),
                'expires_in': auth_result.get('expires_in', 86400),
                'session_id': db_session.session_id,
                'user_id': user.user_id,
                'message': '新規登録が完了しました。'
            }
            
        except Exception as e:
            logger.error(f"登録認証エラー: {e}")
            await logging_service.log_auth_attempt(
                phone_number, "error", 
                {"attempt_type": "signup_verification", "error": str(e)}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def verify_session(self, access_token: str) -> Dict[str, Any]:
        """
        セッションを検証
        
        Args:
            access_token: アクセストークン
            
        Returns:
            Dict: 検証結果
        """
        try:
            # データベースでセッションを確認
            session = await db_manager.get_session_by_token(access_token)
            if not session:
                return {
                    'success': False,
                    'error': 'invalid_session',
                    'message': '無効なセッションです。'
                }
            
            # セッション期限をチェック
            if datetime.utcnow() > session.expires_at:
                await db_manager.invalidate_session(session.session_id)
                return {
                    'success': False,
                    'error': 'session_expired',
                    'message': 'セッションの有効期限が切れています。'
                }
            
            # 非アクティブタイムアウトをチェック（2時間）
            if datetime.utcnow() > session.last_activity + timedelta(hours=2):
                await db_manager.invalidate_session(session.session_id)
                return {
                    'success': False,
                    'error': 'session_inactive',
                    'message': '非アクティブのためセッションが無効になりました。'
                }
            
            # セッションの最終活動時刻を更新
            await db_manager.update_session_activity(session.session_id)
            
            # ユーザー情報を取得
            user = await db_manager.get_user_by_id(session.user_id)
            if not user:
                return {
                    'success': False,
                    'error': 'user_not_found',
                    'message': 'ユーザーが見つかりません。'
                }
            
            return {
                'success': True,
                'user_id': user.user_id,
                'phone_number': user.phone_number,
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
                # セッションを無効化
                await db_manager.invalidate_session(session.session_id)
                
                # ユーザー情報を取得してログに記録
                user = await db_manager.get_user_by_id(session.user_id)
                if user:
                    await logging_service.log_auth_attempt(
                        user.phone_number, "success", 
                        {"attempt_type": "logout", "session_id": session.session_id}, 
                        user.user_id, ip_address
                    )
                    await logging_service.log_session_operation(
                        user.phone_number, "invalidated", "success", 
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
    
    async def refresh_auth_code(self, phone_number: str, old_session: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        認証コードを更新し、古いコードを無効化
        
        Args:
            phone_number: 電話番号
            old_session: 古いCognitoセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 認証コード更新結果
        """
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            
            # 電話番号形式を検証
            if not self.validate_phone_number(phone_number):
                await logging_service.log_auth_attempt(
                    phone_number, "failure", 
                    {"attempt_type": "auth_code_refresh", "error": "invalid_phone_format"}, 
                    None, ip_address
                )
                return {
                    'success': False,
                    'error': 'invalid_phone_format',
                    'message': '有効な日本の電話番号を入力してください。'
                }
            
            # 新しいSMS認証を開始（これにより古いコードが無効化される）
            result = await self.initiate_phone_auth(phone_number)
            
            if result['success']:
                await logging_service.log_sms_sent(
                    normalized_phone, "success", 
                    {"old_session": old_session, "new_session": result.get('session'), "sent_at": datetime.utcnow().isoformat()}, 
                    None, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "success", 
                    {"attempt_type": "auth_code_refresh", "old_session": old_session, "new_session": result.get('session')}, 
                    None, ip_address
                )
                
                logger.info(f"認証コードを更新しました: {normalized_phone}")
                
                return {
                    'success': True,
                    'session': result.get('session'),
                    'challenge_name': result.get('challenge_name'),
                    'message': '新しいSMS認証コードを送信しました。古いコードは無効になりました。'
                }
            else:
                await logging_service.log_sms_sent(
                    normalized_phone, "failure", 
                    {"error": result.get('error'), "attempted_at": datetime.utcnow().isoformat()}, 
                    None, ip_address
                )
                await logging_service.log_auth_attempt(
                    normalized_phone, "failure", 
                    {"attempt_type": "auth_code_refresh", "error": result.get('error')}, 
                    None, ip_address
                )
                return result
                
        except Exception as e:
            logger.error(f"認証コード更新エラー: {e}")
            await logging_service.log_auth_attempt(
                phone_number, "error", 
                {"attempt_type": "auth_code_refresh", "error": str(e)}, 
                None, ip_address
            )
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。管理者にお問い合わせください。'
            }
    
    async def cleanup_expired_sessions(self) -> Dict[str, Any]:
        """
        期限切れセッションのクリーンアップを実行
        
        Returns:
            Dict: クリーンアップ結果
        """
        try:
            cleaned_count = await db_manager.cleanup_expired_sessions()
            
            logger.info(f"期限切れセッションクリーンアップ完了: {cleaned_count}件")
            
            return {
                'success': True,
                'cleaned_count': cleaned_count,
                'message': f'{cleaned_count}件の期限切れセッションをクリーンアップしました。'
            }
            
        except Exception as e:
            logger.error(f"セッションクリーンアップエラー: {e}")
            return {
                'success': False,
                'error': 'cleanup_error',
                'message': 'セッションクリーンアップでエラーが発生しました。'
            }
    
    async def extend_session(self, access_token: str) -> Dict[str, Any]:
        """
        セッションの有効期限を延長
        
        Args:
            access_token: アクセストークン
            
        Returns:
            Dict: セッション延長結果
        """
        try:
            # セッションを取得
            session = await db_manager.get_session_by_token(access_token)
            if not session:
                return {
                    'success': False,
                    'error': 'invalid_session',
                    'message': '無効なセッションです。'
                }
            
            # セッション期限をチェック
            if datetime.utcnow() > session.expires_at:
                await db_manager.invalidate_session(session.session_id)
                return {
                    'success': False,
                    'error': 'session_expired',
                    'message': 'セッションの有効期限が切れています。'
                }
            
            # 非アクティブタイムアウトをチェック（2時間）
            if datetime.utcnow() > session.last_activity + timedelta(hours=2):
                await db_manager.invalidate_session(session.session_id)
                return {
                    'success': False,
                    'error': 'session_inactive',
                    'message': '非アクティブのためセッションが無効になりました。'
                }
            
            # セッションの有効期限を24時間延長
            new_expires_at = datetime.utcnow() + timedelta(hours=24)
            success = await db_manager.extend_session(session.session_id, new_expires_at)
            
            if success:
                logger.info(f"セッションを延長しました: {session.session_id}")
                return {
                    'success': True,
                    'expires_at': new_expires_at.isoformat(),
                    'message': 'セッションの有効期限を延長しました。'
                }
            else:
                return {
                    'success': False,
                    'error': 'extension_failed',
                    'message': 'セッション延長に失敗しました。'
                }
                
        except Exception as e:
            logger.error(f"セッション延長エラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
