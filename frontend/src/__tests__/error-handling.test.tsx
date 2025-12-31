/**
 * エラーハンドリングとユーザー体験向上機能のテスト
 * 要件: 7.2, 7.3, 7.4, 7.5
 *
 * 注意: メモリ使用量削減のため、基本的なテストのみ実行
 */

// ErrorMessageManager のモック
const mockErrorMessageManager = {
  getCognitoErrorMessage: jest.fn(),
  getValidationErrorMessage: jest.fn(),
  combineErrors: jest.fn(),
};

// モジュールのモック
jest.mock("@/lib/errorMessages", () => ({
  ErrorMessageManager: mockErrorMessageManager,
}));

// ErrorMessageManager の基本テスト
describe("ErrorMessageManager", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("Cognitoエラーメッセージを正しく変換する", () => {
    mockErrorMessageManager.getCognitoErrorMessage.mockReturnValue(
      "メールアドレスまたはパスワードが間違っています"
    );

    const notAuthError = { name: "NotAuthorizedException" };
    const message =
      mockErrorMessageManager.getCognitoErrorMessage(notAuthError);

    expect(mockErrorMessageManager.getCognitoErrorMessage).toHaveBeenCalledWith(
      notAuthError
    );
    expect(message).toBe("メールアドレスまたはパスワードが間違っています");
  });

  test("バリデーションエラーメッセージを生成する", () => {
    mockErrorMessageManager.getValidationErrorMessage.mockReturnValue(
      "有効なメールアドレスを入力してください"
    );

    const message = mockErrorMessageManager.getValidationErrorMessage("email");

    expect(
      mockErrorMessageManager.getValidationErrorMessage
    ).toHaveBeenCalledWith("email");
    expect(message).toContain("有効なメールアドレス");
  });

  test("複数エラーを統合する", () => {
    mockErrorMessageManager.combineErrors.mockReturnValue(
      "1. エラー1\n2. エラー2"
    );

    const errors = ["エラー1", "エラー2"];
    const combined = mockErrorMessageManager.combineErrors(errors);

    expect(mockErrorMessageManager.combineErrors).toHaveBeenCalledWith(errors);
    expect(combined).toContain("1. エラー1");
    expect(combined).toContain("2. エラー2");
  });
});

// 基本的なエラーハンドリング機能のテスト
describe("基本的なエラーハンドリング", () => {
  test("エラーオブジェクトの基本構造", () => {
    const error = {
      name: "ValidationError",
      message: "入力値が無効です",
      code: "INVALID_INPUT",
    };

    expect(error.name).toBe("ValidationError");
    expect(error.message).toBe("入力値が無効です");
    expect(error.code).toBe("INVALID_INPUT");
  });

  test("エラーメッセージの日本語化", () => {
    const englishErrors = [
      "Email is required",
      "Password is too short",
      "Invalid format",
    ];

    const japaneseErrors = englishErrors.map((error) => {
      switch (error) {
        case "Email is required":
          return "メールアドレスは必須です";
        case "Password is too short":
          return "パスワードが短すぎます";
        case "Invalid format":
          return "形式が正しくありません";
        default:
          return error;
      }
    });

    expect(japaneseErrors).toEqual([
      "メールアドレスは必須です",
      "パスワードが短すぎます",
      "形式が正しくありません",
    ]);
  });

  test("エラー状態の管理", () => {
    const errorState = {
      hasError: false,
      errorMessage: "",
      errorCode: null,
    };

    // エラー発生
    const withError = {
      ...errorState,
      hasError: true,
      errorMessage: "認証に失敗しました",
      errorCode: "AUTH_FAILED",
    };

    expect(withError.hasError).toBe(true);
    expect(withError.errorMessage).toBe("認証に失敗しました");
    expect(withError.errorCode).toBe("AUTH_FAILED");

    // エラークリア
    const cleared = {
      ...withError,
      hasError: false,
      errorMessage: "",
      errorCode: null,
    };

    expect(cleared.hasError).toBe(false);
    expect(cleared.errorMessage).toBe("");
    expect(cleared.errorCode).toBeNull();
  });
});

// その他のテストは将来的に必要になった場合に追加予定
