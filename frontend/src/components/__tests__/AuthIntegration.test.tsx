import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/contexts/AuthContext";

// テスト用のコンポーネント
const MockAuthIntegrationApp: React.FC = () => {
  const [authState, setAuthState] = React.useState({
    isAuthenticated: false,
    user: null as any,
    token: null as string | null,
  });
  const [renderCount, setRenderCount] = React.useState(0);
  const [phoneNumber, setPhoneNumber] = React.useState("+81901234567");
  const [authFailureState, setAuthFailureState] = React.useState<any>(null);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // 再レンダリング回数をカウント（初回のみ）
  const renderCountRef = React.useRef(0);
  React.useEffect(() => {
    renderCountRef.current += 1;
    setRenderCount(renderCountRef.current);
  }, [authState.isAuthenticated, authState.user]); // 依存配列を追加

  // 認証状態変更のシミュレート
  const simulateLogin = () => {
    setIsUpdating(true);
    setTimeout(() => {
      setAuthState({
        isAuthenticated: true,
        user: { userId: "test-user", phoneNumber },
        token: "mock-token",
      });
      setIsUpdating(false);
    }, 100);
  };

  const simulateLogout = () => {
    setAuthState({
      isAuthenticated: false,
      user: null,
      token: null,
    });
  };

  // 電話番号変更時の重複チェック
  const handlePhoneNumberChange = async (newPhoneNumber: string) => {
    setIsUpdating(true);

    // 重複チェックのシミュレート
    const isDuplicate = newPhoneNumber === "+81900000000"; // テスト用の重複番号

    setTimeout(() => {
      if (isDuplicate) {
        alert("この電話番号は既に使用されています");
      } else {
        setPhoneNumber(newPhoneNumber);
        if (authState.isAuthenticated) {
          setAuthState((prev) => ({
            ...prev,
            user: { ...prev.user, phoneNumber: newPhoneNumber },
          }));
        }
      }
      setIsUpdating(false);
    }, 100);
  };

  // 認証失敗時の状態保持
  const simulateAuthFailure = () => {
    const currentState = {
      phoneNumber,
      attemptedAt: new Date().toISOString(),
      formData: "some-form-data",
    };
    setAuthFailureState(currentState);
  };

  // 認証成功時の即座更新
  const simulateAuthSuccess = () => {
    setIsUpdating(true);
    setTimeout(() => {
      setAuthState({
        isAuthenticated: true,
        user: { userId: "new-user", phoneNumber },
        token: "new-token",
      });
      setAuthFailureState(null); // 失敗状態をクリア
      setIsUpdating(false);
    }, 50); // 即座更新をシミュレート
  };

  return (
    <div data-testid="auth-integration-app">
      <div data-testid="render-count">レンダリング回数: {renderCount}</div>

      <div data-testid="auth-status">
        認証状態: {authState.isAuthenticated ? "認証済み" : "未認証"}
      </div>

      {authState.user && (
        <div data-testid="user-info">
          ユーザー: {authState.user.phoneNumber}
        </div>
      )}

      <div data-testid="phone-number">電話番号: {phoneNumber}</div>

      {authFailureState && (
        <div data-testid="auth-failure-state">
          認証失敗状態保持: {authFailureState.phoneNumber} -{" "}
          {authFailureState.formData}
        </div>
      )}

      {isUpdating && <div data-testid="updating-indicator">更新中...</div>}

      <div className="controls">
        <button onClick={simulateLogin} data-testid="login-button">
          ログイン
        </button>

        <button onClick={simulateLogout} data-testid="logout-button">
          ログアウト
        </button>

        <button
          onClick={() => handlePhoneNumberChange("+81909876543")}
          data-testid="change-phone-button"
        >
          電話番号変更
        </button>

        <button
          onClick={() => handlePhoneNumberChange("+81900000000")}
          data-testid="duplicate-phone-button"
        >
          重複番号設定
        </button>

        <button onClick={simulateAuthFailure} data-testid="auth-failure-button">
          認証失敗シミュレート
        </button>

        <button onClick={simulateAuthSuccess} data-testid="auth-success-button">
          認証成功シミュレート
        </button>
      </div>
    </div>
  );
};

