"use client";

import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";

interface AuthApiResponse {
  success: boolean;
  message?: string;
  data?: unknown;
}

interface InitiateAuthResponse {
  success: boolean;
  message?: string;
}

interface VerifyCodeResponse {
  success: boolean;
  access_token?: string;
  refresh_token?: string;
  user?: {
    userId: string;
    phoneNumber: string;
  };
  message?: string;
}

export function useAuthApi() {
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();

  // 電話番号認証を開始
  const initiatePhoneAuth = async (
    phoneNumber: string
  ): Promise<InitiateAuthResponse> => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/auth/initiate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ phone_number: phoneNumber }),
        }
      );

      const data = await response.json();

      if (response.ok) {
        return { success: true, message: data.message };
      } else {
        return {
          success: false,
          message: data.error || "認証の開始に失敗しました",
        };
      }
    } catch (error) {
      console.error("認証開始エラー:", error);
      return { success: false, message: "ネットワークエラーが発生しました" };
    } finally {
      setIsLoading(false);
    }
  };

  // SMS認証コードを検証
  const verifyCode = async (
    phoneNumber: string,
    code: string
  ): Promise<VerifyCodeResponse> => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/auth/verify`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            phone_number: phoneNumber,
            code: code,
          }),
        }
      );

      const data = await response.json();

      if (response.ok) {
        // 認証成功時、AuthContextにログイン情報を設定
        if (data.access_token && data.refresh_token && data.user) {
          login(data.access_token, data.refresh_token, {
            userId: data.user.userId,
            phoneNumber: data.user.phoneNumber,
          });
        }

        return {
          success: true,
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          user: data.user,
          message: data.message,
        };
      } else {
        return {
          success: false,
          message: data.error || "認証コードの検証に失敗しました",
        };
      }
    } catch (error) {
      console.error("認証コード検証エラー:", error);
      return { success: false, message: "ネットワークエラーが発生しました" };
    } finally {
      setIsLoading(false);
    }
  };

  // 新しい認証コードを要求
  const requestNewCode = async (
    phoneNumber: string
  ): Promise<AuthApiResponse> => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/auth/resend`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ phone_number: phoneNumber }),
        }
      );

      const data = await response.json();

      if (response.ok) {
        return { success: true, message: data.message };
      } else {
        return {
          success: false,
          message: data.error || "新しい認証コードの送信に失敗しました",
        };
      }
    } catch (error) {
      console.error("認証コード再送信エラー:", error);
      return { success: false, message: "ネットワークエラーが発生しました" };
    } finally {
      setIsLoading(false);
    }
  };

  return {
    isLoading,
    initiatePhoneAuth,
    verifyCode,
    requestNewCode,
  };
}
