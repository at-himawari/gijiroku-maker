"use client";

import React, { useState } from "react";
import { useAuthApi } from "@/hooks/useAuthApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2 } from "lucide-react";

interface LoginFormProps {
  onSuccess?: () => void;
}

export const LoginForm: React.FC<LoginFormProps> = ({ onSuccess }) => {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [error, setError] = useState<string | null>(null);

  const { isLoading, initiatePhoneAuth, verifyCode, requestNewCode } =
    useAuthApi();

  const handlePhoneSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 電話番号の基本的な検証
    if (!phoneNumber.trim()) {
      setError("電話番号を入力してください");
      return;
    }

    const result = await initiatePhoneAuth(phoneNumber);

    if (result.success) {
      setStep("code");
    } else {
      setError(result.message || "認証の開始に失敗しました");
    }
  };

  const handleCodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 認証コードの基本的な検証
    if (!code.trim()) {
      setError("認証コードを入力してください");
      return;
    }

    const result = await verifyCode(phoneNumber, code);

    if (result.success) {
      onSuccess?.();
    } else {
      setError(result.message || "認証コードの検証に失敗しました");
    }
  };

  const handleRequestNewCode = async () => {
    setError(null);
    const result = await requestNewCode(phoneNumber);

    if (!result.success) {
      setError(result.message || "新しい認証コードの送信に失敗しました");
    }
  };

  const handleBackToPhone = () => {
    setStep("phone");
    setCode("");
    setError(null);
  };

  return (
    <div className="w-full max-w-md mx-auto space-y-6" data-testid="login-form">
      <div className="text-center">
        <h2 className="text-2xl font-bold">ログイン</h2>
        <p className="text-gray-600 mt-2">
          {step === "phone"
            ? "電話番号を入力してSMS認証を開始してください"
            : "SMSで送信された認証コードを入力してください"}
        </p>
      </div>

      {error && (
        <Alert variant="destructive" data-testid="error-message">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {step === "phone" ? (
        <form
          onSubmit={handlePhoneSubmit}
          className="space-y-4"
          data-testid="phone-form"
        >
          <div>
            <Label htmlFor="phone">電話番号</Label>
            <Input
              id="phone"
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+81901234567"
              disabled={isLoading}
              data-testid="phone-input"
              className="mt-1"
            />
            <p className="text-sm text-gray-500 mt-1">
              国際形式で入力してください（例: +81901234567）
            </p>
          </div>

          <Button
            type="submit"
            disabled={isLoading || !phoneNumber.trim()}
            className="w-full"
            data-testid="phone-submit"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                送信中...
              </>
            ) : (
              "SMS送信"
            )}
          </Button>
        </form>
      ) : (
        <form
          onSubmit={handleCodeSubmit}
          className="space-y-4"
          data-testid="code-form"
        >
          <div>
            <Label htmlFor="code">認証コード</Label>
            <Input
              id="code"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="6桁の認証コード"
              disabled={isLoading}
              data-testid="code-input"
              className="mt-1"
              maxLength={6}
            />
            <p className="text-sm text-gray-500 mt-1">
              {phoneNumber} に送信された6桁のコードを入力してください
            </p>
          </div>

          <Button
            type="submit"
            disabled={isLoading || !code.trim()}
            className="w-full"
            data-testid="code-submit"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                検証中...
              </>
            ) : (
              "認証"
            )}
          </Button>

          <div className="flex flex-col space-y-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleRequestNewCode}
              disabled={isLoading}
              className="w-full"
            >
              新しいコードを送信
            </Button>

            <Button
              type="button"
              variant="ghost"
              onClick={handleBackToPhone}
              disabled={isLoading}
              className="w-full"
            >
              電話番号を変更
            </Button>
          </div>
        </form>
      )}
    </div>
  );
};
