export interface UserProfile {
  user_id: string;
  cognito_sub: string;
  email: string | null;
  name: string | null;
  subscription_status: 'free' | 'premium'; // バックエンドの定義に合わせる
  usage_count: number;
  monthly_usage_count: number;
  preferences: Record<string, any>;
  profile_data: Record<string, any>;
  created_at: string;
  last_login: string | null;
}

export interface UserProfileResponse {
  success: boolean;
  profile: UserProfile;
  error?: string;
  message?: string;
}