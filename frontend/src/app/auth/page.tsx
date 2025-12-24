"use client";

import React, { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CognitoLoginForm } from "@/components/CognitoLoginForm";
import { CognitoRegisterForm } from "@/components/CognitoRegisterForm";
import { Button } from "@/components/ui/button";
import Image from "next/image";

function AuthPageContent() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const router = useRouter();
  const searchParams = useSearchParams();

  const handleSuccess = () => {
    const returnTo = searchParams.get("returnTo") || "/";
    router.push(returnTo);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <div className="flex justify-center">
            <Image
              className="h-12 w-auto"
              src="/logo.png"
              alt="議事録メーカー"
              width={48}
              height={48}
            />
          </div>
          <h1 className="mt-6 text-3xl font-extrabold text-gray-900">
            議事録メーカー
          </h1>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6">
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

          {mode === "login" ? (
            <CognitoLoginForm
              onSuccess={handleSuccess}
              onSwitchToRegister={() => setMode("register")}
            />
          ) : (
            <CognitoRegisterForm
              onSuccess={handleSuccess}
              onSwitchToLogin={() => setMode("login")}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function AuthPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AuthPageContent />
    </Suspense>
  );
}
