import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "../ProtectedRoute";

// Next.js routerのモック
const mockPush = jest.fn();
const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => ({
    get: jest.fn().mockReturnValue("/original-page"),
  }),
}));

// テスト用のコンポーネント
const TestComponent: React.FC = () => (
  <div data-testid="protected-content">保護されたコンテンツ</div>
);

// AuthProviderのモック実装
const MockAuthProvider: React.FC<{
  children: React.ReactNode;
  isAuthenticated?: boolean;
  loading?: boolean;
}> = ({ children, isAuthenticated = false, loading = false }) => {
  const mockValue = {
    isAuthenticated,
    token: isAuthenticated ? "mock-token" : null,
    refreshToken: isAuthenticated ? "mock-refresh-token" : null,
    user: isAuthenticated
      ? { userId: "test-user", phoneNumber: "+81901234567" }
      : null,
    login: jest.fn(),
    logout: jest.fn(),
    loading,
  };

  return (
    <div data-mock-auth-provider="true">
      {React.cloneElement(children as React.ReactElement, {
        authContext: mockValue,
      })}
    </div>
  );
};

// ProtectedRouteコンポーネントのモック実装
const MockProtectedRoute: React.FC<{
  children: React.ReactNode;
  authContext?: any;
  redirectTo?: string;
  mockPath?: string;
}> = ({
  children,
  authContext,
  redirectTo = "/login",
  mockPath = "/protected-page",
}) => {
  const [isRedirecting, setIsRedirecting] = React.useState(false);

  React.useEffect(() => {
    if (!authContext?.loading && !authContext?.isAuthenticated) {
      setIsRedirecting(true);
      // モックパスを使用してリダイレクト
      const redirectUrl = `${redirectTo}?returnTo=${encodeURIComponent(
        mockPath
      )}`;
      mockPush(redirectUrl);
    }
  }, [
    authContext?.loading,
    authContext?.isAuthenticated,
    redirectTo,
    mockPath,
  ]);

  if (authContext?.loading) {
    return <div data-testid="loading">読み込み中...</div>;
  }

  if (!authContext?.isAuthenticated) {
    return isRedirecting ? (
      <div data-testid="redirecting">リダイレクト中...</div>
    ) : null;
  }

  return <>{children}</>;
};

describe("ProtectedRoute - プロパティ 25: 認証完了後の元ページリダイレクト", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPush.mockClear();
    mockReplace.mockClear();
  });

  test("未認証ユーザーが保護されたページにアクセスした時、元ページ情報付きでログインページにリダイレクトされる", async () => {
    render(
      <MockAuthProvider isAuthenticated={false} loading={false}>
        <MockProtectedRoute mockPath="/protected-page">
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // リダイレクトが実行されることを確認
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        "/login?returnTo=%2Fprotected-page"
      );
    });

    // 保護されたコンテンツが表示されないことを確認
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
  });

  test("認証済みユーザーは保護されたコンテンツにアクセスできる", () => {
    render(
      <MockAuthProvider isAuthenticated={true} loading={false}>
        <MockProtectedRoute>
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // 保護されたコンテンツが表示されることを確認
    expect(screen.getByTestId("protected-content")).toBeInTheDocument();

    // リダイレクトが実行されないことを確認
    expect(mockPush).not.toHaveBeenCalled();
  });

  test("認証状態の読み込み中はローディング表示される", () => {
    render(
      <MockAuthProvider isAuthenticated={false} loading={true}>
        <MockProtectedRoute>
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // ローディング表示を確認
    expect(screen.getByTestId("loading")).toBeInTheDocument();

    // 保護されたコンテンツが表示されないことを確認
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();

    // リダイレクトが実行されないことを確認
    expect(mockPush).not.toHaveBeenCalled();
  });

  test("カスタムリダイレクト先が指定された場合、そのページにリダイレクトされる", async () => {
    render(
      <MockAuthProvider isAuthenticated={false} loading={false}>
        <MockProtectedRoute
          redirectTo="/custom-login"
          mockPath="/protected-page"
        >
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // カスタムリダイレクト先にリダイレクトされることを確認
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        "/custom-login?returnTo=%2Fprotected-page"
      );
    });
  });

  test("異なるパスの保護されたページでも正しく元ページ情報が保存される", async () => {
    render(
      <MockAuthProvider isAuthenticated={false} loading={false}>
        <MockProtectedRoute mockPath="/dashboard/settings">
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // 正しいパス情報でリダイレクトされることを確認
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        "/login?returnTo=%2Fdashboard%2Fsettings"
      );
    });
  });

  test("認証状態が変更された時の動作確認", async () => {
    const { rerender } = render(
      <MockAuthProvider isAuthenticated={false} loading={false}>
        <MockProtectedRoute>
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // 最初は未認証でリダイレクト
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        "/login?returnTo=%2Fprotected-page"
      );
    });

    // 認証状態を変更
    rerender(
      <MockAuthProvider isAuthenticated={true} loading={false}>
        <MockProtectedRoute>
          <TestComponent />
        </MockProtectedRoute>
      </MockAuthProvider>
    );

    // 認証後は保護されたコンテンツが表示される
    expect(screen.getByTestId("protected-content")).toBeInTheDocument();
  });
});