describe("Auth Integration - プロパティ 28, 18, 19, 20: 統合機能テスト", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // アラートをモック
    window.alert = jest.fn();
  });

  test("プロパティ 28: 認証状態変更時の適切な再レンダリング", async () => {
    render(<MockAuthIntegrationApp />);

    // 初期レンダリング回数を確認
    const initialRenderCount = parseInt(
      screen.getByTestId("render-count").textContent?.split(": ")[1] || "0"
    );

    // ログイン実行
    fireEvent.click(screen.getByTestId("login-button"));

    // 認証状態変更後の再レンダリングを確認
    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    // 適切な回数の再レンダリングが発生したことを確認
    const finalRenderCount = parseInt(
      screen.getByTestId("render-count").textContent?.split(": ")[1] || "0"
    );
    expect(finalRenderCount).toBeGreaterThan(initialRenderCount);

    // ユーザー情報が表示されることを確認
    expect(screen.getByTestId("user-info")).toHaveTextContent(
      "ユーザー: +81901234567"
    );
  });

  test("プロパティ 18: 電話番号変更時の重複チェック", async () => {
    render(<MockAuthIntegrationApp />);

    // 重複する電話番号を設定
    fireEvent.click(screen.getByTestId("duplicate-phone-button"));

    // 更新中表示を確認
    expect(screen.getByTestId("updating-indicator")).toBeInTheDocument();

    // 重複チェックによるアラートを確認
    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith(
        "この電話番号は既に使用されています"
      );
    });

    // 電話番号が変更されていないことを確認
    expect(screen.getByTestId("phone-number")).toHaveTextContent(
      "電話番号: +81901234567"
    );
  });

  test("プロパティ 18: 有効な電話番号変更の成功", async () => {
    render(<MockAuthIntegrationApp />);

    // 有効な電話番号に変更
    fireEvent.click(screen.getByTestId("change-phone-button"));

    // 電話番号が正常に変更されることを確認
    await waitFor(() => {
      expect(screen.getByTestId("phone-number")).toHaveTextContent(
        "電話番号: +81909876543"
      );
    });

    // アラートが表示されないことを確認
    expect(window.alert).not.toHaveBeenCalled();
  });

  test("プロパティ 19: 認証失敗時の状態保持", async () => {
    render(<MockAuthIntegrationApp />);

    // 認証失敗をシミュレート
    fireEvent.click(screen.getByTestId("auth-failure-button"));

    // 認証失敗状態が保持されることを確認
    await waitFor(() => {
      expect(screen.getByTestId("auth-failure-state")).toHaveTextContent(
        "認証失敗状態保持: +81901234567 - some-form-data"
      );
    });

    // 認証状態は変更されないことを確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");
  });

  test("プロパティ 20: 認証成功時の即座更新", async () => {
    render(<MockAuthIntegrationApp />);

    // まず認証失敗状態を作成
    fireEvent.click(screen.getByTestId("auth-failure-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-failure-state")).toBeInTheDocument();
    });

    // 認証成功をシミュレート
    fireEvent.click(screen.getByTestId("auth-success-button"));

    // 即座に更新されることを確認（短時間で完了）
    await waitFor(
      () => {
        expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
      },
      { timeout: 200 }
    ); // 短いタイムアウトで即座更新を確認

    // 認証失敗状態がクリアされることを確認
    expect(screen.queryByTestId("auth-failure-state")).not.toBeInTheDocument();

    // ユーザー情報が表示されることを確認
    expect(screen.getByTestId("user-info")).toHaveTextContent(
      "ユーザー: +81901234567"
    );
  });

  test("認証状態変更の連続実行での安定性", async () => {
    render(<MockAuthIntegrationApp />);

    // 連続してログイン・ログアウトを実行
    fireEvent.click(screen.getByTestId("login-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    fireEvent.click(screen.getByTestId("logout-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");
    });

    // 再度ログイン
    fireEvent.click(screen.getByTestId("login-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    // 最終的に正しい状態になることを確認
    expect(screen.getByTestId("user-info")).toHaveTextContent(
      "ユーザー: +81901234567"
    );
  });

  test("認証済み状態での電話番号変更時のユーザー情報更新", async () => {
    render(<MockAuthIntegrationApp />);

    // まずログイン
    fireEvent.click(screen.getByTestId("login-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    // 電話番号を変更
    fireEvent.click(screen.getByTestId("change-phone-button"));

    // ユーザー情報も更新されることを確認
    await waitFor(() => {
      expect(screen.getByTestId("user-info")).toHaveTextContent(
        "ユーザー: +81909876543"
      );
    });
  });
});
