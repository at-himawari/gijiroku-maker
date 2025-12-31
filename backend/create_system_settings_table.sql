-- システム設定テーブルの作成
-- 移行状態やシステム設定を管理するためのテーブル

CREATE TABLE IF NOT EXISTS system_settings (
    setting_id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_setting_key (setting_key),
    INDEX idx_created_at (created_at)
);

-- 初期設定値を挿入
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('phone_auth_disabled', 'false', '電話番号認証システムの無効化フラグ'),
('cognito_migration_status', 'not_started', 'Cognito移行の進行状況'),
('migration_start_date', '', 'Cognito移行開始日時'),
('migration_completion_date', '', 'Cognito移行完了日時')
ON DUPLICATE KEY UPDATE
setting_value = VALUES(setting_value),
description = VALUES(description),
updated_at = CURRENT_TIMESTAMP;