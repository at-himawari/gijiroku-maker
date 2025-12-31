"use client";

import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Loader2,
  Eye,
  EyeOff,
  Check,
  X,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { useFormPersistence } from "@/hooks/useFormPersistence";
import { useFormValidation } from "@/hooks/useFormValidation";
import { useLoadingState } from "@/hooks/useLoadingState";
import { ErrorMessageManager } from "@/lib/errorMessages";

interface EmailPasswordResetFormProps {
  onSuccess?: () => void;
  onBackToLogin?: () => void;
}

interface PasswordStrength {
  hasMinLength: boolean;
  hasUpperCase: boolean;
  hasLowerCase: boolean;
  hasNumber: boolean;
  hasSymbol: boolean;
  score: number;
}

interface ResetFormData {
  email: string;
  code: string;
  newPassword: string;
  confirmPassword: string;
}

/**
 * メールアドレス + パスワード認証用パスワードリセットフォーム
 * 要件: 9.1, 9.2, 9.3, 9.4, 9.5
 */
export const EmailPasswordResetForm: React.FC<EmailPasswordResetFormProps> = ({
  onSuccess,
  onBackToLogin,
}) => {
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { cognitoResetPassword, cognitoConfirmResetPassword } = useAuth();
  const router = useRouter();

  // フォーム状態の永続化（パスワードは除外）
  const {
    values: formData,
    updateValue,
    handleSubmitSuccess,
    isLoaded,
  } = useFormPersistence<ResetFormData>(
    "passwordReset",
    { email: "", code: "", newPassword: "", confirmPassword: "" },
    { excludeFields: ["newPassword", "confirmPassword", "code"] }
  );

  // フォームバリデーション
  const {
    errors: validationErrors,
    touchedErrors,
    validate,
    validateAll,
    touch,
    clearAll: clearValidation,
  } = useFormValidation<ResetFormData>({
    email: {
      required: true,
      custom: (value: string) => {
        if (!value) return null;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(value)
          ? null
          : ErrorMessageManager.getValidationErrorMessage("email");
      },
    },
    code: {
      required: true,
      minLength: 6,
      maxLength: 6,
    },
    newPassword: {
      required: true,
      custom: (value: string) => {
        if (!value) return null;
        const strength = checkPasswordStrength(value);
        if (!strength.hasMinLength)
          return "パスワードは8文字以上である必要があります";
        if (!strength.hasUpperCase) return "大文字を含む必要があります";
        if (!strength.hasLowerCase) return "小文字を含む必要があります";
        if (!strength.hasNumber) return "数字を含む必要があります";
        if (!strength.hasSymbol) return "記号を含む必要があります";
        return null;
      },
    },
    confirmPassword: {
      required: true,
      custom: (value: string) => {
        if (!value) return null;
        return value === formData.newPassword
          ? null
          : "パスワードが一致しません";
      },
    },
  });

  // ローディング状態管理
  const { isLoading, loadingMessage, startLoading, stopLoading } =
    useLoadingState();

  // パスワード強度チェック（要件: 9.3）
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

  // フォーム入力ハンドラー
  const handleInputChange = (field: keyof ResetFormData, value: string) => {
    updateValue(field, value);
    validate(field, value);

    // 確認パスワードの再検証（新しいパスワードが変更された場合）
    if (field === "newPassword" && formData.confirmPassword) {
      validate("confirmPassword", formData.confirmPassword);
    }

    setError(null);
    setSuccess(null);
  };

  // フィールドフォーカス時の処理
  const handleFieldFocus = (field: keyof ResetFormData) => {
    touch(field);
  };

  // パスワードリセット要求（要件: 9.1）
  const handleRequestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (
      !validateAll({
        email: formData.email,
        code: "",
        newPassword: "",
        confirmPassword: "",
      })
    ) {
      const errorMessages = Object.values(touchedErrors).filter(Boolean);
      if (errorMessages.length > 0) {
        setError(ErrorMessageManager.combineErrors(errorMessages));
      }
      return;
    }

    startLoading(ErrorMessageManager.getLoadingMessage("resetPassword"));

    try {
      const result = await cognitoResetPassword(formData.email);

      // セキュリティ上の理由で常に成功メッセージを表示（要件: 9.5）
      setSuccess(
        result.message || ErrorMessageManager.getSuccessMessage("resetPassword")
      );
      setStep("confirm");
    } catch (error: any) {
      console.error("パスワードリセット要求エラー:", error);
      // セキュリティ上の理由で成功メッセージを表示（要件: 9.5）
      setSuccess(ErrorMessageManager.getSuccessMessage("resetPassword"));
      setStep("confirm");
    } finally {
      stopLoading();
    }
  };

  // パスワードリセット確認（要件: 9.3）
  const handleConfirmSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!validateAll(formData)) {
      const errorMessages = Object.values(touchedErrors).filter(Boolean);
      if (errorMessages.length > 0) {
        setError(ErrorMessageManager.combineErrors(errorMessages));
      }
      return;
    }

    startLoading(ErrorMessageManager.getLoadingMessage("changePassword"));

    try {
      const result = await cognitoConfirmResetPassword(
        formData.email,
        formData.code,
        formData.newPassword
      );

      if (result.success) {
        setSuccess(
          result.message ||
            ErrorMessageManager.getSuccessMessage("changePassword")
        );
        handleSubmitSuccess();
        clearValidation();

        // 成功後の処理
        setTimeout(() => {
          if (onSuccess) {
            onSuccess();
          } else {
            router.push("/email-auth");
          }
        }, 2000);
      } else {
        setError(
          result.message || ErrorMessageManager.getCognitoErrorMessage(null)
        );
      }
    } catch (error: any) {
      console.error("パスワードリセット確認エラー:", error);
      setError(ErrorMessageManager.getCognitoErrorMessage(error));
    } finally {
      stopLoading();
    }
  };

  const passwordStrength = checkPasswordStrength(formData.newPassword);

  // ローディング中はフォームを表示しない
  if (!isLoaded) {
    return (
      <div className="w-full max-w-md mx-auto space-y-6">
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span className="ml-2">フォームを読み込み中...</span>
        </div>
      </div>
    );
  }

  // パスワードリセット要求画面
  if (step === "request") {
    return (
      <div
        className="w-full max-w-md mx-auto space-y-6"
        data-testid="password-reset-request-form"
      >
        <div className="text-center">
          <h2 className="text-2xl font-bold">パスワードリセット</h2>
          <p className="text-gray-600 mt-2">
            登録済みのメールアドレスを入力してください
          </p>
        </div>

        {error && (
          <Alert variant="destructive" data-testid="error-message">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="whitespace-pre-line">
              {error}
            </AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert
            data-testid="success-message"
            className="border-green-200 bg-green-50"
          >
            <CheckCircle className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-800">
              {success}
            </AlertDescription>
          </Alert>
        )}

        <form
          onSubmit={handleRequestSubmit}
          className="space-y-4"
          data-testid="request-form"
        >
          <div>
            <Label htmlFor="email">
              メールアドレス
              <span className="text-red-500 ml-1">*</span>
            </Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => handleInputChange("email", e.target.value)}
              onFocus={() => handleFieldFocus("email")}
              placeholder="example@email.com"
              disabled={isLoading}
              data-testid="email-input"
              className={`mt-1 ${
                touchedErrors.email ? "border-red-500 focus:border-red-500" : ""
              }`}
              autoComplete="email"
            />
            {touchedErrors.email && (
              <p
                className="text-sm text-red-500 mt-1 flex items-center"
                data-testid="email-error"
              >
                <AlertCircle className="h-3 w-3 mr-1" />
                {touchedErrors.email}
              </p>
            )}
          </div>

          <Button
            type="submit"
            disabled={
              isLoading || !formData.email.trim() || !!touchedErrors.email
            }
            className="w-full"
            data-testid="request-submit"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {loadingMessage}
              </>
            ) : (
              "リセットコードを送信"
            )}
          </Button>
        </form>

        {onBackToLogin && (
          <div className="text-center">
            <button
              type="button"
              onClick={onBackToLogin}
              className="text-sm text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
              data-testid="back-to-login"
              disabled={isLoading}
            >
              ログインに戻る
            </button>
          </div>
        )}
      </div>
    );
  }

  // パスワードリセット確認画面（要件: 9.2, 9.4）
  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="password-reset-confirm-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">新しいパスワードを設定</h2>
        <p className="text-gray-600 mt-2">
          {formData.email}{" "}
          に送信された確認コードと新しいパスワードを入力してください
        </p>
      </div>

      {error && (
        <Alert variant="destructive" data-testid="error-message">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="whitespace-pre-line">
            {error}
          </AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert
          data-testid="success-message"
          className="border-green-200 bg-green-50"
        >
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-800">
            {success}
          </AlertDescription>
        </Alert>
      )}

      <form
        onSubmit={handleConfirmSubmit}
        className="space-y-4"
        data-testid="confirm-form"
      >
        {/* 確認コード */}
        <div>
          <Label htmlFor="code">
            確認コード
            <span className="text-red-500 ml-1">*</span>
          </Label>
          <Input
            id="code"
            type="text"
            value={formData.code}
            onChange={(e) => handleInputChange("code", e.target.value)}
            onFocus={() => handleFieldFocus("code")}
            placeholder="6桁の確認コード"
            disabled={isLoading}
            data-testid="code-input"
            className={`mt-1 ${
              touchedErrors.code ? "border-red-500 focus:border-red-500" : ""
            }`}
            maxLength={6}
            autoComplete="one-time-code"
          />
          {touchedErrors.code && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="code-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.code}
            </p>
          )}
        </div>

        {/* 新しいパスワード */}
        <div>
          <Label htmlFor="newPassword">
            新しいパスワード
            <span className="text-red-500 ml-1">*</span>
          </Label>
          <div className="relative">
            <Input
              id="newPassword"
              type={showNewPassword ? "text" : "password"}
              value={formData.newPassword}
              onChange={(e) => handleInputChange("newPassword", e.target.value)}
              onFocus={() => handleFieldFocus("newPassword")}
              placeholder="新しいパスワードを入力"
              disabled={isLoading}
              data-testid="new-password-input"
              className={`mt-1 pr-10 ${
                touchedErrors.newPassword
                  ? "border-red-500 focus:border-red-500"
                  : ""
              }`}
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowNewPassword(!showNewPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none"
              data-testid="new-password-toggle"
              tabIndex={-1}
              disabled={isLoading}
            >
              {showNewPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>

          {/* パスワード強度インジケーター */}
          {formData.newPassword && (
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
                  className={`text-xs font-medium ${
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

              <div className="grid grid-cols-2 gap-1 text-xs">
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
                  <span>大文字</span>
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
                  <span>小文字</span>
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
                  <span>数字</span>
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
                  <span>記号</span>
                </div>
              </div>
            </div>
          )}

          {touchedErrors.newPassword && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="password-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.newPassword}
            </p>
          )}
        </div>

        {/* パスワード確認 */}
        <div>
          <Label htmlFor="confirmPassword">
            パスワード確認
            <span className="text-red-500 ml-1">*</span>
          </Label>
          <div className="relative">
            <Input
              id="confirmPassword"
              type={showConfirmPassword ? "text" : "password"}
              value={formData.confirmPassword}
              onChange={(e) =>
                handleInputChange("confirmPassword", e.target.value)
              }
              onFocus={() => handleFieldFocus("confirmPassword")}
              placeholder="パスワードを再入力"
              disabled={isLoading}
              data-testid="confirm-password-input"
              className={`mt-1 pr-10 ${
                touchedErrors.confirmPassword
                  ? "border-red-500 focus:border-red-500"
                  : ""
              }`}
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none"
              data-testid="confirm-password-toggle"
              tabIndex={-1}
              disabled={isLoading}
            >
              {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {touchedErrors.confirmPassword && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="confirm-password-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.confirmPassword}
            </p>
          )}
        </div>

        <Button
          type="submit"
          disabled={
            isLoading ||
            !formData.code.trim() ||
            !formData.newPassword.trim() ||
            !formData.confirmPassword.trim() ||
            Object.keys(touchedErrors).length > 0
          }
          className="w-full"
          data-testid="confirm-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {loadingMessage}
            </>
          ) : (
            "パスワードを変更"
          )}
        </Button>
      </form>

      <div className="text-center">
        <button
          type="button"
          onClick={() => setStep("request")}
          className="text-sm text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
          data-testid="back-to-request"
          disabled={isLoading}
        >
          メールアドレスを変更
        </button>
      </div>
    </div>
  );
};
