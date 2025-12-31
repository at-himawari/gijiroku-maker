"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Eye, EyeOff, CheckCircle, AlertCircle } from "lucide-react";
import Link from "next/link";
import { useFormPersistence } from "@/hooks/useFormPersistence";
import { useFormValidation } from "@/hooks/useFormValidation";
import { useLoadingState } from "@/hooks/useLoadingState";
import { ErrorMessageManager } from "@/lib/errorMessages";

interface CognitoLoginFormProps {
  onSuccess?: () => void;
  onSwitchToRegister?: () => void;
}

interface LoginFormData {
  email: string;
  password: string;
}

export const CognitoLoginForm: React.FC<CognitoLoginFormProps> = ({
  onSuccess,
  onSwitchToRegister,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { cognitoSignIn } = useAuth();

  // 定数として定義して再レンダリング時の再作成を防ぐ
  const excludeFields = useMemo(
    () => ["password"] as (keyof LoginFormData)[],
    []
  );
  const initialValues = useMemo(() => ({ email: "", password: "" }), []);
  const persistenceOptions = useMemo(
    () => ({ excludeFields }),
    [excludeFields]
  );

  // フォーム状態の永続化（パスワードは除外）
  const {
    values: formData,
    updateValue,
    handleSubmitSuccess,
    isLoaded,
  } = useFormPersistence<LoginFormData>(
    "login",
    initialValues,
    persistenceOptions
  );

  // バリデーションルールを定数として定義
  const validationRules = useMemo(
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
        minLength: 1,
      },
    }),
    []
  );

  // フォームバリデーション
  const {
    errors: validationErrors,
    touchedErrors,
    validate,
    validateAll,
    touch,
    clearAll: clearValidation,
  } = useFormValidation<LoginFormData>(validationRules);

  // ローディング状態管理
  const { isLoading, loadingMessage, startLoading, stopLoading } =
    useLoadingState();

  // フォーム入力ハンドラー
  const handleInputChange = (field: keyof LoginFormData, value: string) => {
    updateValue(field, value);
    validate(field, value);
    setError(null);
    setSuccess(null);
  };

  // フィールドフォーカス時の処理
  const handleFieldFocus = (field: keyof LoginFormData) => {
    touch(field);
  };

  // フォーム送信処理
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // 全フィールドのバリデーション
    if (!validateAll(formData)) {
      const errorMessages = Object.values(touchedErrors).filter(Boolean);
      if (errorMessages.length > 0) {
        setError(ErrorMessageManager.combineErrors(errorMessages));
      }
      return;
    }

    startLoading(ErrorMessageManager.getLoadingMessage("login"));

    try {
      const result = await cognitoSignIn(formData.email, formData.password);

      if (result.success) {
        setSuccess(ErrorMessageManager.getSuccessMessage("login"));
        handleSubmitSuccess();
        clearValidation();

        // 成功メッセージを少し表示してからコールバック実行
        setTimeout(() => {
          onSuccess?.();
        }, 1000);
      } else {
        setError(
          result.message || ErrorMessageManager.getCognitoErrorMessage(null)
        );
      }
    } catch (error: any) {
      console.error("Login error:", error);
      setError(ErrorMessageManager.getCognitoErrorMessage(error));
    } finally {
      stopLoading();
    }
  };

  const hasErrors = Object.values(touchedErrors).some(Boolean);

  // フォームの有効性チェック
  const isFormValid =
    !!formData.email.trim() && !!formData.password.trim() && !hasErrors;

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

  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="cognito-login-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">ログイン</h2>
        <p className="text-gray-600 mt-2">
          メールアドレスとパスワードでログインしてください
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
        data-testid="login-form"
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
              autoComplete="current-password"
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

        <Button
          type="submit"
          disabled={isLoading || !isFormValid}
          className="w-full"
          data-testid="login-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {loadingMessage}
            </>
          ) : (
            "ログイン"
          )}
        </Button>
      </form>

      <div className="space-y-4 text-center">
        <div>
          <Link
            href="/reset-password"
            className="text-sm text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
            data-testid="reset-password-link"
          >
            パスワードを忘れた方はこちら
          </Link>
        </div>

        {onSwitchToRegister && (
          <div className="text-sm text-gray-600">
            アカウントをお持ちでない方は{" "}
            <button
              type="button"
              onClick={onSwitchToRegister}
              className="text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
              data-testid="switch-to-register"
              disabled={isLoading}
            >
              新規登録
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
