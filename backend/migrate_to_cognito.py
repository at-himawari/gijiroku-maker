#!/usr/bin/env python3
"""
既存の電話番号認証ユーザーをCognitoメールアドレス+パスワード認証に移行するスクリプト

このスクリプトは以下の処理を行います:
1. 既存の電話番号認証ユーザーの一覧を取得
2. 各ユーザーに対してCognitoアカウント作成の案内を表示
3. 管理者が手動でCognitoアカウントを作成した後、データの整合性を確保
4. 移行完了後の旧システム無効化
5. 移行ログの記録

注意: このスクリプトは段階的な移行をサポートし、ユーザーの同意を得てから実行してください。
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import json

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import db_manager
from cognito_service import CognitoService
from logging_service import logging_service
from models import User

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cognito_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CognitoMigrationService:
    """Cognito移行サービス"""
    
    def __init__(self):
        self.cognito_service = CognitoService()
        self.migration_log = []
    
    async def get_existing_phone_users(self) -> List[User]:
        """既存の電話番号認証ユーザーを取得"""
        try:
            query = """
            SELECT user_id, phone_number, created_at, last_login, is_active
            FROM users 
            WHERE phone_number IS NOT NULL 
            AND is_active = TRUE
            ORDER BY created_at ASC
            """
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query)
                    rows = await cursor.fetchall()
                    
                    users = []
                    for row in rows:
                        user = User(
                            user_id=row[0],
                            phone_number=row[1],
                            created_at=row[2],
                            last_login=row[3],
                            is_active=row[4]
                        )
                        users.append(user)
                    
                    return users
                    
        except Exception as e:
            logger.error(f"既存ユーザー取得エラー: {e}")
            return []
    
    async def check_cognito_user_exists(self, email: str) -> bool:
        """Cognitoにユーザーが既に存在するかチェック"""
        try:
            # Cognitoサービスを使用してユーザーの存在確認
            # 実際の実装では、CognitoのAdminGetUserを使用
            import boto3
            from botocore.exceptions import ClientError
            
            cognito_client = boto3.client('cognito-idp')
            user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
            
            try:
                response = cognito_client.admin_get_user(
                    UserPoolId=user_pool_id,
                    Username=email
                )
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'UserNotFoundException':
                    return False
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"Cognitoユーザー存在確認エラー: {e}")
            return False
    
    async def create_cognito_user_mapping(self, phone_user: User, cognito_username: str) -> bool:
        """電話番号ユーザーとCognitoユーザーのマッピングを作成"""
        try:
            # 新しいusersテーブルにCognitoユーザー情報を追加
            query = """
            INSERT INTO users (user_id, cognito_username, created_at, updated_at, is_active)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            cognito_username = VALUES(cognito_username),
            updated_at = VALUES(updated_at)
            """
            
            now = datetime.utcnow()
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (
                        phone_user.user_id,  # 既存のuser_idを保持
                        cognito_username,
                        now,
                        now,
                        True
                    ))
                    await conn.commit()
            
            # 移行ログを記録
            migration_entry = {
                'timestamp': now.isoformat(),
                'action': 'user_mapping_created',
                'phone_user_id': phone_user.user_id,
                'phone_number': phone_user.phone_number,
                'cognito_username': cognito_username,
                'status': 'success'
            }
            self.migration_log.append(migration_entry)
            
            # データベースにも移行ログを記録
            await logging_service.log_auth_attempt(
                phone_user.phone_number,
                "migration_success",
                {
                    "action": "cognito_mapping_created",
                    "cognito_username": cognito_username,
                    "migration_timestamp": now.isoformat()
                },
                phone_user.user_id
            )
            
            logger.info(f"ユーザーマッピング作成成功: {phone_user.phone_number} -> {cognito_username}")
            return True
            
        except Exception as e:
            logger.error(f"ユーザーマッピング作成エラー: {e}")
            
            # エラーログを記録
            error_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'user_mapping_failed',
                'phone_user_id': phone_user.user_id,
                'phone_number': phone_user.phone_number,
                'cognito_username': cognito_username,
                'status': 'error',
                'error': str(e)
            }
            self.migration_log.append(error_entry)
            
            return False
    
    async def disable_phone_auth_system(self) -> bool:
        """旧電話番号認証システムを無効化"""
        try:
            logger.info("旧電話番号認証システムの無効化を開始...")
            
            # 電話番号認証関連のエンドポイントを無効化するフラグを設定
            # 実際の実装では、設定ファイルやデータベースフラグを使用
            
            # 移行完了フラグをデータベースに記録
            query = """
            INSERT INTO system_settings (setting_key, setting_value, created_at, updated_at)
            VALUES ('phone_auth_disabled', 'true', %s, %s)
            ON DUPLICATE KEY UPDATE
            setting_value = VALUES(setting_value),
            updated_at = VALUES(updated_at)
            """
            
            now = datetime.utcnow()
            
            async with db_manager.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (now, now))
                    await conn.commit()
            
            # 移行完了ログを記録
            completion_entry = {
                'timestamp': now.isoformat(),
                'action': 'phone_auth_system_disabled',
                'status': 'success'
            }
            self.migration_log.append(completion_entry)
            
            logger.info("旧電話番号認証システムの無効化が完了しました")
            return True
            
        except Exception as e:
            logger.error(f"旧システム無効化エラー: {e}")
            return False
    
    async def save_migration_log(self) -> bool:
        """移行ログをファイルに保存"""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            log_filename = f"cognito_migration_log_{timestamp}.json"
            
            with open(log_filename, 'w', encoding='utf-8') as f:
                json.dump(self.migration_log, f, ensure_ascii=False, indent=2)
            
            logger.info(f"移行ログを保存しました: {log_filename}")
            return True
            
        except Exception as e:
            logger.error(f"移行ログ保存エラー: {e}")
            return False
    
    async def interactive_migration(self):
        """対話式移行プロセス"""
        logger.info("=== Cognito移行プロセスを開始します ===")
        
        # 既存ユーザーを取得
        phone_users = await self.get_existing_phone_users()
        
        if not phone_users:
            logger.info("移行対象の電話番号認証ユーザーが見つかりませんでした。")
            return
        
        logger.info(f"移行対象ユーザー数: {len(phone_users)}")
        
        print("\n移行対象ユーザー一覧:")
        print("-" * 80)
        print(f"{'No.':<4} {'ユーザーID':<20} {'電話番号':<15} {'作成日':<20} {'最終ログイン':<20}")
        print("-" * 80)
        
        for i, user in enumerate(phone_users, 1):
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M:%S") if user.last_login else "未ログイン"
            created_at = user.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{i:<4} {user.user_id:<20} {user.phone_number:<15} {created_at:<20} {last_login:<20}")
        
        print("-" * 80)
        
        # 移行確認
        response = input("\n移行を続行しますか？ (y/N): ").strip().lower()
        if response != 'y':
            logger.info("移行がキャンセルされました。")
            return
        
        # 各ユーザーの移行処理
        migrated_count = 0
        
        for i, user in enumerate(phone_users, 1):
            print(f"\n--- ユーザー {i}/{len(phone_users)}: {user.phone_number} ---")
            
            # Cognitoアカウント情報の入力
            print("このユーザーのCognitoアカウント情報を入力してください:")
            cognito_email = input("Cognitoメールアドレス: ").strip()
            
            if not cognito_email:
                logger.warning(f"ユーザー {user.phone_number} の移行をスキップしました（メールアドレス未入力）")
                continue
            
            # Cognitoユーザーの存在確認
            exists = await self.check_cognito_user_exists(cognito_email)
            if not exists:
                logger.warning(f"Cognitoユーザー {cognito_email} が見つかりません。先にCognitoアカウントを作成してください。")
                continue
            
            # マッピング作成
            success = await self.create_cognito_user_mapping(user, cognito_email)
            if success:
                migrated_count += 1
                logger.info(f"ユーザー {user.phone_number} の移行が完了しました")
            else:
                logger.error(f"ユーザー {user.phone_number} の移行に失敗しました")
        
        logger.info(f"\n移行完了: {migrated_count}/{len(phone_users)} ユーザー")
        
        # 移行ログを保存
        await self.save_migration_log()
        
        # 全ユーザーが移行完了した場合、旧システムの無効化を提案
        if migrated_count == len(phone_users):
            response = input("\n全ユーザーの移行が完了しました。旧電話番号認証システムを無効化しますか？ (y/N): ").strip().lower()
            if response == 'y':
                await self.disable_phone_auth_system()
                logger.info("移行プロセスが完全に完了しました。")
            else:
                logger.info("旧システムは有効のままです。後で手動で無効化してください。")
        else:
            logger.info("一部のユーザーの移行が未完了です。旧システムは有効のままです。")
    
    async def batch_migration_from_csv(self, csv_file_path: str):
        """CSVファイルからの一括移行"""
        try:
            import csv
            
            logger.info(f"CSVファイルからの一括移行を開始: {csv_file_path}")
            
            migrated_count = 0
            
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    phone_number = row.get('phone_number', '').strip()
                    cognito_email = row.get('cognito_email', '').strip()
                    
                    if not phone_number or not cognito_email:
                        logger.warning(f"無効な行をスキップ: {row}")
                        continue
                    
                    # 電話番号ユーザーを検索
                    phone_users = await self.get_existing_phone_users()
                    phone_user = next((u for u in phone_users if u.phone_number == phone_number), None)
                    
                    if not phone_user:
                        logger.warning(f"電話番号ユーザーが見つかりません: {phone_number}")
                        continue
                    
                    # Cognitoユーザーの存在確認
                    exists = await self.check_cognito_user_exists(cognito_email)
                    if not exists:
                        logger.warning(f"Cognitoユーザーが見つかりません: {cognito_email}")
                        continue
                    
                    # マッピング作成
                    success = await self.create_cognito_user_mapping(phone_user, cognito_email)
                    if success:
                        migrated_count += 1
                        logger.info(f"移行完了: {phone_number} -> {cognito_email}")
                    else:
                        logger.error(f"移行失敗: {phone_number} -> {cognito_email}")
            
            logger.info(f"一括移行完了: {migrated_count} ユーザー")
            await self.save_migration_log()
            
        except Exception as e:
            logger.error(f"一括移行エラー: {e}")


async def main():
    """メイン関数"""
    try:
        # データベース接続を初期化
        await db_manager.init_pool()
        
        migration_service = CognitoMigrationService()
        
        # コマンドライン引数をチェック
        if len(sys.argv) > 1:
            if sys.argv[1] == '--csv' and len(sys.argv) > 2:
                # CSVファイルからの一括移行
                csv_file = sys.argv[2]
                await migration_service.batch_migration_from_csv(csv_file)
            else:
                print("使用方法:")
                print("  python migrate_to_cognito.py                # 対話式移行")
                print("  python migrate_to_cognito.py --csv file.csv # CSV一括移行")
                return
        else:
            # 対話式移行
            await migration_service.interactive_migration()
    
    except KeyboardInterrupt:
        logger.info("移行プロセスが中断されました。")
    except Exception as e:
        logger.error(f"移行プロセスエラー: {e}")
    finally:
        # データベース接続を閉じる
        await db_manager.close_pool()


if __name__ == "__main__":
    asyncio.run(main())