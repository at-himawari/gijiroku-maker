"use client";

import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Eye, EyeOff } from "lucide-react";

interface EmailLoginFormProps {
  onSuccess?: () => void;
  onSwitchToRegister?: () => void;
  onForgotPassword?: () => void;
}

/**
 * メールアドレス + パスワード認証用ログインフォーム
 * 要件: 2.1, 7.1, 7.2, 7.3, 7.4, 7.5
 */
export const EmailLoginForm: React.FC<EmailLoginFormProps> = ({
  onSuccess,
  onSwitchToRegister,
  onForgotPassword,
}) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);

  const { cognitoSignIn } = useAuth();
  const router = useRouter();

  // メールアドレスのリアルタイムバリデーション（要件: 7.3）
  const validateEmail = (value: string): string | null => {
    if (!value) return null;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(value)
      ? null
      : "有効なメールアドレスを入力してください";
  };

  const handleEmailChange = (value: string) => {
    setEmail(value);
    const error = validateEmail(value);
    setEmailError(error);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 入力バリデーション（要件: 2.4）
    if (!email.trim()) {
      setError("メールアドレスを入力してください");
      return;
    }

    if (!password.trim()) {
      setError("パスワードを入力してください");
      return;
    }

    // メールアドレス形式チェック
    const emailValidationError = validateEmail(email);
    if (emailValidationError) {
      setError(emailValidationError);
      return;
    }

    setIsLoading(true);

    try {
      // Cognito認証（要件: 2.1）
      const result = await cognitoSignIn(email, password);

      if (result.success) {
        // 認証成功時の処理（要件: 2.5）
        if (onSuccess) {
          onSuccess();
        } else {
          router.push("/");
        }
      } else {
        // エラーメッセージ表示（要件: 2.3, 7.2）
        setError(result.message || "ログインに失敗しました");
      }
    } catch (error) {
      console.error("ログインエラー:", error);
      setError("ログインに失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="email-login-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">ログイン</h2>
        <p className="text-gray-600 mt-2">
          メールアドレスとパスワードでログインしてください
        </p>
      </div>

      {/* エラーメッセージ表示（要件: 7.2） */}
      {error && (
        <Alert variant="destructive" data-testid="error-message">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-4"
        data-testid="login-form"
      >
        {/* メールアドレス入力（要件: 7.1） */}
        <div>
          <Label htmlFor="email">メールアドレス</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => handleEmailChange(e.target.value)}
            placeholder="example@email.com"
            disabled={isLoading}
            data-testid="email-input"
            className={`mt-1 ${emailError ? "border-red-500" : ""}`}
          />
          {/* リアルタイムバリデーション表示（要件: 7.3） */}
          {emailError && (
            <p className="text-sm text-red-500 mt-1" data-testid="email-error">
              {emailError}
            </p>
          )}
        </div>

        {/* パスワード入力（要件: 7.1） */}
        <div>
          <Label htmlFor="password">パスワード</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(null);
              }}
              placeholder="パスワードを入力"
              disabled={isLoading}
              data-testid="password-input"
              className="mt-1 pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700"
              data-testid="password-toggle"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
        </div>

        {/* パスワードを忘れた場合のリンク */}
        {onForgotPassword && (
          <div className="text-right">
            <button
              type="button"
              onClick={onForgotPassword}
              className="text-sm text-blue-600 hover:text-blue-800 underline"
              data-testid="forgot-password-link"
            >
              パスワードを忘れた場合
            </button>
          </div>
        )}

        {/* ローディング状態管理（要件: 7.5） */}
        <Button
          type="submit"
          disabled={isLoading || !email.trim() || !password.trim()}
          className="w-full"
          data-testid="login-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ログイン中...
            </>
          ) : (
            "ログイン"
          )}
        </Button>
      </form>

      {/* 新規登録へのリンク */}
      {onSwitchToRegister && (
        <div className="text-center text-sm text-gray-600">
          アカウントをお持ちでない方は{" "}
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="text-blue-600 hover:text-blue-800 underline"
            data-testid="switch-to-register"
          >
            新規登録
          </button>
        </div>
      )}
    </div>
  );
};
