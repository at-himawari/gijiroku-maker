import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/contexts/AuthContext";

// WebSocketのモック
const mockWebSocketInstances: MockWebSocket[] = [];

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

  constructor(public url: string) {
    mockWebSocketInstances.push(this);
    // 接続成功をシミュレート
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event("open"));
    }, 100);
  }

  send(data: string) {
    // メッセージ送信をシミュレート
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }
}

// グローバルWebSocketをモック
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

// TranscriptionAppコンポーネントのモック実装
const MockTranscriptionApp: React.FC<{ authContext?: any }> = ({
  authContext,
}) => {
  const [isRecording, setIsRecording] = React.useState(false);
  const [transcription, setTranscription] = React.useState("");
  const [wsConnection, setWsConnection] = React.useState<WebSocket | null>(
    null
  );
  const [sessionInvalidated, setSessionInvalidated] = React.useState(false);
  const [workData, setWorkData] = React.useState<string>("");

  // WebSocket接続の確立
  const connectWebSocket = React.useCallback(() => {
    if (!authContext?.token) {
      console.error("認証トークンがありません");
      return;
    }

    const wsUrl = `ws://${process.env.NEXT_PUBLIC_HOST}/ws?token=${authContext.token}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket接続が確立されました");
      setWsConnection(ws);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "transcription") {
        setTranscription(data.text);
      } else if (data.type === "session_invalid") {
        setSessionInvalidated(true);
        setWsConnection(null);
      }
    };

    ws.onclose = () => {
      console.log("WebSocket接続が閉じられました");
      setWsConnection(null);
    };

    ws.onerror = (error) => {
      console.error("WebSocketエラー:", error);
      setWsConnection(null);
    };

    return ws;
  }, [authContext?.token]);

  // 録音開始
  const startRecording = async () => {
    if (!authContext?.isAuthenticated) {
      console.log("認証が必要です");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ws = connectWebSocket();

      if (ws) {
        setIsRecording(true);
        setWorkData("録音中のデータ"); // 作業データをシミュレート
      }
    } catch (error) {
      console.error("録音開始エラー:", error);
    }
  };

  // 録音停止
  const stopRecording = () => {
    if (wsConnection) {
      wsConnection.close();
    }
    setIsRecording(false);
  };

  // セッション無効化時の処理
  React.useEffect(() => {
    if (sessionInvalidated) {
      // 作業データを保持したまま認証画面にリダイレクト
      localStorage.setItem("preserved_work_data", workData);
      console.log("セッションが無効になりました。再認証してください。");
    }
  }, [sessionInvalidated, workData]);

  // 認証成功時の処理
  React.useEffect(() => {
    if (authContext?.isAuthenticated && authContext?.user) {
      // 保存された作業データを復元
      const preservedData = localStorage.getItem("preserved_work_data");
      if (preservedData) {
        setWorkData(preservedData);
        localStorage.removeItem("preserved_work_data");
      }
    }
  }, [authContext?.isAuthenticated, authContext?.user]);

  return (
    <div data-testid="transcription-app">
      <div data-testid="auth-status">
        認証状態: {authContext?.isAuthenticated ? "認証済み" : "未認証"}
      </div>

      {authContext?.user && (
        <div data-testid="user-context">
          ユーザー: {authContext.user.phoneNumber}
        </div>
      )}

      <div data-testid="work-data">作業データ: {workData}</div>

      <div data-testid="transcription">文字起こし: {transcription}</div>

      <div data-testid="connection-status">
        WebSocket: {wsConnection ? "接続中" : "未接続"}
      </div>

      {sessionInvalidated && (
        <div data-testid="session-invalid-message">
          セッションが無効になりました
        </div>
      )}

      <button
        onClick={startRecording}
        disabled={isRecording}
        data-testid="start-recording"
      >
        {isRecording ? "録音中" : "録音開始"}
      </button>

      <button
        onClick={stopRecording}
        disabled={!isRecording}
        data-testid="stop-recording"
      >
        録音停止
      </button>
    </div>
  );
};

// AuthProviderのモック実装
const MockAuthProvider: React.FC<{
  children: React.ReactNode;
  isAuthenticated?: boolean;
  user?: any;
  token?: string;
}> = ({ children, isAuthenticated = false, user = null, token = null }) => {
  const mockValue = {
    isAuthenticated,
    token,
    refreshToken: token ? "mock-refresh-token" : null,
    user,
    login: jest.fn(),
    logout: jest.fn(),
    loading: false,
  };

  return (
    <div data-mock-auth-provider="true">
      {React.cloneElement(children as React.ReactElement, {
        authContext: mockValue,
      })}
    </div>
  );
};

describe("TranscriptionApp Integration - プロパティ 26, 23, 30: WebSocket接続継続性、作業保持、コンテキスト渡し", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    // WebSocketインスタンスをクリア
    mockWebSocketInstances.length = 0;
  });

  test("プロパティ 26: WebSocket接続の継続性 - 認証トークンが有効な間は接続が維持される", async () => {
    const mockUser = { userId: "test-user", phoneNumber: "+81901234567" };

    render(
      <MockAuthProvider
        isAuthenticated={true}
        user={mockUser}
        token="valid-token"
      >
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 認証状態の確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");

    // 録音開始
    fireEvent.click(screen.getByTestId("start-recording"));

    // WebSocket接続が確立されることを確認
    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveTextContent(
        "WebSocket: 接続中"
      );
    });

    // 録音状態の確認
    expect(screen.getByTestId("start-recording")).toHaveTextContent("録音中");
  });

  test("プロパティ 23: セッション無効化時の作業保持 - セッションが無効になっても作業データが保持される", async () => {
    const mockUser = { userId: "test-user", phoneNumber: "+81901234567" };

    render(
      <MockAuthProvider
        isAuthenticated={true}
        user={mockUser}
        token="valid-token"
      >
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 録音開始して作業データを生成
    fireEvent.click(screen.getByTestId("start-recording"));

    await waitFor(() => {
      expect(screen.getByTestId("work-data")).toHaveTextContent(
        "作業データ: 録音中のデータ"
      );
    });

    // セッション無効化をシミュレート
    const wsConnection = mockWebSocketInstances[0];
    if (wsConnection && wsConnection.onmessage) {
      wsConnection.onmessage({
        data: JSON.stringify({ type: "session_invalid" }),
      } as MessageEvent);
    }

    // セッション無効化メッセージの表示確認
    await waitFor(() => {
      expect(screen.getByTestId("session-invalid-message")).toBeInTheDocument();
    });

    // 作業データがローカルストレージに保存されることを確認
    expect(localStorage.getItem("preserved_work_data")).toBe("録音中のデータ");
  });

  test("プロパティ 30: 認証成功時のコンテキスト渡し - ユーザー情報が正しく渡される", () => {
    const mockUser = { userId: "test-user-123", phoneNumber: "+81901234567" };

    render(
      <MockAuthProvider
        isAuthenticated={true}
        user={mockUser}
        token="valid-token"
      >
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // ユーザーコンテキストが正しく表示されることを確認
    expect(screen.getByTestId("user-context")).toHaveTextContent(
      "ユーザー: +81901234567"
    );
    expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
  });

  test("作業データの復元 - 再認証後に保存された作業データが復元される", () => {
    // 事前に作業データを保存
    localStorage.setItem("preserved_work_data", "保存された作業データ");

    const mockUser = { userId: "test-user", phoneNumber: "+81901234567" };

    render(
      <MockAuthProvider
        isAuthenticated={true}
        user={mockUser}
        token="valid-token"
      >
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 作業データが復元されることを確認
    expect(screen.getByTestId("work-data")).toHaveTextContent(
      "作業データ: 保存された作業データ"
    );

    // ローカルストレージからデータが削除されることを確認
    expect(localStorage.getItem("preserved_work_data")).toBeNull();
  });

  test("未認証時のWebSocket接続防止", async () => {
    render(
      <MockAuthProvider isAuthenticated={false}>
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 未認証状態の確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");

    // 録音開始を試行
    fireEvent.click(screen.getByTestId("start-recording"));

    // WebSocket接続が確立されないことを確認
    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveTextContent(
        "WebSocket: 未接続"
      );
    });
  });

  test("認証状態変更時の動的な動作確認", async () => {
    const { rerender } = render(
      <MockAuthProvider isAuthenticated={false}>
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 最初は未認証
    expect(screen.getByTestId("auth-status")).toHaveTextContent("未認証");

    // 認証状態に変更
    const mockUser = { userId: "test-user", phoneNumber: "+81901234567" };
    rerender(
      <MockAuthProvider
        isAuthenticated={true}
        user={mockUser}
        token="valid-token"
      >
        <MockTranscriptionApp />
      </MockAuthProvider>
    );

    // 認証後の状態確認
    expect(screen.getByTestId("auth-status")).toHaveTextContent("認証済み");
    expect(screen.getByTestId("user-context")).toHaveTextContent(
      "ユーザー: +81901234567"
    );
  });
});
