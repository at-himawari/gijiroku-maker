"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

interface ProtectedRouteProps {
  children: React.ReactNode;
  redirectTo?: string;
  requireAuth?: boolean; // 認証を必須とするか（デフォルト: true）
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  redirectTo = "/login",
  requireAuth = true,
}) => {
  const { isAuthenticated, loading, user } = useAuth();
  const router = useRouter();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (!loading && requireAuth && !isAuthenticated) {
      setRedirecting(true);

      // 現在のページのパスを取得して、リダイレクト後に戻れるようにする
      const currentPath = window.location.pathname + window.location.search;
      const returnUrl = `${redirectTo}?returnTo=${encodeURIComponent(
        currentPath
      )}`;

      // 少し遅延を入れてからリダイレクト（ユーザーに状況を理解させるため）
      setTimeout(() => {
        router.push(returnUrl);
      }, 1000);
    }
  }, [loading, isAuthenticated, requireAuth, redirectTo, router]);

  // 認証状態の読み込み中はローディング表示
  if (loading) {
    return (
      <div
        className="flex items-center justify-center min-h-screen bg-gray-50"
        data-testid="loading"
      >
        <div className="text-center p-8">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-gray-800 mb-2">
            認証状態を確認中...
          </h2>
          <p className="text-gray-600">しばらくお待ちください</p>
        </div>
      </div>
    );
  }

  // 認証が必要で未認証の場合
  if (requireAuth && !isAuthenticated) {
    return (
      <div
        className="flex items-center justify-center min-h-screen bg-gray-50"
        data-testid="redirecting"
      >
        <div className="text-center p-8">
          {redirecting ? (
            <>
              <div className="animate-pulse rounded-full h-12 w-12 bg-blue-200 mx-auto mb-4"></div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                ログインページにリダイレクト中...
              </h2>
              <p className="text-gray-600">認証が必要です</p>
            </>
          ) : (
            <>
              <div className="rounded-full h-12 w-12 bg-red-200 flex items-center justify-center mx-auto mb-4">
                <span className="text-red-600 text-xl">⚠</span>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                認証が必要です
              </h2>
              <p className="text-gray-600 mb-4">
                このページにアクセスするにはログインが必要です
              </p>
              <button
                onClick={() => {
                  const currentPath =
                    window.location.pathname + window.location.search;
                  const returnUrl = `${redirectTo}?returnTo=${encodeURIComponent(
                    currentPath
                  )}`;
                  router.push(returnUrl);
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                ログインページへ
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  // 認証済みまたは認証不要の場合は子コンポーネントを表示
  return <>{children}</>;
};
