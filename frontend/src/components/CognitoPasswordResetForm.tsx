"use client";

import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Eye, EyeOff, Check, X, ArrowLeft } from "lucide-react";
import Link from "next/link";

interface CognitoPasswordResetFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

interface PasswordStrength {
  hasMinLength: boolean;
  hasUpperCase: boolean;
  hasLowerCase: boolean;
  hasNumber: boolean;
  hasSymbol: boolean;
  score: number;
}

export const CognitoPasswordResetForm: React.FC<
  CognitoPasswordResetFormProps
> = ({ onSuccess, onCancel }) => {
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [email, setEmail] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmPasswordError, setConfirmPasswordError] = useState<
    string | null
  >(null);

  const { cognitoResetPassword, cognitoConfirmResetPassword } = useAuth();

  // パスワード強度チェック
  const checkPasswordStrength = (password: string): PasswordStrength => {
    const hasMinLength = password.length >= 8;
    const hasUpperCase = /[A-Z]/.test(password);
    const hasLowerCase = /[a-z]/.test(password);
    const hasNumber = /\d/.test(password);
    const hasSymbol = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password);

    const score = [
      hasMinLength,
      hasUpperCase,
      hasLowerCase,
      hasNumber,
      hasSymbol,
    ].filter(Boolean).length;

    return {
      hasMinLength,
      hasUpperCase,
      hasLowerCase,
      hasNumber,
      hasSymbol,
      score,
    };
  };

  // メールアドレス検証
  const validateEmail = (email: string): string | null => {
    if (!email) return null;

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return "有効なメールアドレスを入力してください";
    }
    return null;
  };

  // パスワード検証
  const validatePassword = (password: string): string | null => {
    if (!password) return null;

    const strength = checkPasswordStrength(password);
    if (!strength.hasMinLength)
      return "パスワードは8文字以上である必要があります";
    if (!strength.hasUpperCase) return "大文字を含む必要があります";
    if (!strength.hasLowerCase) return "小文字を含む必要があります";
    if (!strength.hasNumber) return "数字を含む必要があります";
    if (!strength.hasSymbol) return "記号を含む必要があります";
    return null;
  };

  // 確認パスワード検証
  const validateConfirmPassword = (confirmPassword: string): string | null => {
    if (!confirmPassword) return null;
    return confirmPassword === newPassword ? null : "パスワードが一致しません";
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEmail = e.target.value;
    setEmail(newEmail);
    setEmailError(validateEmail(newEmail));
    setError(null);
    setSuccess(null);
  };

  const handleNewPasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const password = e.target.value;
    setNewPassword(password);
    setPasswordError(validatePassword(password));

    // 確認パスワードの再検証
    if (confirmPassword) {
      setConfirmPasswordError(validateConfirmPassword(confirmPassword));
    }

    setError(null);
    setSuccess(null);
  };

  const handleConfirmPasswordChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const password = e.target.value;
    setConfirmPassword(password);
    setConfirmPasswordError(validateConfirmPassword(password));
    setError(null);
    setSuccess(null);
  };

  // パスワードリセット要求
  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!email.trim()) {
      setError("メールアドレスを入力してください");
      return;
    }

    const emailValidationError = validateEmail(email);
    if (emailValidationError) {
      setError(emailValidationError);
      return;
    }

    setIsLoading(true);

    try {
      const result = await cognitoResetPassword(email);

      if (result.success) {
        setSuccess(
          result.message || "パスワードリセット用のコードをメールに送信しました"
        );
        setStep("confirm");
      } else {
        setError(result.message || "パスワードリセットに失敗しました");
      }
    } catch (error) {
      console.error("Password reset request error:", error);
      setError("パスワードリセットに失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  // パスワードリセット確認
  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!resetCode.trim()) {
      setError("確認コードを入力してください");
      return;
    }

    if (!newPassword.trim()) {
      setError("新しいパスワードを入力してください");
      return;
    }

    if (!confirmPassword.trim()) {
      setError("パスワード確認を入力してください");
      return;
    }

    const passwordValidationError = validatePassword(newPassword);
    if (passwordValidationError) {
      setError(passwordValidationError);
      return;
    }

    const confirmPasswordValidationError =
      validateConfirmPassword(confirmPassword);
    if (confirmPasswordValidationError) {
      setError(confirmPasswordValidationError);
      return;
    }

    setIsLoading(true);

    try {
      const result = await cognitoConfirmResetPassword(
        email,
        resetCode,
        newPassword
      );

      if (result.success) {
        setSuccess(result.message || "パスワードが正常に変更されました");
        setTimeout(() => {
          onSuccess?.();
        }, 2000);
      } else {
        setError(result.message || "パスワード変更に失敗しました");
      }
    } catch (error) {
      console.error("Password reset confirmation error:", error);
      setError("パスワード変更に失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  // 新しいコードを要求
  const handleRequestNewCode = async () => {
    setError(null);
    setSuccess(null);
    setIsLoading(true);

    try {
      const result = await cognitoResetPassword(email);
      if (result.success) {
        setSuccess("新しい確認コードを送信しました");
      } else {
        setError(result.message || "確認コードの再送信に失敗しました");
      }
    } catch (error) {
      console.error("Resend reset code error:", error);
      setError("確認コードの再送信に失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  const passwordStrength = checkPasswordStrength(newPassword);

  if (step === "request") {
    return (
      <div
        className="w-full max-w-md mx-auto space-y-6"
        data-testid="password-reset-request-form"
      >
        <div className="text-center">
          <h2 className="text-2xl font-bold">パスワードリセット</h2>
          <p className="text-gray-600 mt-2">
            登録済みのメールアドレスを入力してください。パスワードリセット用のコードを送信します。
          </p>
        </div>

        {error && (
          <Alert variant="destructive" data-testid="error-message">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert data-testid="success-message">
            <AlertDescription>{success}</AlertDescription>
          </Alert>
        )}

        <form
          onSubmit={handleRequestReset}
          className="space-y-4"
          data-testid="request-form"
        >
          <div>
            <Label htmlFor="email">メールアドレス</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={handleEmailChange}
              placeholder="example@email.com"
              disabled={isLoading}
              data-testid="email-input"
              className={`mt-1 ${emailError ? "border-red-500" : ""}`}
            />
            {emailError && (
              <p
                className="text-sm text-red-500 mt-1"
                data-testid="email-error"
              >
                {emailError}
              </p>
            )}
          </div>

          <Button
            type="submit"
            disabled={isLoading || !email.trim() || !!emailError}
            className="w-full"
            data-testid="request-submit"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                送信中...
              </>
            ) : (
              "リセットコードを送信"
            )}
          </Button>
        </form>

        <div className="text-center space-y-2">
          {onCancel && (
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              className="w-full"
              data-testid="cancel-button"
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              ログインに戻る
            </Button>
          )}

          <div className="text-sm text-gray-600">
            <Link
              href="/login"
              className="text-blue-600 hover:text-blue-800 underline"
              data-testid="back-to-login"
            >
              ログインページに戻る
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="password-reset-confirm-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">新しいパスワードを設定</h2>
        <p className="text-gray-600 mt-2">
          {email} に送信された確認コードと新しいパスワードを入力してください
        </p>
      </div>

      {error && (
        <Alert variant="destructive" data-testid="error-message">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert data-testid="success-message">
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <form
        onSubmit={handleConfirmReset}
        className="space-y-4"
        data-testid="confirm-form"
      >
        <div>
          <Label htmlFor="resetCode">確認コード</Label>
          <Input
            id="resetCode"
            type="text"
            value={resetCode}
            onChange={(e) => setResetCode(e.target.value)}
            placeholder="6桁の確認コード"
            disabled={isLoading}
            data-testid="reset-code-input"
            className="mt-1"
            maxLength={6}
          />
        </div>

        <div>
          <Label htmlFor="newPassword">新しいパスワード</Label>
          <div className="relative">
            <Input
              id="newPassword"
              type={showNewPassword ? "text" : "password"}
              value={newPassword}
              onChange={handleNewPasswordChange}
              placeholder="新しいパスワードを入力"
              disabled={isLoading}
              data-testid="new-password-input"
              className={`mt-1 pr-10 ${passwordError ? "border-red-500" : ""}`}
            />
            <button
              type="button"
              onClick={() => setShowNewPassword(!showNewPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700"
              data-testid="new-password-toggle"
            >
              {showNewPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>

          {/* パスワード強度インジケーター */}
          {newPassword && (
            <div className="mt-2 space-y-1" data-testid="password-strength">
              <div className="flex items-center space-x-2 text-sm">
                <div className={`w-full h-2 rounded-full bg-gray-200`}>
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      passwordStrength.score <= 2
                        ? "bg-red-500"
                        : passwordStrength.score <= 3
                        ? "bg-yellow-500"
                        : passwordStrength.score <= 4
                        ? "bg-blue-500"
                        : "bg-green-500"
                    }`}
                    style={{ width: `${(passwordStrength.score / 5) * 100}%` }}
                  />
                </div>
                <span
                  className={`text-xs ${
                    passwordStrength.score <= 2
                      ? "text-red-500"
                      : passwordStrength.score <= 3
                      ? "text-yellow-500"
                      : passwordStrength.score <= 4
                      ? "text-blue-500"
                      : "text-green-500"
                  }`}
                >
                  {passwordStrength.score <= 2
                    ? "弱い"
                    : passwordStrength.score <= 3
                    ? "普通"
                    : passwordStrength.score <= 4
                    ? "強い"
                    : "非常に強い"}
                </span>
              </div>

              <div className="space-y-1 text-xs">
                <div
                  className={`flex items-center space-x-1 ${
                    passwordStrength.hasMinLength
                      ? "text-green-600"
                      : "text-gray-500"
                  }`}
                >
                  {passwordStrength.hasMinLength ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  <span>8文字以上</span>
                </div>
                <div
                  className={`flex items-center space-x-1 ${
                    passwordStrength.hasUpperCase
                      ? "text-green-600"
                      : "text-gray-500"
                  }`}
                >
                  {passwordStrength.hasUpperCase ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  <span>大文字を含む</span>
                </div>
                <div
                  className={`flex items-center space-x-1 ${
                    passwordStrength.hasLowerCase
                      ? "text-green-600"
                      : "text-gray-500"
                  }`}
                >
                  {passwordStrength.hasLowerCase ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  <span>小文字を含む</span>
                </div>
                <div
                  className={`flex items-center space-x-1 ${
                    passwordStrength.hasNumber
                      ? "text-green-600"
                      : "text-gray-500"
                  }`}
                >
                  {passwordStrength.hasNumber ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  <span>数字を含む</span>
                </div>
                <div
                  className={`flex items-center space-x-1 ${
                    passwordStrength.hasSymbol
                      ? "text-green-600"
                      : "text-gray-500"
                  }`}
                >
                  {passwordStrength.hasSymbol ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  <span>記号を含む</span>
                </div>
              </div>
            </div>
          )}

          {passwordError && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="password-error"
            >
              {passwordError}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="confirmPassword">パスワード確認</Label>
          <div className="relative">
            <Input
              id="confirmPassword"
              type={showConfirmPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={handleConfirmPasswordChange}
              placeholder="パスワードを再入力"
              disabled={isLoading}
              data-testid="confirm-password-input"
              className={`mt-1 pr-10 ${
                confirmPasswordError ? "border-red-500" : ""
              }`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700"
              data-testid="confirm-password-toggle"
            >
              {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {confirmPasswordError && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="confirm-password-error"
            >
              {confirmPasswordError}
            </p>
          )}
        </div>

        <Button
          type="submit"
          disabled={
            isLoading ||
            !resetCode.trim() ||
            !newPassword.trim() ||
            !confirmPassword.trim() ||
            !!passwordError ||
            !!confirmPasswordError
          }
          className="w-full"
          data-testid="confirm-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              変更中...
            </>
          ) : (
            "パスワードを変更"
          )}
        </Button>

        <div className="space-y-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleRequestNewCode}
            disabled={isLoading}
            className="w-full"
            data-testid="resend-code"
          >
            確認コードを再送信
          </Button>

          <Button
            type="button"
            variant="ghost"
            onClick={() => setStep("request")}
            disabled={isLoading}
            className="w-full"
            data-testid="back-to-request"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            メールアドレス入力に戻る
          </Button>
        </div>
      </form>
    </div>
  );
};
