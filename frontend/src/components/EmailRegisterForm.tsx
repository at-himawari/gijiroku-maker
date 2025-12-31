"use client";

import React, { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Eye, EyeOff, Check, X } from "lucide-react";

interface EmailRegisterFormProps {
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

interface FormErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
  givenName?: string;
  familyName?: string;
  phoneNumber?: string;
}

interface PasswordStrength {
  hasMinLength: boolean;
  hasUpperCase: boolean;
  hasLowerCase: boolean;
  hasNumber: boolean;
  hasSymbol: boolean;
  score: number;
}

/**
 * メールアドレス + パスワード認証用登録フォーム
 * 要件: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4, 7.5
 */
export const EmailRegisterForm: React.FC<EmailRegisterFormProps> = ({
  onSuccess,
  onSwitchToLogin,
}) => {
  const [formData, setFormData] = useState<FormData>({
    email: "",
    password: "",
    confirmPassword: "",
    givenName: "",
    familyName: "",
    phoneNumber: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [step, setStep] = useState<"register" | "confirm">("register");
  const [confirmationCode, setConfirmationCode] = useState("");

  const { cognitoSignUp, cognitoConfirmSignUp, cognitoResendSignUpCode } =
    useAuth();
  const router = useRouter();

  // パスワード強度チェック（要件: 1.4）
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

  // リアルタイムバリデーション（要件: 7.3）
  const validateField = (
    name: keyof FormData,
    value: string
  ): string | null => {
    switch (name) {
      case "email":
        if (!value) return null;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(value)
          ? null
          : "有効なメールアドレスを入力してください";

      case "password":
        if (!value) return null;
        const strength = checkPasswordStrength(value);
        if (!strength.hasMinLength)
          return "パスワードは8文字以上である必要があります";
        if (!strength.hasUpperCase) return "大文字を含む必要があります";
        if (!strength.hasLowerCase) return "小文字を含む必要があります";
        if (!strength.hasNumber) return "数字を含む必要があります";
        if (!strength.hasSymbol) return "記号を含む必要があります";
        return null;

      case "confirmPassword":
        if (!value) return null;
        return value === formData.password ? null : "パスワードが一致しません";

      case "givenName":
        if (!value) return null;
        return value.trim().length >= 1 ? null : "名前を入力してください";

      case "familyName":
        if (!value) return null;
        return value.trim().length >= 1 ? null : "姓を入力してください";

      case "phoneNumber":
        if (!value) return null;
        const phoneRegex = /^(\+81|0)[0-9]{10,11}$/;
        return phoneRegex.test(value.replace(/[-\s]/g, ""))
          ? null
          : "有効な日本の電話番号を入力してください（例: 090-1234-5678）";

      default:
        return null;
    }
  };

  // 入力状態保持（要件: 7.5）
  const handleInputChange = (name: keyof FormData, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));

    // リアルタイムバリデーション（要件: 7.3）
    const fieldError = validateField(name, value);
    setFormErrors((prev) => ({ ...prev, [name]: fieldError || undefined }));

    // 確認パスワードの再検証（パスワードが変更された場合）
    if (name === "password" && formData.confirmPassword) {
      const confirmError = validateField(
        "confirmPassword",
        formData.confirmPassword
      );
      setFormErrors((prev) => ({
        ...prev,
        confirmPassword: confirmError || undefined,
      }));
    }

    setError(null);
  };

  // フォーム全体のバリデーション（要件: 1.5）
  const validateForm = (): boolean => {
    const errors: FormErrors = {};
    let isValid = true;

    // 必須フィールドチェック（要件: 1.5）
    if (!formData.email.trim()) {
      errors.email = "メールアドレスは必須です";
      isValid = false;
    } else {
      const emailError = validateField("email", formData.email);
      if (emailError) {
        errors.email = emailError;
        isValid = false;
      }
    }

    if (!formData.password.trim()) {
      errors.password = "パスワードは必須です";
      isValid = false;
    } else {
      const passwordError = validateField("password", formData.password);
      if (passwordError) {
        errors.password = passwordError;
        isValid = false;
      }
    }

    if (!formData.confirmPassword.trim()) {
      errors.confirmPassword = "パスワード確認は必須です";
      isValid = false;
    } else {
      const confirmError = validateField(
        "confirmPassword",
        formData.confirmPassword
      );
      if (confirmError) {
        errors.confirmPassword = confirmError;
        isValid = false;
      }
    }

    if (!formData.givenName.trim()) {
      errors.givenName = "名前は必須です";
      isValid = false;
    }

    if (!formData.familyName.trim()) {
      errors.familyName = "姓は必須です";
      isValid = false;
    }

    if (!formData.phoneNumber.trim()) {
      errors.phoneNumber = "電話番号は必須です";
      isValid = false;
    } else {
      const phoneError = validateField("phoneNumber", formData.phoneNumber);
      if (phoneError) {
        errors.phoneNumber = phoneError;
        isValid = false;
      }
    }

    setFormErrors(errors);
    return isValid;
  };

  // 登録処理（要件: 1.1）
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!validateForm()) {
      setError(
        "入力内容に問題があります。すべての項目を正しく入力してください。"
      );
      return;
    }

    setIsLoading(true);

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
          setStep("confirm");
        } else {
          if (onSuccess) {
            onSuccess();
          } else {
            router.push("/");
          }
        }
      } else {
        // 重複チェック処理（要件: 1.2）
        setError(result.message || "アカウント作成に失敗しました");
      }
    } catch (error) {
      console.error("登録エラー:", error);
      setError("アカウント作成に失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  // 確認コード送信処理
  const handleConfirmSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!confirmationCode.trim()) {
      setError("確認コードを入力してください");
      return;
    }

    setIsLoading(true);

    try {
      const result = await cognitoConfirmSignUp(
        formData.email,
        confirmationCode
      );

      if (result.success) {
        if (onSuccess) {
          onSuccess();
        } else {
          router.push("/login");
        }
      } else {
        setError(result.message || "確認に失敗しました");
      }
    } catch (error) {
      console.error("確認エラー:", error);
      setError("確認に失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  // 確認コード再送信
  const handleResendCode = async () => {
    setError(null);
    setIsLoading(true);

    try {
      const result = await cognitoResendSignUpCode(formData.email);
      if (!result.success) {
        setError(result.message || "確認コードの再送信に失敗しました");
      }
    } catch (error) {
      console.error("再送信エラー:", error);
      setError("確認コードの再送信に失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  const passwordStrength = checkPasswordStrength(formData.password);

  // 確認コード入力画面
  if (step === "confirm") {
    return (
      <div
        className="w-full max-w-md mx-auto space-y-6"
        data-testid="email-confirm-form"
      >
        <div className="text-center">
          <h2 className="text-2xl font-bold">アカウント確認</h2>
          <p className="text-gray-600 mt-2">
            {formData.email} に送信された確認コードを入力してください
          </p>
        </div>

        {error && (
          <Alert variant="destructive" data-testid="error-message">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <form
          onSubmit={handleConfirmSubmit}
          className="space-y-4"
          data-testid="confirm-form"
        >
          <div>
            <Label htmlFor="confirmationCode">確認コード</Label>
            <Input
              id="confirmationCode"
              type="text"
              value={confirmationCode}
              onChange={(e) => setConfirmationCode(e.target.value)}
              placeholder="6桁の確認コード"
              disabled={isLoading}
              data-testid="confirmation-code-input"
              className="mt-1"
              maxLength={6}
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
                確認中...
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

  // 登録フォーム画面（要件: 7.1）
  return (
    <div
      className="w-full max-w-md mx-auto space-y-6"
      data-testid="email-register-form"
    >
      <div className="text-center">
        <h2 className="text-2xl font-bold">新規登録</h2>
        <p className="text-gray-600 mt-2">
          アカウントを作成してサービスを利用開始してください
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
        data-testid="register-form"
      >
        {/* メールアドレス（要件: 7.1） */}
        <div>
          <Label htmlFor="email">メールアドレス *</Label>
          <Input
            id="email"
            type="email"
            value={formData.email}
            onChange={(e) => handleInputChange("email", e.target.value)}
            placeholder="example@email.com"
            disabled={isLoading}
            data-testid="email-input"
            className={`mt-1 ${formErrors.email ? "border-red-500" : ""}`}
          />
          {formErrors.email && (
            <p className="text-sm text-red-500 mt-1" data-testid="email-error">
              {formErrors.email}
            </p>
          )}
        </div>

        {/* 姓（要件: 7.1） */}
        <div>
          <Label htmlFor="familyName">姓 *</Label>
          <Input
            id="familyName"
            type="text"
            value={formData.familyName}
            onChange={(e) => handleInputChange("familyName", e.target.value)}
            placeholder="山田"
            disabled={isLoading}
            data-testid="family-name-input"
            className={`mt-1 ${formErrors.familyName ? "border-red-500" : ""}`}
          />
          {formErrors.familyName && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="family-name-error"
            >
              {formErrors.familyName}
            </p>
          )}
        </div>

        {/* 名（要件: 7.1） */}
        <div>
          <Label htmlFor="givenName">名 *</Label>
          <Input
            id="givenName"
            type="text"
            value={formData.givenName}
            onChange={(e) => handleInputChange("givenName", e.target.value)}
            placeholder="太郎"
            disabled={isLoading}
            data-testid="given-name-input"
            className={`mt-1 ${formErrors.givenName ? "border-red-500" : ""}`}
          />
          {formErrors.givenName && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="given-name-error"
            >
              {formErrors.givenName}
            </p>
          )}
        </div>

        {/* 電話番号（要件: 7.1, 7.4） */}
        <div>
          <Label htmlFor="phoneNumber">電話番号 *</Label>
          <Input
            id="phoneNumber"
            type="tel"
            value={formData.phoneNumber}
            onChange={(e) => handleInputChange("phoneNumber", e.target.value)}
            placeholder="090-1234-5678"
            disabled={isLoading}
            data-testid="phone-number-input"
            className={`mt-1 ${formErrors.phoneNumber ? "border-red-500" : ""}`}
          />
          {formErrors.phoneNumber && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="phone-number-error"
            >
              {formErrors.phoneNumber}
            </p>
          )}
        </div>

        {/* パスワード（要件: 7.1, 7.2） */}
        <div>
          <Label htmlFor="password">パスワード *</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              value={formData.password}
              onChange={(e) => handleInputChange("password", e.target.value)}
              placeholder="パスワードを入力"
              disabled={isLoading}
              data-testid="password-input"
              className={`mt-1 pr-10 ${
                formErrors.password ? "border-red-500" : ""
              }`}
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

          {/* パスワード強度インジケーター（要件: 7.2） */}
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

          {formErrors.password && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="password-error"
            >
              {formErrors.password}
            </p>
          )}
        </div>

        {/* パスワード確認 */}
        <div>
          <Label htmlFor="confirmPassword">パスワード確認 *</Label>
          <div className="relative">
            <Input
              id="confirmPassword"
              type={showConfirmPassword ? "text" : "password"}
              value={formData.confirmPassword}
              onChange={(e) =>
                handleInputChange("confirmPassword", e.target.value)
              }
              placeholder="パスワードを再入力"
              disabled={isLoading}
              data-testid="confirm-password-input"
              className={`mt-1 pr-10 ${
                formErrors.confirmPassword ? "border-red-500" : ""
              }`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700"
              data-testid="confirm-password-toggle"
              tabIndex={-1}
            >
              {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {formErrors.confirmPassword && (
            <p
              className="text-sm text-red-500 mt-1"
              data-testid="confirm-password-error"
            >
              {formErrors.confirmPassword}
            </p>
          )}
        </div>

        {/* ローディング状態管理（要件: 7.5） */}
        <Button
          type="submit"
          disabled={
            isLoading ||
            Object.keys(formErrors).some(
              (key) => formErrors[key as keyof FormErrors]
            )
          }
          className="w-full"
          data-testid="register-submit"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              登録中...
            </>
          ) : (
            "アカウントを作成"
          )}
        </Button>
      </form>

      {/* ログインへのリンク */}
      {onSwitchToLogin && (
        <div className="text-center text-sm text-gray-600">
          既にアカウントをお持ちの方は{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-blue-600 hover:text-blue-800 underline"
            data-testid="switch-to-login"
          >
            ログイン
          </button>
        </div>
      )}
    </div>
  );
};
