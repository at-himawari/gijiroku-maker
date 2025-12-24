"""
Cognito トークン管理サービス
ID Token、Access Token、Refresh Token の管理、検証、リフレッシュ機能
"""
import os
import jwt
import boto3
import logging
import json
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from database import db_manager
from models import UserSession, SessionCreate
from logging_service import logging_service

load_dotenv()

logger = logging.getLogger(__name__)

class CognitoTokenService:
    """Cognito トークン管理サービス"""
    
    def __init__(self):
        """CognitoTokenService を初期化"""
        self.region = os.getenv('AWS_REGION', 'ap-northeast-1')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('COGNITO_CLIENT_ID')
        
        if not self.user_pool_id or not self.client_id:
            raise ValueError("Cognito 設定が不完全です。環境変数を確認してください。")
        
        # Cognito クライアントを初期化
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        
        # JWKSエンドポイントURL
        self.jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
        self.jwks_cache = None
        self.jwks_cache_expiry = None
    
    async def get_jwks(self) -> Dict[str, Any]:
        """
        Cognito JWKSを取得（キャッシュ付き）
        
        Returns:
            Dict: JWKS データ
        """
        try:
            # キャッシュが有効かチェック
            if (self.jwks_cache and self.jwks_cache_expiry and 
                datetime.utcnow() < self.jwks_cache_expiry):
                return self.jwks_cache
            
            # JWKSを取得
            response = requests.get(self.jwks_url, timeout=10)
            response.raise_for_status()
            
            self.jwks_cache = response.json()
            # 1時間キャッシュ
            self.jwks_cache_expiry = datetime.utcnow() + timedelta(hours=1)
            
            logger.debug("Cognito JWKSを取得しました")
            return self.jwks_cache
            
        except Exception as e:
            logger.error(f"JWKS取得エラー: {e}")
            raise
    
    def get_jwk_key(self, token_header: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        JWTヘッダーからJWKキーを取得
        
        Args:
            token_header: JWTヘッダー
            
        Returns:
            Optional[Dict]: JWKキー
        """
        try:
            if not self.jwks_cache:
                return None
            
            kid = token_header.get('kid')
            if not kid:
                return None
            
            for key in self.jwks_cache.get('keys', []):
                if key.get('kid') == kid:
                    return key
            
            return None
            
        except Exception as e:
            logger.error(f"JWKキー取得エラー: {e}")
            return None
    
    async def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Cognito ID Tokenを検証
        
        Args:
            id_token: 検証するID Token
            
        Returns:
            Dict: 検証結果とペイロード
        """
        try:
            if not id_token:
                return {
                    'valid': False,
                    'error': 'missing_token',
                    'message': 'ID Tokenが提供されていません。'
                }
            
            # JWKSを取得
            await self.get_jwks()
            
            # JWTヘッダーをデコード
            try:
                header = jwt.get_unverified_header(id_token)
            except jwt.InvalidTokenError as e:
                return {
                    'valid': False,
                    'error': 'invalid_token_format',
                    'message': 'ID Tokenの形式が無効です。'
                }
            
            # JWKキーを取得
            jwk_key = self.get_jwk_key(header)
            if not jwk_key:
                return {
                    'valid': False,
                    'error': 'jwk_key_not_found',
                    'message': 'JWKキーが見つかりません。'
                }
            
            # RSA公開キーを構築
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(json.dumps(jwk_key))
            
            # JWTを検証
            try:
                payload = jwt.decode(
                    id_token,
                    public_key,
                    algorithms=['RS256'],
                    options={"verify_aud": False}, # audクレームの検証を個別に行うため一旦スキップ
                    issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
                )
                
                # ID Tokenの audience (aud) は client_id と一致する必要がある
                # クレームが存在しない場合や一致しない場合にエラーを出す
                if payload.get('aud') != self.client_id:
                    return {
                        'valid': False,
                        'error': 'invalid_audience',
                        'message': 'ID Tokenのaudienceが無効です。'
                    }
            except jwt.ExpiredSignatureError:
                return {
                    'valid': False,
                    'error': 'token_expired',
                    'message': 'ID Tokenの有効期限が切れています。'
                }
            except jwt.InvalidAudienceError:
                return {
                    'valid': False,
                    'error': 'invalid_audience',
                    'message': 'ID Tokenのaudienceが無効です。'
                }
            except jwt.InvalidIssuerError:
                return {
                    'valid': False,
                    'error': 'invalid_issuer',
                    'message': 'ID Tokenのissuerが無効です。'
                }
            except jwt.InvalidTokenError as e:
                return {
                    'valid': False,
                    'error': 'invalid_token',
                    'message': f'ID Tokenが無効です: {str(e)}'
                }
            
            # トークンタイプを確認
            if payload.get('token_use') != 'id':
                return {
                    'valid': False,
                    'error': 'invalid_token_type',
                    'message': 'ID Tokenではありません。'
                }
            
            return {
                'valid': True,
                'payload': payload,
                'user_sub': payload.get('sub'),
                'email': payload.get('email'),
                'given_name': payload.get('given_name'),
                'family_name': payload.get('family_name'),
                'phone_number': payload.get('phone_number'),
                'exp': payload.get('exp'),
                'iat': payload.get('iat')
            }
            
        except Exception as e:
            logger.error(f"ID Token検証エラー: {e}")
            return {
                'valid': False,
                'error': 'verification_error',
                'message': 'ID Token検証中にエラーが発生しました。'
            }
    
    async def verify_access_token(self, access_token: str) -> Dict[str, Any]:
        """
        Cognito Access Tokenを検証
        
        Args:
            access_token: 検証するAccess Token
            
        Returns:
            Dict: 検証結果とペイロード
        """
        try:
            if not access_token:
                return {
                    'valid': False,
                    'error': 'missing_token',
                    'message': 'Access Tokenが提供されていません。'
                }
            
            # JWKSを取得
            await self.get_jwks()
            
            # JWTヘッダーをデコード
            try:
                header = jwt.get_unverified_header(access_token)
            except jwt.InvalidTokenError as e:
                return {
                    'valid': False,
                    'error': 'invalid_token_format',
                    'message': 'Access Tokenの形式が無効です。'
                }
            
            # JWKキーを取得
            jwk_key = self.get_jwk_key(header)
            if not jwk_key:
                return {
                    'valid': False,
                    'error': 'jwk_key_not_found',
                    'message': 'JWKキーが見つかりません。'
                }
            
            # RSA公開キーを構築
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(json.dumps(jwk_key))
            
            # JWTを検証
            try:
                # Access Tokenには標準的な 'aud' クレームが含まれていないため、
                # audience の検証をスキップし、代わりに client_id クレームを確認する
                payload = jwt.decode(
                    access_token,
                    public_key,
                    algorithms=['RS256'],
                    options={"verify_aud": False},
                    issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
                )
                
                # client_id クレームの検証
                if payload.get('client_id') != self.client_id:
                    return {
                        'valid': False,
                        'error': 'invalid_client_id',
                        'message': 'Access Tokenのclient_idが無効です。'
                    }
                    
            except jwt.ExpiredSignatureError:
                return {
                    'valid': False,
                    'error': 'token_expired',
                    'message': 'Access Tokenの有効期限が切れています。'
                }
            except jwt.InvalidAudienceError:
                return {
                    'valid': False,
                    'error': 'invalid_audience',
                    'message': 'Access Tokenのaudienceが無効です。'
                }
            except jwt.InvalidIssuerError:
                return {
                    'valid': False,
                    'error': 'invalid_issuer',
                    'message': 'Access Tokenのissuerが無効です。'
                }
            except jwt.InvalidTokenError as e:
                return {
                    'valid': False,
                    'error': 'invalid_token',
                    'message': f'Access Tokenが無効です: {str(e)}'
                }
            
            # トークンタイプを確認
            if payload.get('token_use') != 'access':
                return {
                    'valid': False,
                    'error': 'invalid_token_type',
                    'message': 'Access Tokenではありません。'
                }
            
            return {
                'valid': True,
                'payload': payload,
                'user_sub': payload.get('sub'),
                'username': payload.get('username'),
                'client_id': payload.get('client_id'),
                'scope': payload.get('scope'),
                'exp': payload.get('exp'),
                'iat': payload.get('iat')
            }
            
        except Exception as e:
            logger.error(f"Access Token検証エラー: {e}")
            return {
                'valid': False,
                'error': 'verification_error',
                'message': 'Access Token検証中にエラーが発生しました。'
            }
    
    async def refresh_tokens(self, refresh_token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Refresh Tokenを使用してトークンをリフレッシュ
        
        Args:
            refresh_token: リフレッシュトークン
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: リフレッシュ結果
        """
        try:
            if not refresh_token:
                return {
                    'success': False,
                    'error': 'missing_refresh_token',
                    'message': 'Refresh Tokenが提供されていません。'
                }
            
            # Cognito でトークンをリフレッシュ
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )
            
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                # 新しいトークンを取得
                new_access_token = auth_result.get('AccessToken')
                new_id_token = auth_result.get('IdToken')
                expires_in = auth_result.get('ExpiresIn', 3600)
                
                # 新しいRefresh Tokenが提供される場合もある
                new_refresh_token = auth_result.get('RefreshToken', refresh_token)
                
                logger.info("Cognitoトークンリフレッシュ成功")
                
                return {
                    'success': True,
                    'access_token': new_access_token,
                    'id_token': new_id_token,
                    'refresh_token': new_refresh_token,
                    'expires_in': expires_in,
                    'message': 'トークンを更新しました。'
                }
            else:
                return {
                    'success': False,
                    'error': 'refresh_failed',
                    'message': 'トークンの更新に失敗しました。'
                }
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Cognitoトークンリフレッシュエラー: {error_code} - {e}")
            
            if error_code == 'NotAuthorizedException':
                return {
                    'success': False,
                    'error': 'invalid_refresh_token',
                    'message': 'Refresh Tokenが無効です。再度ログインしてください。'
                }
            elif error_code == 'TokenRefreshException':
                return {
                    'success': False,
                    'error': 'refresh_token_expired',
                    'message': 'Refresh Tokenの有効期限が切れています。再度ログインしてください。'
                }
            else:
                return {
                    'success': False,
                    'error': 'cognito_error',
                    'message': 'トークン更新サービスでエラーが発生しました。'
                }
                
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': 'システムエラーが発生しました。'
            }
    
    async def validate_and_sync_session(self, access_token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Cognitoトークンを検証し、ローカルセッションと同期
        自動トークンリフレッシュ機能付き
        
        Args:
            access_token: 検証するAccess Token
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 検証・同期結果
        """
        try:
            # Access Tokenを検証
            access_validation = await self.verify_access_token(access_token)
            
            # トークンが期限切れの場合、自動リフレッシュを試行
            if not access_validation['valid'] and access_validation['error'] == 'token_expired':
                logger.info("Access Tokenが期限切れです。自動リフレッシュを試行します。")
                
                # ローカルセッションからRefresh Tokenを取得
                session = await db_manager.get_session_by_token(access_token)
                # 属性の存在を安全にチェック
                if session and hasattr(session, 'refresh_token_hash') and session.refresh_token_hash:
                    # Refresh Tokenでトークンを更新
                    refresh_result = await self._auto_refresh_session_tokens(session, ip_address)
                    if refresh_result['success']:
                        # 新しいAccess Tokenで再検証
                        access_validation = await self.verify_access_token(refresh_result['new_access_token'])
                        if access_validation['valid']:
                            logger.info("自動トークンリフレッシュが成功しました。")
                            # 新しいトークンを返す
                            access_validation['token_refreshed'] = True
                            access_validation['new_access_token'] = refresh_result['new_access_token']
                            access_validation['new_id_token'] = refresh_result.get('new_id_token')
                        else:
                            logger.warning("リフレッシュ後のトークン検証に失敗しました。")
                    else:
                        logger.warning(f"自動トークンリフレッシュに失敗しました: {refresh_result['error']}")
            
            if not access_validation['valid']:
                return {
                    'success': False,
                    'error': access_validation['error'],
                    'message': access_validation['message']
                }
            
            user_sub = access_validation['user_sub']
            
            # ローカルセッションを取得
            session = await db_manager.get_session_by_token(access_token)
            if not session:
                logger.info(f"ローカルセッションが見つかりません。新規作成します (JIT): user_sub={user_sub}")
                # ユーザーがデータベースに存在するか確認、なければ作成
                user = await db_manager.get_user_by_cognito_sub(user_sub)
                if not user:
                    from models import UserCreate
                    user = await db_manager.create_user(UserCreate(cognito_user_sub=user_sub))
                
                if not user:
                    return {
                        'success': False,
                        'error': 'user_creation_failed',
                        'message': 'ユーザーの自動作成に失敗しました。'
                    }

                # 新しいセッションを作成
                from models import SessionCreate
                # 有効期限をトークンのexpから計算
                expires_in = access_validation['exp'] - int(datetime.utcnow().timestamp())
                if expires_in <= 0:
                    expires_in = 3600 # フォールバック

                    session_data = SessionCreate(
                        user_id=user.user_id,
                        cognito_user_sub=user_sub,
                        access_token=access_token,
                        expires_in=expires_in,
                        client_ip=ip_address
                    )
                    session = await db_manager.create_session(session_data)
                    logger.info(f"JITセッション作成完了: {session.session_id if session else '失敗'}")
                
                if not session:
                    return {
                        'success': False,
                        'error': 'session_creation_failed',
                        'message': 'セッションの自動作成に失敗しました。'
                    }
            
            # セッション期限をチェック（24時間）
            if datetime.utcnow() > session.expires_at:
                # セッション期限切れの場合、自動延長を試行
                logger.info("セッションが期限切れです。自動延長を試行します。")
                extension_result = await self._auto_extend_session(session, ip_address)
                if not extension_result['success']:
                    await db_manager.invalidate_session(session.session_id)
                    return {
                        'success': False,
                        'error': 'session_expired',
                        'message': 'セッションの有効期限が切れています。'
                    }
                else:
                    logger.info("セッションの自動延長が成功しました。")
                    # 延長されたセッション情報を再取得
                    session = await db_manager.get_session_by_id(session.session_id)
            
            # 非アクティブタイムアウトをチェック（2時間）
            if datetime.utcnow() > session.last_activity + timedelta(hours=2):
                await db_manager.invalidate_session(session.session_id)
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "auto_logout", "success",
                    {
                        "session_id": session.session_id,
                        "reason": "inactive_timeout",
                        "last_activity": session.last_activity.isoformat()
                    },
                    session.user_id, ip_address
                )
                return {
                    'success': False,
                    'error': 'session_inactive',
                    'message': '非アクティブのためセッションが無効になりました。'
                }
            
            # Cognito User Subが一致するかチェック
            if session.cognito_user_sub != user_sub:
                await db_manager.invalidate_session(session.session_id)
                return {
                    'success': False,
                    'error': 'user_mismatch',
                    'message': 'ユーザー情報が一致しません。'
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
            
            # ユーザーがアクティブかチェック
            if not user.is_active:
                return {
                    'success': False,
                    'error': 'user_inactive',
                    'message': 'ユーザーアカウントが無効です。'
                }
            
            result = {
                'success': True,
                'user': user,
                'session': session,
                'cognito_payload': access_validation['payload'],
                'message': 'トークン検証・セッション同期成功'
            }
            
            # トークンがリフレッシュされた場合、新しいトークンを含める
            if access_validation.get('token_refreshed'):
                result['token_refreshed'] = True
                result['new_access_token'] = access_validation['new_access_token']
                result['new_id_token'] = access_validation.get('new_id_token')
            
            return result
            
        except Exception as e:
            logger.error(f"トークン検証・セッション同期エラー: {e}")
            return {
                'success': False,
                'error': 'validation_error',
                'message': 'トークン検証・セッション同期中にエラーが発生しました。'
            }
    
    async def update_session_tokens(self, session_id: str, new_access_token: str, 
                                  new_id_token: Optional[str] = None, 
                                  new_refresh_token: Optional[str] = None,
                                  expires_in: int = 3600) -> Dict[str, Any]:
        """
        セッションのトークンを更新
        
        Args:
            session_id: セッションID
            new_access_token: 新しいAccess Token
            new_id_token: 新しいID Token
            new_refresh_token: 新しいRefresh Token
            expires_in: 有効期限（秒）
            
        Returns:
            Dict: 更新結果
        """
        try:
            import hashlib
            from encryption_utils import encryption_utils
            
            # 新しい有効期限を計算
            new_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # トークンをハッシュ化
            access_token_hash = hashlib.sha256(new_access_token.encode()).hexdigest()
            id_token_hash = hashlib.sha256(new_id_token.encode()).hexdigest() if new_id_token else None
            refresh_token_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest() if new_refresh_token else None
            
            # Refresh Tokenを暗号化
            encrypted_refresh_token = None
            if new_refresh_token:
                try:
                    encrypted_refresh_token = encryption_utils.encrypt_token(new_refresh_token)
                except Exception as e:
                    logger.error(f"新しいRefresh Token暗号化エラー: {e}")
            
            # データベースを更新
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # 更新するフィールドを動的に構築
                    update_fields = ["access_token_hash = %s", "expires_at = %s", "last_activity = %s"]
                    update_values = [access_token_hash, new_expires_at, datetime.utcnow()]
                    
                    if id_token_hash:
                        update_fields.append("id_token_hash = %s")
                        update_values.append(id_token_hash)
                    
                    if refresh_token_hash:
                        update_fields.append("refresh_token_hash = %s")
                        update_values.append(refresh_token_hash)
                    
                    if encrypted_refresh_token:
                        update_fields.append("encrypted_refresh_token = %s")
                        update_values.append(encrypted_refresh_token)
                    
                    update_values.append(session_id)
                    
                    await cursor.execute(f"""
                        UPDATE user_sessions 
                        SET {', '.join(update_fields)}
                        WHERE session_id = %s AND is_active = TRUE
                    """, update_values)
                    
                    if cursor.rowcount == 0:
                        return {
                            'success': False,
                            'error': 'session_not_found',
                            'message': 'セッションが見つかりません。'
                        }
            
            logger.info(f"セッショントークンを更新しました: {session_id}")
            
            return {
                'success': True,
                'expires_at': new_expires_at.isoformat(),
                'message': 'セッショントークンを更新しました。'
            }
            
        except Exception as e:
            logger.error(f"セッショントークン更新エラー: {e}")
            return {
                'success': False,
                'error': 'update_error',
                'message': 'セッショントークン更新中にエラーが発生しました。'
            }
    
    async def get_token_expiry_info(self, access_token: str) -> Dict[str, Any]:
        """
        トークンの有効期限情報を取得
        
        Args:
            access_token: Access Token
            
        Returns:
            Dict: 有効期限情報
        """
        try:
            # Access Tokenを検証（有効期限チェック含む）
            validation_result = await self.verify_access_token(access_token)
            
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': validation_result['error'],
                    'message': validation_result['message']
                }
            
            payload = validation_result['payload']
            exp_timestamp = payload.get('exp')
            iat_timestamp = payload.get('iat')
            
            if not exp_timestamp:
                return {
                    'success': False,
                    'error': 'missing_expiry',
                    'message': 'トークンに有効期限情報がありません。'
                }
            
            exp_datetime = datetime.utcfromtimestamp(exp_timestamp)
            iat_datetime = datetime.utcfromtimestamp(iat_timestamp) if iat_timestamp else None
            current_time = datetime.utcnow()
            
            # 残り時間を計算
            time_remaining = exp_datetime - current_time
            seconds_remaining = max(0, int(time_remaining.total_seconds()))
            
            return {
                'success': True,
                'issued_at': iat_datetime.isoformat() if iat_datetime else None,
                'expires_at': exp_datetime.isoformat(),
                'current_time': current_time.isoformat(),
                'seconds_remaining': seconds_remaining,
                'is_expired': seconds_remaining == 0,
                'needs_refresh': seconds_remaining < 300,  # 5分以内
                'message': 'トークン有効期限情報を取得しました。'
            }
            
        except Exception as e:
            logger.error(f"トークン有効期限情報取得エラー: {e}")
            return {
                'success': False,
                'error': 'expiry_check_error',
                'message': 'トークン有効期限情報取得中にエラーが発生しました。'
            }
    
    async def _auto_refresh_session_tokens(self, session: UserSession, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        セッションのトークンを自動リフレッシュ
        
        Args:
            session: ユーザーセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: リフレッシュ結果
        """
        try:
            if not session.refresh_token_hash:
                return {
                    'success': False,
                    'error': 'no_refresh_token',
                    'message': 'Refresh Tokenが見つかりません。'
                }
            
            # 実際のRefresh Tokenを取得（ハッシュから復元は不可能なので、別途保存が必要）
            # 注意: セキュリティ上、Refresh Tokenは暗号化して保存すべき
            # ここでは簡略化のため、セッションテーブルに暗号化されたRefresh Tokenを保存する想定
            
            # データベースから暗号化されたRefresh Tokenを取得
            refresh_token = await self._get_encrypted_refresh_token(session.session_id)
            if not refresh_token:
                return {
                    'success': False,
                    'error': 'refresh_token_not_found',
                    'message': '暗号化されたRefresh Tokenが見つかりません。'
                }
            
            # トークンをリフレッシュ
            refresh_result = await self.refresh_tokens(refresh_token, ip_address)
            if not refresh_result['success']:
                return refresh_result
            
            # セッションのトークンを更新
            update_result = await self.update_session_tokens(
                session.session_id,
                refresh_result['access_token'],
                refresh_result.get('id_token'),
                refresh_result.get('refresh_token'),
                refresh_result.get('expires_in', 3600)
            )
            
            if update_result['success']:
                # 自動リフレッシュログ
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "auto_refresh", "success",
                    {
                        "session_id": session.session_id,
                        "expires_in": refresh_result.get('expires_in', 3600)
                    },
                    session.user_id, ip_address
                )
                
                return {
                    'success': True,
                    'new_access_token': refresh_result['access_token'],
                    'new_id_token': refresh_result.get('id_token'),
                    'expires_in': refresh_result.get('expires_in', 3600),
                    'message': 'トークンを自動リフレッシュしました。'
                }
            else:
                return update_result
                
        except Exception as e:
            logger.error(f"自動トークンリフレッシュエラー: {e}")
            return {
                'success': False,
                'error': 'auto_refresh_error',
                'message': '自動トークンリフレッシュ中にエラーが発生しました。'
            }
    
    async def _auto_extend_session(self, session: UserSession, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        セッションを自動延長
        
        Args:
            session: ユーザーセッション
            ip_address: クライアントのIPアドレス
            
        Returns:
            Dict: 延長結果
        """
        try:
            # セッションが最近アクティブだった場合のみ自動延長
            last_activity_threshold = datetime.utcnow() - timedelta(hours=1)  # 1時間以内にアクティブ
            
            if session.last_activity < last_activity_threshold:
                return {
                    'success': False,
                    'error': 'session_too_old',
                    'message': 'セッションが長時間非アクティブのため自動延長できません。'
                }
            
            # セッションを24時間延長
            from session_manager import session_manager
            extension_result = await session_manager.extend_session(session.session_id, 24)
            
            if extension_result['success']:
                # 自動延長ログ
                await logging_service.log_cognito_session_operation(
                    "cognito_user", "auto_extend", "success",
                    {
                        "session_id": session.session_id,
                        "extension_hours": 24,
                        "new_expires_at": extension_result['expires_at']
                    },
                    session.user_id, ip_address
                )
                
                logger.info(f"セッションを自動延長しました: {session.session_id}")
            
            return extension_result
            
        except Exception as e:
            logger.error(f"セッション自動延長エラー: {e}")
            return {
                'success': False,
                'error': 'auto_extend_error',
                'message': 'セッション自動延長中にエラーが発生しました。'
            }
    
    async def _get_encrypted_refresh_token(self, session_id: str) -> Optional[str]:
        """
        暗号化されたRefresh Tokenを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            Optional[str]: 復号化されたRefresh Token
        """
        try:
            from encryption_utils import encryption_utils
            
            async with db_manager.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        SELECT encrypted_refresh_token 
                        FROM user_sessions 
                        WHERE session_id = %s AND is_active = TRUE
                    """, (session_id,))
                    
                    row = await cursor.fetchone()
                    if row and row[0]:
                        encrypted_token = row[0]
                        
                        # 暗号化されたトークンを復号化
                        try:
                            decrypted_token = encryption_utils.decrypt_token(encrypted_token)
                            return decrypted_token
                        except Exception as e:
                            logger.error(f"Refresh Token復号化エラー: {e}")
                            return None
                    
                    return None
                    
        except Exception as e:
            logger.error(f"暗号化Refresh Token取得エラー: {e}")
            return None


# グローバルインスタンス
cognito_token_service = CognitoTokenService()
