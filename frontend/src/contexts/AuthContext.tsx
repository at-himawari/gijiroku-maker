"use client";
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { Amplify } from "aws-amplify";
import {
  signIn,
  signUp,
  signOut,
  getCurrentUser,
  fetchAuthSession,
  confirmSignUp,
  resetPassword,
  confirmResetPassword,
  resendSignUpCode,
  type SignInInput,
  type SignUpInput,
  type ConfirmSignUpInput,
  type ResetPasswordInput,
  type ConfirmResetPasswordInput,
} from "aws-amplify/auth";

// Amplify設定
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!,
      userPoolClientId: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!,
      loginWith: {
        email: true,
      },
    },
  },
});

interface User {
  userId: string;
  email?: string;
  phoneNumber?: string;
  givenName?: string;
  familyName?: string;
  // 既存の電話番号認証との互換性のため
  phone_number?: string;
}

interface AuthContextType {
  isAuthenticated: boolean;
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  login: (accessToken: string, refreshToken: string, user: User) => void;
  logout: () => Promise<void>;
  loading: boolean;
  // Cognito認証メソッド
  cognitoSignIn: (
    email: string,
    password: string
  ) => Promise<{ success: boolean; message?: string }>;
  cognitoSignUp: (
    email: string,
    password: string,
    givenName: string,
    familyName: string,
    phoneNumber: string
  ) => Promise<{
    success: boolean;
    message?: string;
    requiresConfirmation?: boolean;
  }>;
  cognitoConfirmSignUp: (
    email: string,
    code: string
  ) => Promise<{ success: boolean; message?: string }>;
  cognitoSignOut: () => Promise<void>;
  cognitoResetPassword: (
    email: string
  ) => Promise<{ success: boolean; message?: string }>;
  cognitoConfirmResetPassword: (
    email: string,
    code: string,
    newPassword: string
  ) => Promise<{ success: boolean; message?: string }>;
  cognitoResendSignUpCode: (
    email: string
  ) => Promise<{ success: boolean; message?: string }>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // ページロード時にCognitoセッションを確認
    checkCognitoSession();
  }, []);

  const checkCognitoSession = async () => {
    try {
      // Cognitoセッションを確認
      const session = await fetchAuthSession();
      if (session.tokens?.accessToken) {
        const currentUser = await getCurrentUser();
        const userAttributes = currentUser.signInDetails?.loginId
          ? {
              userId: currentUser.userId,
              email: currentUser.signInDetails.loginId,
              givenName: currentUser.signInDetails?.loginId, // 実際の属性は後で取得
              familyName: "",
              phoneNumber: "",
            }
          : null;

        if (userAttributes) {
          setToken(session.tokens.accessToken.toString());
          // Refresh tokenは直接アクセスできない場合があるため、nullに設定
          setRefreshToken(null);
          setUser(userAttributes);
        }
      } else {
        // Cognitoセッションがない場合、ローカルストレージから電話番号認証情報を取得
        const savedToken = localStorage.getItem("auth_access_token");
        const savedRefreshToken = localStorage.getItem("auth_refresh_token");
        const savedUser = localStorage.getItem("auth_user_data");

        if (savedToken && savedRefreshToken && savedUser) {
          try {
            const parsedUser = JSON.parse(savedUser);
            // トークンの有効性を確認（簡易チェック）
            if (isTokenValid(savedToken)) {
              setToken(savedToken);
              setRefreshToken(savedRefreshToken);
              setUser(parsedUser);
            } else {
              clearAuthData();
            }
          } catch (error) {
            console.error("Saved user data parsing error:", error);
            clearAuthData();
          }
        }
      }
    } catch (error) {
      console.error("Cognito session check error:", error);
      // Cognitoセッションエラーの場合、ローカルストレージをチェック
      const savedToken = localStorage.getItem("auth_access_token");
      const savedRefreshToken = localStorage.getItem("auth_refresh_token");
      const savedUser = localStorage.getItem("auth_user_data");

      if (savedToken && savedRefreshToken && savedUser) {
        try {
          const parsedUser = JSON.parse(savedUser);
          if (isTokenValid(savedToken)) {
            setToken(savedToken);
            setRefreshToken(savedRefreshToken);
            setUser(parsedUser);
          } else {
            clearAuthData();
          }
        } catch (error) {
          console.error("Saved user data parsing error:", error);
          clearAuthData();
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const clearAuthData = () => {
    localStorage.removeItem("auth_access_token");
    localStorage.removeItem("auth_refresh_token");
    localStorage.removeItem("auth_user_data");
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  const isTokenValid = (token: string): boolean => {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const currentTime = Math.floor(Date.now() / 1000);
      return payload.exp > currentTime;
    } catch (error) {
      return false;
    }
  };

  // 既存の電話番号認証用ログイン（互換性のため）
  const login = (
    accessToken: string,
    newRefreshToken: string,
    newUser: User
  ) => {
    setToken(accessToken);
    setRefreshToken(newRefreshToken);
    setUser(newUser);
    localStorage.setItem("auth_access_token", accessToken);
    localStorage.setItem("auth_refresh_token", newRefreshToken);
    localStorage.setItem("auth_user_data", JSON.stringify(newUser));

    console.log("ユーザーがログインしました:", newUser);
  };

  // Cognitoサインイン
  const cognitoSignIn = async (email: string, password: string) => {
    try {
      try {
        await getCurrentUser();
        return { success: true, message: "すでにログイン済みです" };
      } catch {}
      const signInInput: SignInInput = {
        username: email,
        password: password,
      };

      const { isSignedIn } = await signIn(signInInput);

      if (isSignedIn) {
        // セッション情報を取得
        const session = await fetchAuthSession();
        const currentUser = await getCurrentUser();

        if (session.tokens?.accessToken) {
          const userInfo: User = {
            userId: currentUser.userId,
            email: email,
            givenName: "", // 実際の属性は後で取得
            familyName: "",
            phoneNumber: "",
          };

          setToken(session.tokens.accessToken.toString());
          setRefreshToken(null); // Cognitoでは直接refresh tokenにアクセスしない
          setUser(userInfo);

          console.log("Cognitoログインが成功しました:", userInfo);
          return { success: true, message: "ログインに成功しました" };
        }
      }

      return { success: false, message: "ログインに失敗しました" };
    } catch (error: any) {
      console.error("Cognito sign in error:", error);
      if (error?.name === "UserAlreadyAuthenticatedException") {
        return { success: true, message: "すでにログイン済みです" };
      }
      let message = "ログインに失敗しました";

      if (error.name === "NotAuthorizedException") {
        message = "メールアドレスまたはパスワードが間違っています";
      } else if (error.name === "UserNotConfirmedException") {
        message = "アカウントが確認されていません。メールを確認してください";
      } else if (error.name === "TooManyRequestsException") {
        message = "試行回数が多すぎます。しばらく待ってから再試行してください";
      }

      return { success: false, message };
    }
  };

  // Cognitoサインアップ
  const cognitoSignUp = async (
    email: string,
    password: string,
    givenName: string,
    familyName: string,
    phoneNumber: string
  ) => {
    try {
      const signUpInput: SignUpInput = {
        username: email,
        password: password,
        options: {
          userAttributes: {
            email: email,
            given_name: givenName,
            family_name: familyName,
            phone_number: phoneNumber,
          },
        },
      };

      const { isSignUpComplete, userId } = await signUp(signUpInput);

      if (!isSignUpComplete) {
        return {
          success: true,
          message:
            "確認コードをメールに送信しました。メールを確認してアカウントを有効化してください。",
          requiresConfirmation: true,
        };
      }

      return { success: true, message: "アカウントが作成されました" };
    } catch (error: any) {
      console.error("Cognito sign up error:", error);
      let message = "アカウント作成に失敗しました";

      if (error.name === "UsernameExistsException") {
        message = "このメールアドレスは既に登録されています";
      } else if (error.name === "InvalidPasswordException") {
        message = "パスワードが要件を満たしていません";
      } else if (error.name === "InvalidParameterException") {
        message =
          "入力内容に問題があります。すべての項目を正しく入力してください";
      }

      return { success: false, message };
    }
  };

  // Cognitoサインアップ確認
  const cognitoConfirmSignUp = async (email: string, code: string) => {
    try {
      const confirmSignUpInput: ConfirmSignUpInput = {
        username: email,
        confirmationCode: code,
      };

      await confirmSignUp(confirmSignUpInput);
      return {
        success: true,
        message: "アカウントが確認されました。ログインしてください。",
      };
    } catch (error: any) {
      console.error("Cognito confirm sign up error:", error);
      let message = "確認に失敗しました";

      if (error.name === "CodeMismatchException") {
        message = "確認コードが間違っています";
      } else if (error.name === "ExpiredCodeException") {
        message = "確認コードの有効期限が切れています";
      }

      return { success: false, message };
    }
  };

  // Cognitoサインアウト
  const cognitoSignOut = async () => {
    try {
      console.log("Cognitoサインアウトを実行中...");
      await signOut();
      clearAuthData();
      console.log("Cognitoサインアウトが完了しました");
    } catch (error) {
      console.error("Cognito sign out error:", error);
      // エラーが発生してもローカル状態はクリア
      clearAuthData();
    }
  };

  // 既存のログアウト（互換性のため）
  const logout = async (): Promise<void> => {
    console.log("ユーザーがログアウトしました");

    try {
      // Cognito/Amplify 側のセッションを破棄（これが本丸）
      await signOut();
    } catch (e) {
      // ここで落とさず、アプリ側の状態クリアは必ず実行
      console.warn("signOut failed (continue clearing local auth data):", e);
    } finally {
      // アプリ側の状態・保存データをクリア
      clearAuthData();
    }
  };

  // Cognitoパスワードリセット要求
  const cognitoResetPassword = async (email: string) => {
    try {
      const resetPasswordInput: ResetPasswordInput = {
        username: email,
      };

      await resetPassword(resetPasswordInput);
      return {
        success: true,
        message: "パスワードリセット用のコードをメールに送信しました",
      };
    } catch (error: any) {
      console.error("Cognito reset password error:", error);
      let message = "パスワードリセットに失敗しました";

      if (error.name === "UserNotFoundException") {
        // セキュリティ上の理由で成功メッセージを表示
        message = "パスワードリセット用のコードをメールに送信しました";
      }

      return { success: true, message }; // セキュリティ上常に成功を返す
    }
  };

  // Cognitoパスワードリセット確認
  const cognitoConfirmResetPassword = async (
    email: string,
    code: string,
    newPassword: string
  ) => {
    try {
      const confirmResetPasswordInput: ConfirmResetPasswordInput = {
        username: email,
        confirmationCode: code,
        newPassword: newPassword,
      };

      await confirmResetPassword(confirmResetPasswordInput);
      return { success: true, message: "パスワードが正常に変更されました" };
    } catch (error: any) {
      console.error("Cognito confirm reset password error:", error);
      let message = "パスワード変更に失敗しました";

      if (error.name === "CodeMismatchException") {
        message = "確認コードが間違っています";
      } else if (error.name === "ExpiredCodeException") {
        message = "確認コードの有効期限が切れています";
      } else if (error.name === "InvalidPasswordException") {
        message = "新しいパスワードが要件を満たしていません";
      }

      return { success: false, message };
    }
  };

  // Cognitoサインアップコード再送信
  const cognitoResendSignUpCode = async (email: string) => {
    try {
      await resendSignUpCode({ username: email });
      return { success: true, message: "確認コードを再送信しました" };
    } catch (error: any) {
      console.error("Cognito resend sign up code error:", error);
      return { success: false, message: "確認コードの再送信に失敗しました" };
    }
  };

  const value: AuthContextType = {
    isAuthenticated: !!token,
    token,
    refreshToken,
    user,
    login,
    logout,
    loading,
    cognitoSignIn,
    cognitoSignUp,
    cognitoConfirmSignUp,
    cognitoSignOut,
    cognitoResetPassword,
    cognitoConfirmResetPassword,
    cognitoResendSignUpCode,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
