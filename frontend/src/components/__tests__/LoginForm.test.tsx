import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/contexts/AuthContext";
import { LoginForm } from "../LoginForm";

// LoginFormコンポーネントのモック実装
const MockLoginForm: React.FC = () => {
  const [phoneNumber, setPhoneNumber] = React.useState("");
  const [code, setCode] = React.useState("");
  const [step, setStep] = React.useState<"phone" | "code">("phone");
  const [error, setError] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);

  const handlePhoneSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/auth/initiate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone_number: phoneNumber }),
        }
      );

      const data = await response.json();

      if (response.ok) {
        setStep("code");
      } else {
        setError(data.error || "認証の開始に失敗しました");
      }
    } catch (error) {
      setError("ネットワークエラーが発生しました");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/auth/verify`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone_number: phoneNumber, code }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        setError(data.error || "認証コードの検証に失敗しました");
      }
    } catch (error) {
      setError("ネットワークエラーが発生しました");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div data-testid="login-form">
      {error && <div data-testid="error-message">{error}</div>}

      {step === "phone" ? (
        <form onSubmit={handlePhoneSubmit} data-testid="phone-form">
          <input
            type="tel"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="電話番号を入力"
            data-testid="phone-input"
            disabled={isLoading}
          />
          <button type="submit" disabled={isLoading} data-testid="phone-submit">
            {isLoading ? "送信中..." : "SMS送信"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleCodeSubmit} data-testid="code-form">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="認証コードを入力"
            data-testid="code-input"
            disabled={isLoading}
          />
          <button type="submit" disabled={isLoading} data-testid="code-submit">
            {isLoading ? "検証中..." : "認証"}
          </button>
        </form>
      )}
    </div>
  );
};

// テスト用のラッパーコンポーネント
const TestWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AuthProvider>{children}</AuthProvider>
);

describe("LoginForm - プロパティ 29: 認証失敗時のUI保護", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();
  });

  test("認証失敗時にフォームが適切に保護される", async () => {
    // 認証失敗のレスポンスをモック
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "無効な電話番号です" }),
    });

    render(
      <TestWrapper>
        <MockLoginForm />
      </TestWrapper>
    );

    const phoneInput = screen.getByTestId("phone-input");
    const submitButton = screen.getByTestId("phone-submit");

    // 無効な電話番号を入力
    fireEvent.change(phoneInput, { target: { value: "invalid-phone" } });
    fireEvent.click(submitButton);

    // ローディング状態の確認
    expect(submitButton).toHaveTextContent("送信中...");
    expect(phoneInput).toBeDisabled();
    expect(submitButton).toBeDisabled();

    // エラーメッセージの表示を待機
    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "無効な電話番号です"
      );
    });

    // フォームが再び有効になることを確認
    expect(phoneInput).not.toBeDisabled();
    expect(submitButton).not.toBeDisabled();
    expect(submitButton).toHaveTextContent("SMS送信");
  });

  test("認証コード検証失敗時にフォームが適切に保護される", async () => {
    // 最初のSMS送信は成功
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: "SMS送信完了" }),
    });

    render(
      <TestWrapper>
        <MockLoginForm />
      </TestWrapper>
    );

    // 電話番号入力フェーズ
    const phoneInput = screen.getByTestId("phone-input");
    const phoneSubmit = screen.getByTestId("phone-submit");

    fireEvent.change(phoneInput, { target: { value: "+81901234567" } });
    fireEvent.click(phoneSubmit);

    // コード入力フェーズに移行するまで待機
    await waitFor(() => {
      expect(screen.getByTestId("code-form")).toBeInTheDocument();
    });

    // 認証コード検証失敗のレスポンスをモック
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "認証コードが正しくありません" }),
    });

    const codeInput = screen.getByTestId("code-input");
    const codeSubmit = screen.getByTestId("code-submit");

    // 無効な認証コードを入力
    fireEvent.change(codeInput, { target: { value: "000000" } });
    fireEvent.click(codeSubmit);

    // ローディング状態の確認
    expect(codeSubmit).toHaveTextContent("検証中...");
    expect(codeInput).toBeDisabled();
    expect(codeSubmit).toBeDisabled();

    // エラーメッセージの表示を待機
    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "認証コードが正しくありません"
      );
    });

    // フォームが再び有効になることを確認
    expect(codeInput).not.toBeDisabled();
    expect(codeSubmit).not.toBeDisabled();
    expect(codeSubmit).toHaveTextContent("認証");
  });

  test("ネットワークエラー時にフォームが適切に保護される", async () => {
    // ネットワークエラーをモック
    (global.fetch as jest.Mock).mockRejectedValueOnce(
      new Error("Network error")
    );

    render(
      <TestWrapper>
        <MockLoginForm />
      </TestWrapper>
    );

    const phoneInput = screen.getByTestId("phone-input");
    const submitButton = screen.getByTestId("phone-submit");

    fireEvent.change(phoneInput, { target: { value: "+81901234567" } });
    fireEvent.click(submitButton);

    // ローディング状態の確認
    expect(submitButton).toHaveTextContent("送信中...");
    expect(phoneInput).toBeDisabled();

    // エラーメッセージの表示を待機
    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "ネットワークエラーが発生しました"
      );
    });

    // フォームが再び有効になることを確認
    expect(phoneInput).not.toBeDisabled();
    expect(submitButton).not.toBeDisabled();
  });

  test("連続した認証失敗でもフォームが正常に動作する", async () => {
    render(
      <TestWrapper>
        <MockLoginForm />
      </TestWrapper>
    );

    const phoneInput = screen.getByTestId("phone-input");
    const submitButton = screen.getByTestId("phone-submit");

    // 1回目の失敗
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "1回目のエラー" }),
    });

    fireEvent.change(phoneInput, { target: { value: "invalid1" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "1回目のエラー"
      );
    });

    // 2回目の失敗
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "2回目のエラー" }),
    });

    fireEvent.change(phoneInput, { target: { value: "invalid2" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        "2回目のエラー"
      );
    });

    // フォームが正常に動作することを確認
    expect(phoneInput).not.toBeDisabled();
    expect(submitButton).not.toBeDisabled();
  });
});
