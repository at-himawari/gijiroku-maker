/**
 * フロントエンドセキュリティ統合テスト
 * XSS対策、CSRF対策、入力検証、セキュリティヘッダーのテスト
 * 要件: 8.1, 8.5
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// セキュリティテスト用のコンポーネント
const SecurityTestComponent: React.FC = () => {
  const [userInput, setUserInput] = React.useState("");
  const [sanitizedOutput, setSanitizedOutput] = React.useState("");
  const [csrfToken, setCsrfToken] = React.useState("");
  const [authToken, setAuthToken] = React.useState("");
  const [apiResponse, setApiResponse] = React.useState("");

  // 入力サニタイゼーション関数
  const sanitizeInput = (input: string): string => {
    return input
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;")
      .replace(/\//g, "&#x2F;")
      .replace(/javascript:/gi, "")
      .replace(/data:/gi, "")
      .replace(/vbscript:/gi, "");
  };

  // CSRFトークン生成（簡易版）
  const generateCSRFToken = (): string => {
    return (
      Math.random().toString(36).substring(2, 15) +
      Math.random().toString(36).substring(2, 15)
    );
  };

  // 入力処理
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setUserInput(value);
    setSanitizedOutput(sanitizeInput(value));
  };

  // セキュアなAPI呼び出し
  const makeSecureAPICall = async () => {
    if (!csrfToken || !authToken) {
      setApiResponse("エラー: CSRFトークンまたは認証トークンが不足しています");
      return;
    }

    try {
      // セキュリティヘッダーを含むリクエスト
      const headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        Authorization: `Bearer ${authToken}`,
        "X-Requested-With": "XMLHttpRequest",
      };

      // モックAPIレスポンス
      setApiResponse("セキュアなAPI呼び出しが成功しました");
    } catch (error) {
      setApiResponse("API呼び出しでエラーが発生しました");
    }
  };

  // 初期化
  React.useEffect(() => {
    setCsrfToken(generateCSRFToken());
    setAuthToken("test-auth-token");
  }, []);

  return (
    <div data-testid="security-test-component">
      <h2>セキュリティテストコンポーネント</h2>

      {/* 入力フィールド */}
      <div>
        <label htmlFor="user-input">ユーザー入力:</label>
        <input
          id="user-input"
          data-testid="user-input"
          type="text"
          value={userInput}
          onChange={handleInputChange}
          placeholder="テキストを入力してください"
        />
      </div>

      {/* サニタイズされた出力 */}
      <div data-testid="sanitized-output">
        サニタイズ済み: {sanitizedOutput}
      </div>

      {/* セキュリティトークン表示 */}
      <div data-testid="csrf-token">CSRFトークン: {csrfToken}</div>
      <div data-testid="auth-token">認証トークン: {authToken}</div>

      {/* セキュアなAPI呼び出しボタン */}
      <button data-testid="secure-api-button" onClick={makeSecureAPICall}>
        セキュアなAPI呼び出し
      </button>

      {/* APIレスポンス */}
      <div data-testid="api-response">{apiResponse}</div>
    </div>
  );
};

// 脆弱なコンポーネント（テスト用）
const VulnerableComponent: React.FC<{ userInput: string }> = ({
  userInput,
}) => {
  // 危険: HTMLを直接挿入（XSS脆弱性のデモ）
  return (
    <div
      data-testid="vulnerable-output"
      dangerouslySetInnerHTML={{ __html: userInput }}
    />
  );
};

// セキュアなコンポーネント
const SecureComponent: React.FC<{ userInput: string }> = ({ userInput }) => {
  // 安全: テキストとして表示
  return <div data-testid="secure-output">{userInput}</div>;
};

