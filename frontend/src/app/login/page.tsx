"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { CognitoLoginForm } from "@/components/CognitoLoginForm";
import { CognitoRegisterForm } from "@/components/CognitoRegisterForm";
import Image from "next/image";

function LoginPageContent() {
  const [currentView, setCurrentView] = useState<"login" | "register">("login");
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (isAuthenticated) {
      const returnTo = searchParams.get("returnTo") || "/";
      router.push(returnTo);
    }
  }, [isAuthenticated, router, searchParams]);

  const handleLoginSuccess = () => {
    const returnTo = searchParams.get("returnTo") || "/";
    router.push(returnTo);
  };

  const handleRegisterSuccess = () => {
    // 登録成功後はログイン画面に戻る
    setCurrentView("login");
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
          <h2 className="mt-6 text-3xl font-extrabold text-gray-900">
            議事録メーカー
          </h2>
        </div>

        <div className="mt-8">
          {currentView === "login" ? (
            <CognitoLoginForm
              onSuccess={handleLoginSuccess}
              onSwitchToRegister={() => setCurrentView("register")}
            />
          ) : (
            <CognitoRegisterForm
              onSuccess={handleRegisterSuccess}
              onSwitchToLogin={() => setCurrentView("login")}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LoginPageContent />
    </Suspense>
  );
}
