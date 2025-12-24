"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
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

interface CognitoRegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
}

interface FormData {
  email: string;
  password: string;
  confirmPassword: string;
  givenName: string;
  familyName: string;
  phoneNumber: string;
}

interface PasswordStrength {
  hasMinLength: boolean;
  hasUpperCase: boolean;
  hasLowerCase: boolean;
  hasNumber: boolean;
  hasSymbol: boolean;
  score: number;
}

export const CognitoRegisterForm: React.FC<CognitoRegisterFormProps> = ({
  onSuccess,
  onSwitchToLogin,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [step, setStep] = useState<"register" | "confirm">("register");
  const [confirmationCode, setConfirmationCode] = useState("");

  const { cognitoSignUp, cognitoConfirmSignUp, cognitoResendSignUpCode } =
    useAuth();

  // 定数として定義して再レンダリング時の再作成を防ぐ
  const excludeFields = useMemo(
    () => ["password", "confirmPassword"] as (keyof FormData)[],
    []
  );
  const initialValues = useMemo(
    () => ({
      email: "",
      password: "",
      confirmPassword: "",
      givenName: "",
      familyName: "",
      phoneNumber: "",
    }),
    []
  );
  const persistenceOptions = useMemo(
    () => ({ excludeFields }),
    [excludeFields]
  );

  // フォーム状態の永続化（パスワードは除外）
  const {
    values: formData,
    updateValue,
    updateValues,
    handleSubmitSuccess,
    isLoaded,
  } = useFormPersistence<FormData>(
    "register",
    initialValues,
    persistenceOptions
  );

  // パスワード強度チェック
  const checkPasswordStrength = useCallback(
    (password: string): PasswordStrength => {
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
    },
    []
  );

  // バリデーションルールを定数として定義（confirmPasswordは動的に更新）
  const baseValidationRules = useMemo(
    () => ({
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
      password: {
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
      givenName: {
        required: true,
        minLength: 1,
      },
      familyName: {
        required: true,
        minLength: 1,
      },
      phoneNumber: {
        required: true,
        custom: (value: string) => {
          if (!value) return null;
          const phoneRegex = /^(\+81|0)[0-9]{10,11}$/;
          return phoneRegex.test(value.replace(/[-\s]/g, ""))
            ? null
            : ErrorMessageManager.getValidationErrorMessage("phoneNumber");
        },
      },
    }),
    [checkPasswordStrength]
  );

  // confirmPasswordのバリデーションルールは動的に生成
  const validationRules = useMemo(
    () => ({
      ...baseValidationRules,
      confirmPassword: {
        required: true,
        custom: (value: string) => {
          if (!value) return null;
          return value === formData.password
            ? null
            : "パスワードが一致しません";
        },
      },
    }),
    [baseValidationRules, formData.password]
  );

  // フォームバリデーション
  const {
    errors: validationErrors,
    touchedErrors,
    validate,
    validateAll,
    touch,
    clearAll: clearValidation,
  } = useFormValidation<FormData>(validationRules);

  // ローディング状態管理
  const { isLoading, loadingMessage, startLoading, stopLoading } =
    useLoadingState();

  // フォーム入力ハンドラー
  const handleInputChange = (field: keyof FormData, value: string) => {
    updateValue(field, value);
    validate(field, value);

    // 確認パスワードの再検証（パスワードが変更された場合）
    if (field === "password" && formData.confirmPassword) {
      validate("confirmPassword", formData.confirmPassword);
    }

    setError(null);
    setSuccess(null);
  };

  // フィールドフォーカス時の処理
  const handleFieldFocus = (field: keyof FormData) => {
    touch(field);
  };

  const handleSubmit = async (e: React.FormEvent) => {
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

    startLoading(ErrorMessageManager.getLoadingMessage("register"));

    try {
      // 電話番号を国際形式に変換
      const formattedPhone = formData.phoneNumber.startsWith("+81")
        ? formData.phoneNumber
        : formData.phoneNumber.replace(/^0/, "+81");

      const result = await cognitoSignUp(
        formData.email,
        formData.password,
        formData.givenName,
        formData.familyName,
        formattedPhone
      );

      if (result.success) {
        if (result.requiresConfirmation) {
          setSuccess(
            result.message || ErrorMessageManager.getSuccessMessage("register")
          );
          setStep("confirm");
        } else {
          setSuccess(ErrorMessageManager.getSuccessMessage("register"));
          handleSubmitSuccess();
          clearValidation();
          setTimeout(() => {
            onSuccess?.();
          }, 1000);
        }
      } else {
        setError(
          result.message || ErrorMessageManager.getCognitoErrorMessage(null)
        );
      }
    } catch (error: any) {
      console.error("Registration error:", error);
      setError(ErrorMessageManager.getCognitoErrorMessage(error));
    } finally {
      stopLoading();
    }
  };

  const handleConfirmSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!confirmationCode.trim()) {
      setError("確認コードを入力してください");
      return;
    }

    startLoading(ErrorMessageManager.getLoadingMessage("confirm"));

    try {
      const result = await cognitoConfirmSignUp(
        formData.email,
        confirmationCode
      );

      if (result.success) {
        setSuccess(
          result.message || ErrorMessageManager.getSuccessMessage("confirm")
        );
        handleSubmitSuccess();
        clearValidation();
        setTimeout(() => {
          onSuccess?.();
        }, 1000);
      } else {
        setError(
          result.message || ErrorMessageManager.getCognitoErrorMessage(null)
        );
      }
    } catch (error: any) {
      console.error("Confirmation error:", error);
      setError(ErrorMessageManager.getCognitoErrorMessage(error));
    } finally {
      stopLoading();
    }
  };

  const handleResendCode = async () => {
    setError(null);
    setSuccess(null);

    startLoading(ErrorMessageManager.getLoadingMessage("resendCode"));

    try {
      const result = await cognitoResendSignUpCode(formData.email);
      if (result.success) {
        setSuccess(
          result.message || ErrorMessageManager.getSuccessMessage("resendCode")
        );
      } else {
        setError(result.message || "確認コードの再送信に失敗しました");
      }
    } catch (error: any) {
      console.error("Resend code error:", error);
      setError(ErrorMessageManager.getCognitoErrorMessage(error));
    } finally {
      stopLoading();
    }
  };

  const passwordStrength = checkPasswordStrength(formData.password);

  const hasErrors = Object.values(validationErrors).some(Boolean);
  // フォームの有効性チェック
  const isFormValid =
    Object.values(formData).every((value) => value.trim()) && !hasErrors;

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

  if (step === "confirm") {
    return (
      <div
        className="w-full max-w-md mx-auto space-y-6"
        data-testid="cognito-confirm-form"
      >
        <div className="text-center">
          <h2 className="text-2xl font-bold">アカウント確認</h2>
          <p className="text-gray-600 mt-2">
            {formData.phoneNumber} に送信された確認コードを入力してください
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
          <div>
            <Label htmlFor="confirmationCode">
              確認コード
              <span className="text-red-500 ml-1">*</span>
            </Label>
            <Input
              id="confirmationCode"
              type="text"
              value={confirmationCode}
              onChange={(e) => {
                setConfirmationCode(e.target.value);
                setError(null);
                setSuccess(null);
              }}
              placeholder="6桁の確認コード"
              disabled={isLoading}
              data-testid="confirmation-code-input"
              className="mt-1"
              maxLength={6}
              autoComplete="one-time-code"
            />
          </div>

          <Button
            type="submit"
            disabled={isLoading || !confirmationCode.trim()}
            className="w-full"
            data-testid="confirm-submit"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {loadingMessage}
              </>
            ) : (
              "アカウントを確認"
            )}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={handleResendCode}
            disabled={isLoading}
            className="w-full"
            data-testid="resend-code"
          >
            確認コードを再送信
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="cognito-register-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">新規登録</h2>
        <p className="text-gray-600 mt-2">
          アカウントを作成してサービスを利用開始してください
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
        onSubmit={handleSubmit}
        className="space-y-4"
        data-testid="register-form"
      >
        {/* メールアドレス */}
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

        {/* 姓 */}
        <div>
          <Label htmlFor="familyName">
            姓<span className="text-red-500 ml-1">*</span>
          </Label>
          <Input
            id="familyName"
            type="text"
            value={formData.familyName}
            onChange={(e) => handleInputChange("familyName", e.target.value)}
            onFocus={() => handleFieldFocus("familyName")}
            placeholder="山田"
            disabled={isLoading}
            data-testid="family-name-input"
            className={`mt-1 ${
              touchedErrors.familyName
                ? "border-red-500 focus:border-red-500"
                : ""
            }`}
            autoComplete="family-name"
          />
          {touchedErrors.familyName && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="family-name-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.familyName}
            </p>
          )}
        </div>

        {/* 名 */}
        <div>
          <Label htmlFor="givenName">
            名<span className="text-red-500 ml-1">*</span>
          </Label>
          <Input
            id="givenName"
            type="text"
            value={formData.givenName}
            onChange={(e) => handleInputChange("givenName", e.target.value)}
            onFocus={() => handleFieldFocus("givenName")}
            placeholder="太郎"
            disabled={isLoading}
            data-testid="given-name-input"
            className={`mt-1 ${
              touchedErrors.givenName
                ? "border-red-500 focus:border-red-500"
                : ""
            }`}
            autoComplete="given-name"
          />
          {touchedErrors.givenName && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="given-name-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.givenName}
            </p>
          )}
        </div>

        {/* 電話番号 */}
        <div>
          <Label htmlFor="phoneNumber">
            電話番号
            <span className="text-red-500 ml-1">*</span>
          </Label>
          <Input
            id="phoneNumber"
            type="tel"
            value={formData.phoneNumber}
            onChange={(e) => handleInputChange("phoneNumber", e.target.value)}
            onFocus={() => handleFieldFocus("phoneNumber")}
            placeholder="090-1234-5678"
            disabled={isLoading}
            data-testid="phone-number-input"
            className={`mt-1 ${
              touchedErrors.phoneNumber
                ? "border-red-500 focus:border-red-500"
                : ""
            }`}
            autoComplete="tel"
          />
          {touchedErrors.phoneNumber && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="phone-number-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.phoneNumber}
            </p>
          )}
        </div>

        {/* パスワード */}
        <div>
          <Label htmlFor="password">
            パスワード
            <span className="text-red-500 ml-1">*</span>
          </Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              value={formData.password}
              onChange={(e) => handleInputChange("password", e.target.value)}
              onFocus={() => handleFieldFocus("password")}
              placeholder="パスワードを入力"
              disabled={isLoading}
              data-testid="password-input"
              className={`mt-1 pr-10 ${
                touchedErrors.password
                  ? "border-red-500 focus:border-red-500"
                  : ""
              }`}
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none"
              data-testid="password-toggle"
              tabIndex={-1}
              disabled={isLoading}
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>

          {/* パスワード強度インジケーター */}
          {formData.password && (
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

          {touchedErrors.password && (
            <p
              className="text-sm text-red-500 mt-1 flex items-center"
              data-testid="password-error"
            >
              <AlertCircle className="h-3 w-3 mr-1" />
              {touchedErrors.password}
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
          disabled={isLoading || !isFormValid}
          className="w-full"
          data-testid="register-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {loadingMessage}
            </>
          ) : (
            "アカウントを作成"
          )}
        </Button>
      </form>

      {onSwitchToLogin && (
        <div className="text-center text-sm text-gray-600">
          既にアカウントをお持ちの方は{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
            data-testid="switch-to-login"
            disabled={isLoading}
          >
            ログイン
          </button>
        </div>
      )}
    </div>
  );
};
