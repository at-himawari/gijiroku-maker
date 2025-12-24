"""
ログ機能サービス
認証、SMS、セッション、課金、セキュリティに関するログを記録
CloudWatch Logs統合対応
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from database import db_manager
from models import AuthLogCreate
import json
import os

logger = logging.getLogger(__name__)

# CloudWatch Logs統合設定
ENABLE_CLOUDWATCH_LOGS = os.getenv("ENABLE_CLOUDWATCH_LOGS", "false").lower() == "true"
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/aws/application/gijiroku-maker")
CLOUDWATCH_LOG_STREAM = os.getenv("CLOUDWATCH_LOG_STREAM", "authentication-logs")


class LoggingService:
    """ログ記録サービスクラス"""
    
    def __init__(self):
        """ログサービスを初期化"""
        self.db = db_manager
        
        # CloudWatch Logs クライアントの初期化（オプション）
        self.cloudwatch_client = None
        if ENABLE_CLOUDWATCH_LOGS:
            try:
                import boto3
                self.cloudwatch_client = boto3.client('logs')
                logger.info("CloudWatch Logs統合が有効化されました")
            except ImportError:
                logger.warning("boto3がインストールされていません。CloudWatch Logs統合は無効です")
            except Exception as e:
                logger.error(f"CloudWatch Logs初期化エラー: {e}")
    
    async def _send_to_cloudwatch(self, log_entry: Dict[str, Any]) -> bool:
        """
        CloudWatch Logsにログエントリを送信
        
        Args:
            log_entry: ログエントリ
            
        Returns:
            bool: 送信成功/失敗
        """
        if not self.cloudwatch_client or not ENABLE_CLOUDWATCH_LOGS:
            return False
        
        try:
            # ログメッセージを構築
            log_message = json.dumps(log_entry, ensure_ascii=False, default=str)
            
            # CloudWatch Logsに送信
            response = self.cloudwatch_client.put_log_events(
                logGroupName=CLOUDWATCH_LOG_GROUP,
                logStreamName=CLOUDWATCH_LOG_STREAM,
                logEvents=[
                    {
                        'timestamp': int(datetime.utcnow().timestamp() * 1000),
                        'message': log_message
                    }
                ]
            )
            
            logger.debug(f"CloudWatch Logsに送信成功: {response.get('nextSequenceToken', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"CloudWatch Logs送信エラー: {e}")
            return False
    
    async def log_auth_attempt(
        self,
        phone_number: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        認証試行ログを記録
        
        Args:
            phone_number: 電話番号
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（試行タイプ、失敗理由など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            log_data = AuthLogCreate(
                user_id=user_id,
                phone_number=phone_number,
                event_type="auth_attempt",
                result=result,
                details=details,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"認証試行ログを記録しました: "
                    f"電話番号={phone_number}, 結果={result}, "
                    f"詳細={json.dumps(details, ensure_ascii=False)}"
                )
                
                # CloudWatch Logsに送信
                await self._send_to_cloudwatch({
                    "event_type": "auth_attempt",
                    "user_id": user_id,
                    "phone_number": phone_number,
                    "result": result,
                    "details": details,
                    "ip_address": ip_address,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return True
            else:
                logger.error(f"認証試行ログの記録に失敗しました: {phone_number}")
                return False
                
        except Exception as e:
            logger.error(f"認証試行ログ記録エラー: {e}")
            return False
    
    async def log_sms_sent(
        self,
        phone_number: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        SMS送信ログを記録
        
        Args:
            phone_number: 送信先電話番号
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（送信時刻、メッセージタイプなど）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            log_data = AuthLogCreate(
                user_id=user_id,
                phone_number=phone_number,
                event_type="sms_sent",
                result=result,
                details=details, # Pydanticのバリデーションを通るよう辞書型のまま渡す
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"SMS送信ログを記録しました: "
                    f"電話番号={phone_number}, 結果={result}, "
                    f"送信時刻={details.get('sent_at', 'N/A')}"
                )
                return True
            else:
                logger.error(f"SMS送信ログの記録に失敗しました: {phone_number}")
                return False
                
        except Exception as e:
            logger.error(f"SMS送信ログ記録エラー: {e}")
            return False
    
    async def log_session_operation(
        self,
        phone_number: str,
        operation: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        セッション操作ログを記録
        
        Args:
            phone_number: 電話番号
            operation: 操作タイプ ("created", "updated", "invalidated", "extended")
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（セッションID、有効期限など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            # 操作タイプを詳細に含める
            details_with_operation = {**details, "operation": operation}
            
            log_data = AuthLogCreate(
                user_id=user_id,
                phone_number=phone_number,
                event_type="session_operation",
                result=result,
                details=details_with_operation,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"セッション操作ログを記録しました: "
                    f"電話番号={phone_number}, 操作={operation}, 結果={result}, "
                    f"セッションID={details.get('session_id', 'N/A')}"
                )
                return True
            else:
                logger.error(f"セッション操作ログの記録に失敗しました: {phone_number}")
                return False
                
        except Exception as e:
            logger.error(f"セッション操作ログ記録エラー: {e}")
            return False
    
    async def log_billing_operation(
        self,
        user_id: str,
        phone_number: str,
        amount: float,
        result: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None
    ) -> bool:
        """
        課金処理ログを記録
        
        Args:
            user_id: ユーザーID
            phone_number: 電話番号
            amount: 課金金額
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（処理時刻、トランザクションIDなど）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            # 課金金額を詳細に含める
            details_with_amount = {
                **details,
                "amount": amount,
                "currency": "JPY",
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                phone_number=phone_number,
                event_type="billing_operation",
                result=result,
                details=details_with_amount,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"課金処理ログを記録しました: "
                    f"ユーザーID={user_id}, 金額={amount}円, 結果={result}, "
                    f"トランザクションID={details.get('transaction_id', 'N/A')}"
                )
                return True
            else:
                logger.error(f"課金処理ログの記録に失敗しました: ユーザーID={user_id}")
                return False
                
        except Exception as e:
            logger.error(f"課金処理ログ記録エラー: {e}")
            return False
    
    async def log_security_error(
        self,
        email: str,
        error_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        セキュリティエラーログを記録
        
        Args:
            email: メールアドレス（電話番号から変更）
            error_type: エラータイプ ("invalid_token", "account_locked", "suspicious_activity", etc.)
            details: 詳細情報（エラーメッセージ、攻撃の可能性など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            # エラータイプを詳細に含める
            details_with_error = {
                **details,
                "error_type": error_type,
                "detected_at": datetime.utcnow().isoformat(),
                "severity": self._get_security_severity(error_type)
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="security_error",
                result="error",
                details=details_with_error, # Pydanticのバリデーションを通るよう辞書型のまま渡す
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                severity = details_with_error.get('severity', 'medium')
                if severity == 'high':
                    logger.error(
                        f"【高危険度】セキュリティエラーログを記録しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}, "
                        f"IPアドレス={ip_address}, "
                        f"詳細={json.dumps(details, ensure_ascii=False)}"
                    )
                elif severity == 'medium':
                    logger.warning(
                        f"【中危険度】セキュリティエラーログを記録しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}, "
                        f"IPアドレス={ip_address}, "
                        f"詳細={json.dumps(details, ensure_ascii=False)}"
                    )
                else:
                    logger.info(
                        f"【低危険度】セキュリティエラーログを記録しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}, "
                        f"IPアドレス={ip_address}"
                    )
                
                # CloudWatch Logsに送信（セキュリティログは重要なので必ず送信）
                await self._send_to_cloudwatch({
                    "event_type": "security_error",
                    "user_id": user_id,
                    "email": email,
                    "error_type": error_type,
                    "severity": severity,
                    "details": details,
                    "ip_address": ip_address,
                    "timestamp": datetime.utcnow().isoformat(),
                    "alert_level": "critical" if severity == "high" else "warning" if severity == "medium" else "info"
                })
                
                return True
            else:
                logger.error(f"セキュリティエラーログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"セキュリティエラーログ記録エラー: {e}")
            return False

    async def log_cognito_brute_force_attack(
        self,
        email: str,
        attack_details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoブルートフォース攻撃ログを記録
        
        Args:
            email: 攻撃対象のメールアドレス
            attack_details: 攻撃詳細（試行回数、時間範囲など）
            user_id: ユーザーID（オプション）
            ip_address: 攻撃元IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_attack = {
                **attack_details,
                "attack_type": "brute_force",
                "service": "cognito",
                "detected_at": datetime.utcnow().isoformat(),
                "severity": "high"
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_brute_force_attack",
                result="error",
                details=details_with_attack,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.error(
                    f"【セキュリティ警告】Cognitoブルートフォース攻撃を検出しました: "
                    f"メールアドレス={email}, IPアドレス={ip_address}, "
                    f"試行回数={attack_details.get('attempt_count', 'N/A')}, "
                    f"時間範囲={attack_details.get('time_window', 'N/A')}"
                )
                return True
            else:
                logger.error(f"Cognitoブルートフォース攻撃ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoブルートフォース攻撃ログ記録エラー: {e}")
            return False

    async def log_cognito_unauthorized_access(
        self,
        email: str,
        access_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognito不正アクセス試行ログを記録
        
        Args:
            email: メールアドレス
            access_type: アクセスタイプ ("invalid_token", "expired_session", "unauthorized_endpoint", etc.)
            details: 詳細情報（エンドポイント、トークン情報など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_access = {
                **details,
                "access_type": access_type,
                "service": "cognito",
                "detected_at": datetime.utcnow().isoformat(),
                "severity": self._get_access_severity(access_type)
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_unauthorized_access",
                result="error",
                details=details_with_access, # Pydanticのバリデーションを通るよう辞書型のまま渡す
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                severity = details_with_access.get('severity', 'medium')
                if severity == 'high':
                    logger.error(
                        f"【セキュリティ警告】Cognito不正アクセス試行を検出しました: "
                        f"メールアドレス={email}, アクセスタイプ={access_type}, "
                        f"IPアドレス={ip_address}, "
                        f"詳細={json.dumps(details, ensure_ascii=False)}"
                    )
                else:
                    logger.warning(
                        f"Cognito不正アクセス試行ログを記録しました: "
                        f"メールアドレス={email}, アクセスタイプ={access_type}, "
                        f"IPアドレス={ip_address}"
                    )
                return True
            else:
                logger.error(f"Cognito不正アクセス試行ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognito不正アクセス試行ログ記録エラー: {e}")
            return False

    async def log_cognito_security_error(
        self,
        email: str,
        error_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoセキュリティエラーログを記録
        
        Args:
            email: メールアドレス
            error_type: エラータイプ ("token_validation_failed", "csrf_detected", "rate_limit_exceeded", etc.)
            details: 詳細情報（エラーメッセージ、検出条件など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_security = {
                **details,
                "error_type": error_type,
                "service": "cognito",
                "detected_at": datetime.utcnow().isoformat(),
                "severity": self._get_security_severity(error_type)
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_security_error",
                result="error",
                details=details_with_security,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                severity = details_with_security.get('severity', 'medium')
                if severity == 'high':
                    logger.error(
                        f"【高危険度】Cognitoセキュリティエラーを検出しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}, "
                        f"IPアドレス={ip_address}, "
                        f"詳細={json.dumps(details, ensure_ascii=False)}"
                    )
                elif severity == 'medium':
                    logger.warning(
                        f"【中危険度】Cognitoセキュリティエラーを検出しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}, "
                        f"IPアドレス={ip_address}"
                    )
                else:
                    logger.info(
                        f"【低危険度】Cognitoセキュリティエラーを検出しました: "
                        f"メールアドレス={email}, エラータイプ={error_type}"
                    )
                return True
            else:
                logger.error(f"Cognitoセキュリティエラーログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoセキュリティエラーログ記録エラー: {e}")
            return False

    async def log_billing_service_execution(
        self,
        user_id: str,
        user_identifier: str,
        service_name: str,
        amount: float,
        result: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None
    ) -> bool:
        """
        課金サービス実行ログを記録
        
        Args:
            user_id: ユーザーID
            user_identifier: ユーザー識別子（メールアドレスまたは電話番号）
            service_name: サービス名（"generate_minutes", "transcription", etc.）
            amount: 課金金額
            result: 結果 ("started", "success", "failure", "error")
            details: 詳細情報（処理時刻、トランザクションIDなど）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            # 課金金額と詳細を含める
            details_with_billing = {
                **details,
                "service_name": service_name,
                "amount": amount,
                "currency": "JPY",
                "processed_at": datetime.utcnow().isoformat(),
                "billing_service": True
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=user_identifier,
                event_type="billing_service_execution",
                result=result,
                details=details_with_billing,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                if result == "success":
                    logger.info(
                        f"課金サービス実行成功ログを記録しました: "
                        f"ユーザーID={user_id}, サービス={service_name}, "
                        f"金額={amount}円, 結果={result}"
                    )
                elif result == "failure":
                    logger.warning(
                        f"課金サービス実行失敗ログを記録しました: "
                        f"ユーザーID={user_id}, サービス={service_name}, "
                        f"金額={amount}円, エラー={details.get('error', 'N/A')}"
                    )
                else:
                    logger.info(
                        f"課金サービス実行ログを記録しました: "
                        f"ユーザーID={user_id}, サービス={service_name}, "
                        f"金額={amount}円, 結果={result}"
                    )
                
                # CloudWatch Logsに送信（課金ログは重要なので必ず送信）
                await self._send_to_cloudwatch({
                    "event_type": "billing_service_execution",
                    "user_id": user_id,
                    "user_identifier": user_identifier,
                    "service_name": service_name,
                    "amount": amount,
                    "currency": "JPY",
                    "result": result,
                    "details": details,
                    "ip_address": ip_address,
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high" if result == "failure" else "normal"
                })
                
                return True
            else:
                logger.error(f"課金サービス実行ログの記録に失敗しました: ユーザーID={user_id}")
                return False
                
        except Exception as e:
            logger.error(f"課金サービス実行ログ記録エラー: {e}")
            return False
    
    def _get_security_severity(self, error_type: str) -> str:
        """
        セキュリティエラータイプから危険度を判定
        
        Args:
            error_type: エラータイプ
            
        Returns:
            str: 危険度 ("low", "medium", "high")
        """
        high_severity_types = [
            "sql_injection",
            "xss_attack", 
            "brute_force_attack",
            "brute_force_token_attack",
            "security_threshold_exceeded",
            "account_takeover_attempt",
            "credential_stuffing",
            "suspicious_login_pattern"
        ]
        
        medium_severity_types = [
            "csrf_validation_failed",
            "invalid_websocket_token",
            "websocket_auth_failed",
            "token_verification_error",
            "rate_limit_exceeded",
            "invalid_token",
            "expired_session",
            "unauthorized_endpoint_access"
        ]
        
        if error_type in high_severity_types:
            return "high"
        elif error_type in medium_severity_types:
            return "medium"
        else:
            return "low"

    def _get_access_severity(self, access_type: str) -> str:
        """
        アクセスタイプから危険度を判定
        
        Args:
            access_type: アクセスタイプ
            
        Returns:
            str: 危険度 ("low", "medium", "high")
        """
        high_severity_types = [
            "privilege_escalation",
            "admin_endpoint_access",
            "data_exfiltration_attempt",
            "unauthorized_api_access"
        ]
        
        medium_severity_types = [
            "invalid_token",
            "expired_session",
            "unauthorized_endpoint",
            "cross_origin_request",
            "suspicious_user_agent"
        ]
        
        if access_type in high_severity_types:
            return "high"
        elif access_type in medium_severity_types:
            return "medium"
        else:
            return "low"
    
    async def log_cognito_operation(
        self,
        email: str,
        operation: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognito操作ログを記録
        
        Args:
            email: メールアドレス
            operation: 操作タイプ ("register", "login", "logout", "password_reset", etc.)
            result: 結果 ("success", "failure", "error")
            details: 詳細情報
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            # 操作タイプを詳細に含める
            details_with_operation = {
                **details,
                "operation": operation,
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_operation",
                result=result,
                details=details_with_operation,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"Cognito操作ログを記録しました: "
                    f"メールアドレス={email}, 操作={operation}, 結果={result}, "
                    f"詳細={json.dumps(details, ensure_ascii=False)}"
                )
                return True
            else:
                logger.error(f"Cognito操作ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognito操作ログ記録エラー: {e}")
            return False

    async def log_cognito_user_registration(
        self,
        email: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoユーザー登録ログを記録
        
        Args:
            email: メールアドレス
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（氏名、電話番号、エラー理由など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_registration = {
                **details,
                "operation": "user_registration",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_user_registration",
                result=result,
                details=details_with_registration,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"Cognitoユーザー登録ログを記録しました: "
                    f"メールアドレス={email}, 結果={result}, "
                    f"ユーザーID={user_id}"
                )
                
                # CloudWatch Logsに送信（ユーザー登録は重要なイベント）
                await self._send_to_cloudwatch({
                    "event_type": "cognito_user_registration",
                    "user_id": user_id,
                    "email": email,
                    "result": result,
                    "details": details,
                    "ip_address": ip_address,
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "normal"
                })
                
                return True
            else:
                logger.error(f"Cognitoユーザー登録ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoユーザー登録ログ記録エラー: {e}")
            return False

    async def log_cognito_user_login(
        self,
        email: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoユーザーログインログを記録
        
        Args:
            email: メールアドレス
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（セッションID、失敗理由など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_login = {
                **details,
                "operation": "user_login",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_user_login",
                result=result,
                details=details_with_login,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                if result == "success":
                    logger.info(
                        f"Cognitoユーザーログイン成功ログを記録しました: "
                        f"メールアドレス={email}, ユーザーID={user_id}, "
                        f"セッションID={details.get('session_id', 'N/A')}"
                    )
                else:
                    logger.warning(
                        f"Cognitoユーザーログイン失敗ログを記録しました: "
                        f"メールアドレス={email}, 理由={details.get('error', 'N/A')}"
                    )
                return True
            else:
                logger.error(f"Cognitoユーザーログインログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoユーザーログインログ記録エラー: {e}")
            return False

    async def log_cognito_user_logout(
        self,
        email: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoユーザーログアウトログを記録
        
        Args:
            email: メールアドレス
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（セッションID、ログアウト理由など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_logout = {
                **details,
                "operation": "user_logout",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_user_logout",
                result=result,
                details=details_with_logout,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"Cognitoユーザーログアウトログを記録しました: "
                    f"メールアドレス={email}, ユーザーID={user_id}, "
                    f"セッションID={details.get('session_id', 'N/A')}"
                )
                return True
            else:
                logger.error(f"Cognitoユーザーログアウトログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoユーザーログアウトログ記録エラー: {e}")
            return False

    async def log_cognito_authentication_failure(
        self,
        email: str,
        failure_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognito認証失敗ログを記録
        
        Args:
            email: メールアドレス
            failure_type: 失敗タイプ ("invalid_credentials", "account_locked", "rate_limit_exceeded", etc.)
            details: 詳細情報（失敗理由、試行回数など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_failure = {
                **details,
                "failure_type": failure_type,
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_authentication_failure",
                result="failure",
                details=details_with_failure,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                # 失敗タイプに応じてログレベルを調整
                if failure_type in ["account_locked", "rate_limit_exceeded", "brute_force_detected"]:
                    logger.warning(
                        f"【セキュリティ警告】Cognito認証失敗ログを記録しました: "
                        f"メールアドレス={email}, 失敗タイプ={failure_type}, "
                        f"IPアドレス={ip_address}"
                    )
                else:
                    logger.info(
                        f"Cognito認証失敗ログを記録しました: "
                        f"メールアドレス={email}, 失敗タイプ={failure_type}"
                    )
                return True
            else:
                logger.error(f"Cognito認証失敗ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognito認証失敗ログ記録エラー: {e}")
            return False

    async def log_cognito_password_reset(
        self,
        email: str,
        operation: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoパスワードリセット操作ログを記録
        
        Args:
            email: メールアドレス
            operation: 操作タイプ ("request", "confirm")
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（リセット理由、コード送信先など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_reset = {
                **details,
                "operation": f"password_reset_{operation}",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_password_reset",
                result=result,
                details=details_with_reset,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"Cognitoパスワードリセットログを記録しました: "
                    f"メールアドレス={email}, 操作={operation}, 結果={result}"
                )
                return True
            else:
                logger.error(f"Cognitoパスワードリセットログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoパスワードリセットログ記録エラー: {e}")
            return False

    async def log_cognito_session_operation(
        self,
        email: str,
        operation: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognitoセッション操作ログを記録
        
        Args:
            email: メールアドレス
            operation: 操作タイプ ("created", "refreshed", "invalidated", "expired")
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（セッションID、有効期限など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_session = {
                **details,
                "operation": f"session_{operation}",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_session_operation",
                result=result,
                details=details_with_session,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                logger.info(
                    f"Cognitoセッション操作ログを記録しました: "
                    f"メールアドレス={email}, 操作={operation}, 結果={result}, "
                    f"セッションID={details.get('session_id', 'N/A')}"
                )
                return True
            else:
                logger.error(f"Cognitoセッション操作ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognitoセッション操作ログ記録エラー: {e}")
            return False

    async def log_cognito_sms_verification(
        self,
        email: str,
        operation: str,
        result: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Cognito SMS認証ログを記録
        
        Args:
            email: メールアドレス
            operation: 操作タイプ ("code_sent", "code_verified", "code_resend", "code_expired", etc.)
            result: 結果 ("success", "failure", "error")
            details: 詳細情報（セッションID、認証コード情報など）
            user_id: ユーザーID（オプション）
            ip_address: IPアドレス（オプション）
        
        Returns:
            bool: ログ記録の成功/失敗
        """
        try:
            details_with_sms = {
                **details,
                "operation": f"sms_{operation}",
                "cognito_service": True,
                "processed_at": datetime.utcnow().isoformat()
            }
            
            log_data = AuthLogCreate(
                user_id=user_id,
                email=email,
                event_type="cognito_sms_verification",
                result=result,
                details=details_with_sms,
                ip_address=ip_address
            )
            
            log = await self.db.create_auth_log(log_data)
            
            if log:
                if operation == "code_sent" and result == "success":
                    logger.info(
                        f"Cognito SMS認証コード送信ログを記録しました: "
                        f"メールアドレス={email}, 操作={operation}, 結果={result}"
                    )
                elif operation == "code_verified" and result == "success":
                    logger.info(
                        f"Cognito SMS認証コード検証成功ログを記録しました: "
                        f"メールアドレス={email}, ユーザーID={user_id}"
                    )
                elif result == "failure":
                    logger.warning(
                        f"Cognito SMS認証失敗ログを記録しました: "
                        f"メールアドレス={email}, 操作={operation}, "
                        f"エラー={details.get('error', 'N/A')}"
                    )
                else:
                    logger.info(
                        f"Cognito SMS認証ログを記録しました: "
                        f"メールアドレス={email}, 操作={operation}, 結果={result}"
                    )
                return True
            else:
                logger.error(f"Cognito SMS認証ログの記録に失敗しました: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Cognito SMS認証ログ記録エラー: {e}")
            return False


# グローバルなログサービスインスタンス
logging_service = LoggingService()
