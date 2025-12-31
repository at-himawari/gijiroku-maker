"""
セキュリティ監視サービス - 包括的なセキュリティイベント監視とログ記録
CloudWatch Logs統合対応
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from database import db_manager
from logging_service import logging_service
from rate_limiting_service import rate_limiting_service
import asyncio
import json
import os

logger = logging.getLogger(__name__)

# CloudWatch Logs統合設定
ENABLE_CLOUDWATCH_LOGS = os.getenv("ENABLE_CLOUDWATCH_LOGS", "false").lower() == "true"
CLOUDWATCH_SECURITY_LOG_GROUP = os.getenv("CLOUDWATCH_SECURITY_LOG_GROUP", "/aws/application/gijiroku-maker/security")
CLOUDWATCH_SECURITY_LOG_STREAM = os.getenv("CLOUDWATCH_SECURITY_LOG_STREAM", "security-monitoring")


class SecurityMonitoringService:
    """セキュリティ監視サービスクラス"""
    
    def __init__(self):
        """セキュリティ監視サービスを初期化"""
        self.db = db_manager
        
        # セキュリティイベントのメモリキャッシュ
        self.security_events_cache = {}
        self.suspicious_patterns_cache = {}
        
        # セキュリティ閾値設定
        self.security_thresholds = {
            'brute_force_attempts': 10,  # 15分間での失敗試行回数
            'brute_force_window_minutes': 15,
            'suspicious_login_count': 5,  # 1時間での異常ログイン回数
            'suspicious_login_window_minutes': 60,
            'ip_ban_threshold': 50,  # 1時間でのIP制限閾値
            'ip_ban_window_minutes': 60,
            'account_lockout_threshold': 5,  # アカウントロック閾値
            'account_lockout_window_minutes': 30
        }
        
        # CloudWatch Logs クライアントの初期化（オプション）
        self.cloudwatch_client = None
        if ENABLE_CLOUDWATCH_LOGS:
            try:
                import boto3
                self.cloudwatch_client = boto3.client('logs')
                logger.info("セキュリティ監視用CloudWatch Logs統合が有効化されました")
            except ImportError:
                logger.warning("boto3がインストールされていません。セキュリティ監視CloudWatch Logs統合は無効です")
            except Exception as e:
                logger.error(f"セキュリティ監視CloudWatch Logs初期化エラー: {e}")
    
    async def _send_security_alert_to_cloudwatch(self, alert_data: Dict[str, Any]) -> bool:
        """
        セキュリティアラートをCloudWatch Logsに送信
        
        Args:
            alert_data: アラートデータ
            
        Returns:
            bool: 送信成功/失敗
        """
        if not self.cloudwatch_client or not ENABLE_CLOUDWATCH_LOGS:
            return False
        
        try:
            # アラートメッセージを構築
            alert_message = json.dumps({
                **alert_data,
                "alert_timestamp": datetime.utcnow().isoformat(),
                "service": "security_monitoring"
            }, ensure_ascii=False, default=str)
            
            # CloudWatch Logsに送信
            response = self.cloudwatch_client.put_log_events(
                logGroupName=CLOUDWATCH_SECURITY_LOG_GROUP,
                logStreamName=CLOUDWATCH_SECURITY_LOG_STREAM,
                logEvents=[
                    {
                        'timestamp': int(datetime.utcnow().timestamp() * 1000),
                        'message': alert_message
                    }
                ]
            )
            
            logger.debug(f"セキュリティアラートをCloudWatch Logsに送信成功: {response.get('nextSequenceToken', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"セキュリティアラートCloudWatch Logs送信エラー: {e}")
            return False
    
    async def monitor_cognito_authentication_failure(
        self,
        email: str,
        failure_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cognito認証失敗を監視し、セキュリティ脅威を検出
        
        Args:
            email: メールアドレス
            failure_type: 失敗タイプ
            details: 詳細情報
            user_id: ユーザーID
            ip_address: IPアドレス
            
        Returns:
            Dict: 監視結果
        """
        try:
            current_time = datetime.utcnow()
            
            # 認証失敗ログを記録
            await logging_service.log_cognito_authentication_failure(
                email, failure_type, details, user_id, ip_address
            )
            
            # ブルートフォース攻撃の検出
            brute_force_result = await self._detect_brute_force_attack(
                email, ip_address, current_time
            )
            
            # 疑わしいIPアドレスパターンの検出
            if ip_address:
                ip_pattern_result = await self._detect_suspicious_ip_patterns(
                    ip_address, email, current_time
                )
            
            # アカウントロック状態の監視
            account_lock_result = await self._monitor_account_lockout(
                email, user_id, current_time
            )
            
            return {
                'success': True,
                'brute_force_detected': brute_force_result.get('detected', False),
                'suspicious_ip_detected': ip_pattern_result.get('detected', False) if ip_address else False,
                'account_lockout_risk': account_lock_result.get('risk_level', 'low'),
                'monitoring_timestamp': current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cognito認証失敗監視エラー: {e}")
            return {
                'success': False,
                'error': str(e),
                'monitoring_timestamp': datetime.utcnow().isoformat()
            }
    
    async def _detect_brute_force_attack(
        self,
        email: str,
        ip_address: Optional[str],
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        ブルートフォース攻撃を検出
        
        Args:
            email: メールアドレス
            ip_address: IPアドレス
            current_time: 現在時刻
            
        Returns:
            Dict: 検出結果
        """
        try:
            window_start = current_time - timedelta(
                minutes=self.security_thresholds['brute_force_window_minutes']
            )
            
            # メールアドレスベースの攻撃検出
            email_key = f"auth_fail_{email}"
            if email_key not in self.security_events_cache:
                self.security_events_cache[email_key] = []
            
            # 古いエントリをクリーンアップ
            self.security_events_cache[email_key] = [
                event_time for event_time in self.security_events_cache[email_key]
                if event_time > window_start
            ]
            
            # 新しい失敗を記録
            self.security_events_cache[email_key].append(current_time)
            
            failure_count = len(self.security_events_cache[email_key])
            
            if failure_count >= self.security_thresholds['brute_force_attempts']:
                # ブルートフォース攻撃を検出
                attack_data = {
                    "attack_type": "email_based_brute_force",
                    "attempt_count": failure_count,
                    "time_window_minutes": self.security_thresholds['brute_force_window_minutes'],
                    "first_attempt": min(self.security_events_cache[email_key]).isoformat(),
                    "latest_attempt": max(self.security_events_cache[email_key]).isoformat(),
                    "detection_timestamp": current_time.isoformat()
                }
                
                await logging_service.log_cognito_brute_force_attack(
                    email, attack_data, None, ip_address
                )
                
                # CloudWatch Logsにセキュリティアラートを送信
                await self._send_security_alert_to_cloudwatch({
                    "alert_type": "brute_force_attack_detected",
                    "severity": "high",
                    "target_email": email,
                    "source_ip": ip_address,
                    "attack_details": attack_data
                })
                
                logger.error(
                    f"ブルートフォース攻撃検出: {email} - "
                    f"{failure_count}回の失敗試行 ({self.security_thresholds['brute_force_window_minutes']}分間)"
                )
                
                return {
                    'detected': True,
                    'attack_type': 'email_based_brute_force',
                    'failure_count': failure_count,
                    'threshold': self.security_thresholds['brute_force_attempts']
                }
            
            return {
                'detected': False,
                'failure_count': failure_count,
                'threshold': self.security_thresholds['brute_force_attempts']
            }
            
        except Exception as e:
            logger.error(f"ブルートフォース攻撃検出エラー: {e}")
            return {'detected': False, 'error': str(e)}
    
    async def _detect_suspicious_ip_patterns(
        self,
        ip_address: str,
        email: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        疑わしいIPアドレスパターンを検出
        
        Args:
            ip_address: IPアドレス
            email: メールアドレス
            current_time: 現在時刻
            
        Returns:
            Dict: 検出結果
        """
        try:
            window_start = current_time - timedelta(
                minutes=self.security_thresholds['ip_ban_window_minutes']
            )
            
            # IPアドレスベースの攻撃検出
            ip_key = f"ip_activity_{ip_address}"
            if ip_key not in self.security_events_cache:
                self.security_events_cache[ip_key] = []
            
            # 古いエントリをクリーンアップ
            self.security_events_cache[ip_key] = [
                event for event in self.security_events_cache[ip_key]
                if event['timestamp'] > window_start
            ]
            
            # 新しいイベントを記録
            self.security_events_cache[ip_key].append({
                'timestamp': current_time,
                'email': email,
                'event_type': 'auth_failure'
            })
            
            # 複数アカウントへの攻撃を検出
            unique_emails = set(event['email'] for event in self.security_events_cache[ip_key])
            total_attempts = len(self.security_events_cache[ip_key])
            
            if len(unique_emails) >= 5 and total_attempts >= 20:
                # 複数アカウント攻撃を検出
                attack_data = {
                    "ip_address": ip_address,
                    "target_accounts": len(unique_emails),
                    "total_attempts": total_attempts,
                    "time_window_minutes": self.security_thresholds['ip_ban_window_minutes'],
                    "attack_pattern": "multiple_account_targeting",
                    "targeted_emails": list(unique_emails)[:10],  # 最初の10件のみ
                    "detection_timestamp": current_time.isoformat()
                }
                
                await logging_service.log_cognito_security_error(
                    "multiple_accounts", "credential_stuffing_attack",
                    attack_data, None, ip_address
                )
                
                # CloudWatch Logsにセキュリティアラートを送信
                await self._send_security_alert_to_cloudwatch({
                    "alert_type": "credential_stuffing_attack_detected",
                    "severity": "critical",
                    "source_ip": ip_address,
                    "target_accounts_count": len(unique_emails),
                    "attack_details": attack_data
                })
                
                logger.error(
                    f"クレデンシャルスタッフィング攻撃検出: IP {ip_address} - "
                    f"{len(unique_emails)}アカウント、{total_attempts}回の試行"
                )
                
                return {
                    'detected': True,
                    'attack_type': 'credential_stuffing',
                    'target_accounts': len(unique_emails),
                    'total_attempts': total_attempts
                }
            
            return {
                'detected': False,
                'target_accounts': len(unique_emails),
                'total_attempts': total_attempts
            }
            
        except Exception as e:
            logger.error(f"疑わしいIPパターン検出エラー: {e}")
            return {'detected': False, 'error': str(e)}
    
    async def _monitor_account_lockout(
        self,
        email: str,
        user_id: Optional[str],
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        アカウントロック状態を監視
        
        Args:
            email: メールアドレス
            user_id: ユーザーID
            current_time: 現在時刻
            
        Returns:
            Dict: 監視結果
        """
        try:
            window_start = current_time - timedelta(
                minutes=self.security_thresholds['account_lockout_window_minutes']
            )
            
            # アカウント固有の失敗試行を監視
            account_key = f"account_fail_{email}"
            if account_key not in self.security_events_cache:
                self.security_events_cache[account_key] = []
            
            # 古いエントリをクリーンアップ
            self.security_events_cache[account_key] = [
                event_time for event_time in self.security_events_cache[account_key]
                if event_time > window_start
            ]
            
            # 新しい失敗を記録
            self.security_events_cache[account_key].append(current_time)
            
            failure_count = len(self.security_events_cache[account_key])
            threshold = self.security_thresholds['account_lockout_threshold']
            
            # リスクレベルを判定
            if failure_count >= threshold:
                risk_level = 'high'
                
                # アカウントロック警告ログ
                await logging_service.log_cognito_security_error(
                    email, "account_lockout_risk",
                    {
                        "failure_count": failure_count,
                        "threshold": threshold,
                        "time_window_minutes": self.security_thresholds['account_lockout_window_minutes'],
                        "risk_level": risk_level,
                        "user_id": user_id,
                        "detection_timestamp": current_time.isoformat()
                    },
                    user_id
                )
                
            elif failure_count >= threshold * 0.8:  # 80%に達した場合
                risk_level = 'medium'
            else:
                risk_level = 'low'
            
            return {
                'risk_level': risk_level,
                'failure_count': failure_count,
                'threshold': threshold,
                'lockout_imminent': failure_count >= threshold
            }
            
        except Exception as e:
            logger.error(f"アカウントロック監視エラー: {e}")
            return {'risk_level': 'unknown', 'error': str(e)}
    
    async def monitor_billing_service_execution(
        self,
        user_id: str,
        user_identifier: str,
        service_name: str,
        amount: float,
        result: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        課金サービス実行を監視し、異常なパターンを検出
        
        Args:
            user_id: ユーザーID
            user_identifier: ユーザー識別子
            service_name: サービス名
            amount: 課金金額
            result: 実行結果
            details: 詳細情報
            ip_address: IPアドレス
            
        Returns:
            Dict: 監視結果
        """
        try:
            current_time = datetime.utcnow()
            
            # 課金サービス実行ログを記録
            await logging_service.log_billing_service_execution(
                user_id, user_identifier, service_name, amount, result, details, ip_address
            )
            
            # 異常な課金パターンを検出
            billing_pattern_result = await self._detect_abnormal_billing_patterns(
                user_id, service_name, amount, current_time
            )
            
            # 高額課金の監視
            high_amount_result = await self._monitor_high_amount_billing(
                user_id, user_identifier, amount, current_time
            )
            
            return {
                'success': True,
                'abnormal_pattern_detected': billing_pattern_result.get('detected', False),
                'high_amount_alert': high_amount_result.get('alert', False),
                'monitoring_timestamp': current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"課金サービス監視エラー: {e}")
            return {
                'success': False,
                'error': str(e),
                'monitoring_timestamp': datetime.utcnow().isoformat()
            }
    
    async def _detect_abnormal_billing_patterns(
        self,
        user_id: str,
        service_name: str,
        amount: float,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        異常な課金パターンを検出
        
        Args:
            user_id: ユーザーID
            service_name: サービス名
            amount: 課金金額
            current_time: 現在時刻
            
        Returns:
            Dict: 検出結果
        """
        try:
            window_start = current_time - timedelta(hours=1)  # 1時間の窓
            
            # ユーザーの課金履歴を監視
            billing_key = f"billing_{user_id}_{service_name}"
            if billing_key not in self.security_events_cache:
                self.security_events_cache[billing_key] = []
            
            # 古いエントリをクリーンアップ
            self.security_events_cache[billing_key] = [
                event for event in self.security_events_cache[billing_key]
                if event['timestamp'] > window_start
            ]
            
            # 新しい課金イベントを記録
            self.security_events_cache[billing_key].append({
                'timestamp': current_time,
                'amount': amount,
                'service_name': service_name
            })
            
            # 異常パターンの検出
            recent_events = self.security_events_cache[billing_key]
            
            # 1時間に10回以上の課金実行
            if len(recent_events) >= 10:
                total_amount = sum(event['amount'] for event in recent_events)
                
                billing_alert_data = {
                    "user_id": user_id,
                    "service_name": service_name,
                    "billing_count": len(recent_events),
                    "total_amount": total_amount,
                    "time_window": "1_hour",
                    "pattern_type": "high_frequency_billing",
                    "detection_timestamp": current_time.isoformat()
                }
                
                await logging_service.log_security_error(
                    user_id, "abnormal_billing_pattern", billing_alert_data, user_id
                )
                
                # CloudWatch Logsにセキュリティアラートを送信
                await self._send_security_alert_to_cloudwatch({
                    "alert_type": "abnormal_billing_pattern_detected",
                    "severity": "high",
                    "user_id": user_id,
                    "service_name": service_name,
                    "billing_details": billing_alert_data
                })
                
                logger.warning(
                    f"異常な課金パターン検出: ユーザー {user_id} - "
                    f"1時間に{len(recent_events)}回の{service_name}課金"
                )
                
                return {
                    'detected': True,
                    'pattern_type': 'high_frequency_billing',
                    'billing_count': len(recent_events),
                    'total_amount': total_amount
                }
            
            return {
                'detected': False,
                'billing_count': len(recent_events)
            }
            
        except Exception as e:
            logger.error(f"異常課金パターン検出エラー: {e}")
            return {'detected': False, 'error': str(e)}
    
    async def _monitor_high_amount_billing(
        self,
        user_id: str,
        user_identifier: str,
        amount: float,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        高額課金を監視
        
        Args:
            user_id: ユーザーID
            user_identifier: ユーザー識別子
            amount: 課金金額
            current_time: 現在時刻
            
        Returns:
            Dict: 監視結果
        """
        try:
            # 高額課金の閾値（例：1000円以上）
            high_amount_threshold = 1000.0
            
            if amount >= high_amount_threshold:
                # 高額課金アラートログ
                high_amount_alert_data = {
                    "user_id": user_id,
                    "user_identifier": user_identifier,
                    "amount": amount,
                    "threshold": high_amount_threshold,
                    "alert_level": "high" if amount >= high_amount_threshold * 2 else "medium",
                    "detection_timestamp": current_time.isoformat()
                }
                
                await logging_service.log_security_error(
                    user_identifier, "high_amount_billing_alert", high_amount_alert_data, user_id
                )
                
                # CloudWatch Logsにセキュリティアラートを送信
                await self._send_security_alert_to_cloudwatch({
                    "alert_type": "high_amount_billing_detected",
                    "severity": "high" if amount >= high_amount_threshold * 2 else "medium",
                    "user_id": user_id,
                    "user_identifier": user_identifier,
                    "billing_details": high_amount_alert_data
                })
                
                logger.warning(
                    f"高額課金アラート: ユーザー {user_id} ({user_identifier}) - "
                    f"課金金額: {amount}円"
                )
                
                return {
                    'alert': True,
                    'amount': amount,
                    'threshold': high_amount_threshold,
                    'alert_level': 'high' if amount >= high_amount_threshold * 2 else 'medium'
                }
            
            return {
                'alert': False,
                'amount': amount,
                'threshold': high_amount_threshold
            }
            
        except Exception as e:
            logger.error(f"高額課金監視エラー: {e}")
            return {'alert': False, 'error': str(e)}
    
    async def monitor_unauthorized_access_attempt(
        self,
        email: str,
        access_type: str,
        endpoint: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        不正アクセス試行を監視
        
        Args:
            email: メールアドレス
            access_type: アクセスタイプ
            endpoint: エンドポイント
            details: 詳細情報
            user_id: ユーザーID
            ip_address: IPアドレス
            
        Returns:
            Dict: 監視結果
        """
        try:
            current_time = datetime.utcnow()
            
            # 不正アクセス試行ログを記録
            await logging_service.log_cognito_unauthorized_access(
                email, access_type, 
                {**details, "endpoint": endpoint, "timestamp": current_time.isoformat()},
                user_id, ip_address
            )
            
            # 不正アクセスパターンを検出
            unauthorized_pattern_result = await self._detect_unauthorized_access_patterns(
                email, ip_address, access_type, current_time
            )
            
            return {
                'success': True,
                'pattern_detected': unauthorized_pattern_result.get('detected', False),
                'monitoring_timestamp': current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"不正アクセス監視エラー: {e}")
            return {
                'success': False,
                'error': str(e),
                'monitoring_timestamp': datetime.utcnow().isoformat()
            }
    
    async def _detect_unauthorized_access_patterns(
        self,
        email: str,
        ip_address: Optional[str],
        access_type: str,
        current_time: datetime
    ) -> Dict[str, Any]:
        """
        不正アクセスパターンを検出
        
        Args:
            email: メールアドレス
            ip_address: IPアドレス
            access_type: アクセスタイプ
            current_time: 現在時刻
            
        Returns:
            Dict: 検出結果
        """
        try:
            window_start = current_time - timedelta(minutes=30)  # 30分の窓
            
            # 不正アクセス試行を監視
            access_key = f"unauthorized_{email}_{ip_address}"
            if access_key not in self.security_events_cache:
                self.security_events_cache[access_key] = []
            
            # 古いエントリをクリーンアップ
            self.security_events_cache[access_key] = [
                event for event in self.security_events_cache[access_key]
                if event['timestamp'] > window_start
            ]
            
            # 新しい不正アクセス試行を記録
            self.security_events_cache[access_key].append({
                'timestamp': current_time,
                'access_type': access_type
            })
            
            access_count = len(self.security_events_cache[access_key])
            
            # 30分間に5回以上の不正アクセス試行
            if access_count >= 5:
                await logging_service.log_cognito_security_error(
                    email, "repeated_unauthorized_access",
                    {
                        "email": email,
                        "ip_address": ip_address,
                        "access_count": access_count,
                        "time_window_minutes": 30,
                        "access_types": [event['access_type'] for event in self.security_events_cache[access_key]],
                        "detection_timestamp": current_time.isoformat()
                    },
                    None, ip_address
                )
                
                logger.warning(
                    f"繰り返し不正アクセス検出: {email} (IP: {ip_address}) - "
                    f"30分間に{access_count}回の試行"
                )
                
                return {
                    'detected': True,
                    'access_count': access_count,
                    'pattern_type': 'repeated_unauthorized_access'
                }
            
            return {
                'detected': False,
                'access_count': access_count
            }
            
        except Exception as e:
            logger.error(f"不正アクセスパターン検出エラー: {e}")
            return {'detected': False, 'error': str(e)}
    
    async def get_security_summary(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        セキュリティサマリーを取得
        
        Args:
            time_window_hours: 時間窓（時間）
            
        Returns:
            Dict: セキュリティサマリー
        """
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(hours=time_window_hours)
            
            summary = {
                'time_window_hours': time_window_hours,
                'summary_generated_at': current_time.isoformat(),
                'security_events': {
                    'brute_force_attacks': 0,
                    'credential_stuffing_attacks': 0,
                    'unauthorized_access_attempts': 0,
                    'high_amount_billing_alerts': 0,
                    'abnormal_billing_patterns': 0
                },
                'active_threats': [],
                'recommendations': []
            }
            
            # キャッシュからセキュリティイベントを集計
            for cache_key, events in self.security_events_cache.items():
                if isinstance(events, list):
                    recent_events = [
                        event for event in events
                        if (isinstance(event, datetime) and event > window_start) or
                           (isinstance(event, dict) and event.get('timestamp', datetime.min) > window_start)
                    ]
                    
                    if recent_events:
                        if 'auth_fail_' in cache_key:
                            summary['security_events']['brute_force_attacks'] += len(recent_events)
                        elif 'ip_activity_' in cache_key:
                            summary['security_events']['credential_stuffing_attacks'] += len(recent_events)
                        elif 'unauthorized_' in cache_key:
                            summary['security_events']['unauthorized_access_attempts'] += len(recent_events)
                        elif 'billing_' in cache_key:
                            summary['security_events']['abnormal_billing_patterns'] += len(recent_events)
            
            # 推奨事項を生成
            if summary['security_events']['brute_force_attacks'] > 10:
                summary['recommendations'].append(
                    "ブルートフォース攻撃が多発しています。レート制限の強化を検討してください。"
                )
            
            if summary['security_events']['credential_stuffing_attacks'] > 5:
                summary['recommendations'].append(
                    "クレデンシャルスタッフィング攻撃が検出されています。IP制限の強化を検討してください。"
                )
            
            if summary['security_events']['unauthorized_access_attempts'] > 20:
                summary['recommendations'].append(
                    "不正アクセス試行が多発しています。認証システムの見直しを検討してください。"
                )
            
            return summary
            
        except Exception as e:
            logger.error(f"セキュリティサマリー取得エラー: {e}")
            return {
                'error': str(e),
                'summary_generated_at': datetime.utcnow().isoformat()
            }
    
    async def cleanup_security_cache(self):
        """
        セキュリティキャッシュをクリーンアップ
        """
        try:
            current_time = datetime.utcnow()
            cutoff_time = current_time - timedelta(hours=24)  # 24時間より古いデータを削除
            
            for cache_key in list(self.security_events_cache.keys()):
                events = self.security_events_cache[cache_key]
                
                if isinstance(events, list):
                    # イベントリストをクリーンアップ
                    cleaned_events = []
                    for event in events:
                        if isinstance(event, datetime):
                            if event > cutoff_time:
                                cleaned_events.append(event)
                        elif isinstance(event, dict) and 'timestamp' in event:
                            if event['timestamp'] > cutoff_time:
                                cleaned_events.append(event)
                    
                    if cleaned_events:
                        self.security_events_cache[cache_key] = cleaned_events
                    else:
                        del self.security_events_cache[cache_key]
            
            logger.info("セキュリティキャッシュのクリーンアップが完了しました")
            
        except Exception as e:
            logger.error(f"セキュリティキャッシュクリーンアップエラー: {e}")


# グローバルインスタンス
security_monitoring_service = SecurityMonitoringService()