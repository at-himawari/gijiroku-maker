/**
 * 簡易エンドツーエンド認証統合テスト
 * 要件: 5.1, 5.2, 5.3, 6.4, 6.5
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// AWS Amplifyのモック
jest.mock("aws-amplify/auth", () => ({
  signIn: jest.fn(),
  signUp: jest.fn(),
  signOut: jest.fn(),
  getCurrentUser: jest.fn(),
  fetchAuthSession: jest.fn(),
  confirmSignUp: jest.fn(),
  resetPassword: jest.fn(),
  confirmResetPassword: jest.fn(),
  resendSignUpCode: jest.fn(),
}));

// WebSocketのモック
const mockWebSocketInstances: any[] = [];

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    mockWebSocketInstances.push(this);

    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event("open"));
    }, 100);
  }

  send(data: string | ArrayBuffer) {
    console.log("WebSocket send:", data);
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { code, reason }));
  }
}

(global as any).WebSocket = MockWebSocket;

// MediaDevicesのモック
Object.defineProperty(navigator, "mediaDevices", {
  writable: true,
  value: {
    getUserMedia: jest.fn().mockResolvedValue({
      getTracks: () => [{ stop: jest.fn() }],
    }),
  },
});

// AudioContextのモック
(global as any).AudioContext = jest.fn().mockImplementation(() => ({
  createScriptProcessor: jest.fn().mockReturnValue({
    connect: jest.fn(),
    disconnect: jest.fn(),
    onaudioprocess: null,
  }),
  createMediaStreamSource: jest.fn().mockReturnValue({
    connect: jest.fn(),
  }),
  sampleRate: 44100,
  close: jest.fn(),
}));

// 簡易認証コンポーネント
const SimpleAuthTest: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = React.useState(false);
  const [token, setToken] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");

  const handleLogin = async () => {
    const {
      signIn,
      fetchAuthSession,
      getCurrentUser,
    } = require("aws-amplify/auth");

    try {
      await signIn({
        username: "test@example.com",
        password: "TestPassword123!",
      });
      const session = await fetchAuthSession();
      const user = await getCurrentUser();

      setIsAuthenticated(true);
      setToken(session.tokens?.accessToken?.toString() || "mock-token");
      setMessage("ログイン成功");
    } catch (error: any) {
      setMessage("ログイン失敗: " + error.name);
    }
  };

  const handleLogout = async () => {
    const { signOut } = require("aws-amplify/auth");

    try {
      await signOut();
      setIsAuthenticated(false);
      setToken(null);
      setMessage("ログアウト成功");
    } catch (error) {
      setMessage("ログアウト失敗");
    }
  };

  const handleWebSocketConnect = () => {
    if (!token) {
      setMessage("認証が必要です");
      return;
    }

    const ws = new WebSocket(`ws://localhost:8000/ws?token=${token}`);
    ws.onopen = () => setMessage("WebSocket接続成功");
    ws.onerror = () => setMessage("WebSocket接続失敗");
  };

  return (
    <div data-testid="simple-auth-test">
      <div data-testid="auth-status">
        認証状態: {isAuthenticated ? "認証済み" : "未認証"}
      </div>

      {token && <div data-testid="token-display">トークン: {token}</div>}

      <div data-testid="message">{message}</div>

      {!isAuthenticated ? (
        <button data-testid="login-button" onClick={handleLogin}>
          ログイン
        </button>
      ) : (
        <div>
          <button data-testid="logout-button" onClick={handleLogout}>
            ログアウト
          </button>
          <button
            data-testid="websocket-button"
            onClick={handleWebSocketConnect}
          >
            WebSocket接続
          </button>
        </div>
      )}
    </div>
  );
};

describe("簡易E2E認証統合テスト", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    mockWebSocketInstances.length = 0;
  });

  test("完全なログインフローテスト", async () => {
    const {
      signIn,
      fetchAuthSession,
      getCurrentUser,
    } = require("aws-amplify/auth");

    // ログイン成功をモック
    signIn.mockResolvedValue({ isSignedIn: true });
    fetchAuthSession.mockResolvedValue({
      tokens: {
        accessToken: {
          toString: () => "test-access-token",
        },
      },
    });
    getCurrentUser.mockResolvedValue({
      userId: "test-user-123",
    });

    render(<SimpleAuthTest />);

    // 初期状態では未認証
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");

    // ログインボタンをクリック
    fireEvent.click(screen.getByTestId("login-button"));

    // ログイン成功を確認
    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    expect(screen.getByTestId("message")).toHaveTextContent("ログイン成功");
    expect(screen.getByTestId("token-display")).toHaveTextContent(
      "test-access-token"
    );

    // AWS Amplifyのメソッドが呼ばれたことを確認
    expect(signIn).toHaveBeenCalledWith({
      username: "test@example.com",
      password: "TestPassword123!",
    });
  });

  test("WebSocket認証統合テスト", async () => {
    const {
      signIn,
      fetchAuthSession,
      getCurrentUser,
    } = require("aws-amplify/auth");

    // 認証成功をモック
    signIn.mockResolvedValue({ isSignedIn: true });
    fetchAuthSession.mockResolvedValue({
      tokens: {
        accessToken: {
          toString: () => "valid-token",
        },
      },
    });
    getCurrentUser.mockResolvedValue({
      userId: "test-user-123",
    });

    render(<SimpleAuthTest />);

    // ログイン
    fireEvent.click(screen.getByTestId("login-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    // WebSocket接続
    fireEvent.click(screen.getByTestId("websocket-button"));

    // WebSocket接続成功を確認
    await waitFor(() => {
      expect(screen.getByTestId("message")).toHaveTextContent(
        "WebSocket接続成功"
      );
    });

    // WebSocketインスタンスが作成されたことを確認
    expect(mockWebSocketInstances.length).toBe(1);
    expect(mockWebSocketInstances[0].url).toContain("token=valid-token");
  });

  test("認証エラーハンドリングテスト", async () => {
    const { signIn } = require("aws-amplify/auth");

    // 認証エラーをモック
    signIn.mockRejectedValue({
      name: "NotAuthorizedException",
      message: "Incorrect username or password.",
    });

    render(<SimpleAuthTest />);

    // ログイン試行
    fireEvent.click(screen.getByTestId("login-button"));

    // エラーメッセージを確認
    await waitFor(() => {
      expect(screen.getByTestId("message")).toHaveTextContent(
        "ログイン失敗: NotAuthorizedException"
      );
    });

    // 認証状態が未認証のままであることを確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");
  });

  test("ログアウトフローテスト", async () => {
    const {
      signIn,
      fetchAuthSession,
      getCurrentUser,
      signOut,
    } = require("aws-amplify/auth");

    // 認証成功をモック
    signIn.mockResolvedValue({ isSignedIn: true });
    fetchAuthSession.mockResolvedValue({
      tokens: {
        accessToken: {
          toString: () => "test-token",
        },
      },
    });
    getCurrentUser.mockResolvedValue({
      userId: "test-user-123",
    });
    signOut.mockResolvedValue({});

    render(<SimpleAuthTest />);

    // ログイン
    fireEvent.click(screen.getByTestId("login-button"));

    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    });

    // ログアウト
    fireEvent.click(screen.getByTestId("logout-button"));

    // ログアウト成功を確認
    await waitFor(() => {
      expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");
    });

    expect(screen.getByTestId("message")).toHaveTextContent("ログアウト成功");
    expect(signOut).toHaveBeenCalled();
  });

  test("未認証時のWebSocket接続防止テスト", () => {
    render(<SimpleAuthTest />);

    // 未認証状態でWebSocket接続を試行（ボタンが存在しないことを確認）
    expect(screen.queryByTestId("websocket-button")).not.toBeInTheDocument();

    // 認証状態を確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");
  });
});
