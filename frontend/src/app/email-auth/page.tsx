"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { EmailLoginForm } from "@/components/EmailLoginForm";
import { EmailRegisterForm } from "@/components/EmailRegisterForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * メールアドレス + パスワード認証ページ
 * ログインと登録フォームを切り替え可能
 * 要件: 2.1, 7.1, 7.2, 7.3, 7.4, 7.5
 */
export default function EmailAuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const router = useRouter();

  const handleAuthSuccess = () => {
    // 認証成功時は文字起こしアプリにリダイレクト
    router.push("/");
  };

  const handleForgotPassword = () => {
    // パスワードリセットページにリダイレクト
    router.push("/reset-password");
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-3xl font-bold text-gray-900">
              議事録メーカー
            </CardTitle>
            <p className="text-gray-600">
              {mode === "login"
                ? "アカウントにログインしてください"
                : "新しいアカウントを作成してください"}
            </p>
          </CardHeader>
          <CardContent>
            {/* モード切り替えタブ */}
            <div className="flex mb-6 bg-gray-100 rounded-lg p-1">
              <Button
                variant={mode === "login" ? "default" : "ghost"}
                onClick={() => setMode("login")}
                className="flex-1"
                data-testid="login-tab"
              >
                ログイン
              </Button>
              <Button
                variant={mode === "register" ? "default" : "ghost"}
                onClick={() => setMode("register")}
                className="flex-1"
                data-testid="register-tab"
              >
                新規登録
              </Button>
            </div>

            {/* フォーム表示 */}
            {mode === "login" ? (
              <EmailLoginForm
                onSuccess={handleAuthSuccess}
                onSwitchToRegister={() => setMode("register")}
                onForgotPassword={handleForgotPassword}
              />
            ) : (
              <EmailRegisterForm
                onSuccess={handleAuthSuccess}
                onSwitchToLogin={() => setMode("login")}
              />
            )}
          </CardContent>
        </Card>

        {/* 既存の電話番号認証へのリンク */}
        <div className="text-center">
          <p className="text-sm text-gray-600">
            電話番号認証をご希望の方は{" "}
            <button
              onClick={() => router.push("/login")}
              className="text-blue-600 hover:text-blue-800 underline"
              data-testid="phone-auth-link"
            >
              こちら
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