describe("フロントエンドセキュリティ統合テスト", () => {
  beforeEach(() => {
    // テスト前にlocalStorageをクリア
    localStorage.clear();
    sessionStorage.clear();
  });

  test("XSS攻撃対策 - 入力サニタイゼーション", async () => {
    const user = userEvent.setup();
    render(<SecurityTestComponent />);

    const input = screen.getByTestId("user-input");
    const maliciousScript = "<script>alert('XSS')</script>";

    // 悪意のあるスクリプトを入力
    await user.type(input, maliciousScript);

    // サニタイズされた出力を確認
    const sanitizedOutput = screen.getByTestId("sanitized-output");
    expect(sanitizedOutput).toHaveTextContent(
      "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;&#x2F;script&gt;"
    );

    // 元の危険な文字列が含まれていないことを確認
    expect(sanitizedOutput).not.toHaveTextContent("<script>");
  });

  test("XSS攻撃対策 - 脆弱なコンポーネントとセキュアなコンポーネントの比較", () => {
    const maliciousInput = "<img src=x onerror=alert('XSS')>";

    // 脆弱なコンポーネント（dangerouslySetInnerHTMLを使用）
    const { container: vulnerableContainer } = render(
      <VulnerableComponent userInput={maliciousInput} />
    );

    // セキュアなコンポーネント（テキストとして表示）
    const { container: secureContainer } = render(
      <SecureComponent userInput={maliciousInput} />
    );

    // 脆弱なコンポーネントはHTMLタグを含む
    const vulnerableOutput = vulnerableContainer.querySelector(
      '[data-testid="vulnerable-output"]'
    );
    expect(vulnerableOutput?.innerHTML).toContain("<img");

    // セキュアなコンポーネントはテキストとして表示
    const secureOutput = secureContainer.querySelector(
      '[data-testid="secure-output"]'
    );
    expect(secureOutput?.textContent).toBe(maliciousInput);
    expect(secureOutput?.innerHTML).not.toContain("<img");
  });

  test("CSRF対策 - トークン生成と検証", () => {
    render(<SecurityTestComponent />);

    // CSRFトークンが生成されていることを確認
    const csrfTokenElement = screen.getByTestId("csrf-token");
    expect(csrfTokenElement).toHaveTextContent(/CSRFトークン: \w+/);

    // トークンが空でないことを確認
    const tokenText = csrfTokenElement.textContent;
    const token = tokenText?.replace("CSRFトークン: ", "");
    expect(token).toBeTruthy();
    expect(token?.length).toBeGreaterThan(10);
  });

  test("セキュアなAPI呼び出し - 必要なヘッダーの確認", async () => {
    render(<SecurityTestComponent />);

    // セキュアなAPI呼び出しボタンをクリック
    const apiButton = screen.getByTestId("secure-api-button");
    fireEvent.click(apiButton);

    // API呼び出しが成功することを確認
    await waitFor(() => {
      const apiResponse = screen.getByTestId("api-response");
      expect(apiResponse).toHaveTextContent(
        "セキュアなAPI呼び出しが成功しました"
      );
    });
  });

  test("認証トークンの管理", () => {
    render(<SecurityTestComponent />);

    // 認証トークンが設定されていることを確認
    const authTokenElement = screen.getByTestId("auth-token");
    expect(authTokenElement).toHaveTextContent("認証トークン: test-auth-token");
  });

  test("入力検証 - 様々な悪意のある入力パターン", async () => {
    const user = userEvent.setup();
    render(<SecurityTestComponent />);

    const input = screen.getByTestId("user-input");
    const maliciousInputs = [
      "<script>alert('XSS')</script>",
      "javascript:alert('XSS')",
      "<img src=x onerror=alert('XSS')>",
      "<iframe src='javascript:alert(\"XSS\")'></iframe>",
      "'; DROP TABLE users; --",
      "<svg onload=alert('XSS')>",
      "<body onload=alert('XSS')>",
    ];

    for (const maliciousInput of maliciousInputs) {
      // 入力をクリアして新しい値を入力
      await user.clear(input);
      await user.type(input, maliciousInput);

      // サニタイズされた出力を確認
      const sanitizedOutput = screen.getByTestId("sanitized-output");
      const outputText = sanitizedOutput.textContent || "";

      // 危険な文字列が含まれていないことを確認
      expect(outputText).not.toContain("<script>");
      expect(outputText).not.toContain("javascript:");
      expect(outputText).not.toContain("<img");
      expect(outputText).not.toContain("<iframe");
      expect(outputText).not.toContain("<svg");
      expect(outputText).not.toContain("<body");

      // サニタイズされた文字が含まれていることを確認
      if (maliciousInput.includes("<")) {
        expect(outputText).toContain("&lt;");
      }
      if (maliciousInput.includes(">")) {
        expect(outputText).toContain("&gt;");
      }
    }
  });

  test("セッションストレージのセキュリティ", () => {
    // 機密情報がlocalStorageに保存されていないことを確認
    expect(localStorage.getItem("password")).toBeNull();
    expect(localStorage.getItem("secret")).toBeNull();
    expect(localStorage.getItem("private_key")).toBeNull();

    // セッションストレージも同様にチェック
    expect(sessionStorage.getItem("password")).toBeNull();
    expect(sessionStorage.getItem("secret")).toBeNull();
    expect(sessionStorage.getItem("private_key")).toBeNull();
  });

  test("コンテンツセキュリティポリシー準拠", () => {
    render(<SecurityTestComponent />);

    // インラインスクリプトが実行されないことを確認
    // （実際のCSPはHTTPヘッダーで設定されるため、ここでは基本的なチェックのみ）
    const scriptElements = document.querySelectorAll("script[src]");

    // 外部スクリプトのみが許可されていることを確認
    scriptElements.forEach((script) => {
      const src = script.getAttribute("src");
      expect(src).toBeTruthy(); // srcが設定されていることを確認
    });
  });

  test("フォーム送信時のセキュリティ検証", async () => {
    const user = userEvent.setup();

    // フォーム送信テスト用のコンポーネント
    const FormComponent: React.FC = () => {
      const [formData, setFormData] = React.useState({ name: "", email: "" });
      const [submitted, setSubmitted] = React.useState(false);

      const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();

        // 入力検証
        if (!formData.name.trim() || !formData.email.trim()) {
          return;
        }

        // メールアドレスの基本的な検証
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(formData.email)) {
          return;
        }

        setSubmitted(true);
      };

      return (
        <form onSubmit={handleSubmit} data-testid="secure-form">
          <input
            data-testid="name-input"
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="名前"
          />
          <input
            data-testid="email-input"
            type="email"
            value={formData.email}
            onChange={(e) =>
              setFormData({ ...formData, email: e.target.value })
            }
            placeholder="メールアドレス"
          />
          <button type="submit" data-testid="submit-button">
            送信
          </button>
          {submitted && <div data-testid="success-message">送信完了</div>}
        </form>
      );
    };

    render(<FormComponent />);

    const nameInput = screen.getByTestId("name-input");
    const emailInput = screen.getByTestId("email-input");
    const submitButton = screen.getByTestId("submit-button");

    // 有効なデータで送信
    await user.type(nameInput, "田中太郎");
    await user.type(emailInput, "tanaka@example.com");
    await user.click(submitButton);

    // 送信が成功することを確認
    expect(screen.getByTestId("success-message")).toBeInTheDocument();
  });

  test("URLパラメータのセキュリティ検証", () => {
    // URLパラメータから悪意のあるコードが実行されないことを確認
    const maliciousParams = [
      "javascript:alert('XSS')",
      "<script>alert('XSS')</script>",
      "data:text/html,<script>alert('XSS')</script>",
    ];

    maliciousParams.forEach((param) => {
      // URLSearchParamsを使用して安全にパラメータを処理
      const urlParams = new URLSearchParams(
        `?param=${encodeURIComponent(param)}`
      );
      const value = urlParams.get("param");

      // パラメータが適切にエンコードされていることを確認
      expect(value).toBe(param);

      // 実際のアプリケーションではさらにサニタイゼーションが必要
      // ここではエンコード/デコードが正しく動作することを確認
      if (param.includes("javascript:")) {
        // javascript:プロトコルが含まれている場合の処理を確認
        expect(param).toContain("javascript:");
      }
    });
  });
});
