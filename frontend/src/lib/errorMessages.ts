/**
 * エラーメッセージ管理クラス
 * 認証関連のエラーメッセージを一元管理する
 */
export class ErrorMessageManager {
  /**
   * バリデーションエラーメッセージを取得
   */
  static getValidationErrorMessage(field: string): string {
    const messages: Record<string, string> = {
      email: "有効なメールアドレスを入力してください",
      password: "パスワードを入力してください",
      phoneNumber: "有効な電話番号を入力してください（例: 090-1234-5678）",
      givenName: "名前を入力してください",
      familyName: "姓を入力してください",
      confirmPassword: "パスワード確認を入力してください",
    };
    return messages[field] || "入力内容を確認してください";
  }

  /**
   * Cognitoエラーメッセージを取得
   */
  static getCognitoErrorMessage(error: any): string {
    if (!error) return "認証エラーが発生しました";

    const errorName = error.name || error.code;
    const errorMessages: Record<string, string> = {
      NotAuthorizedException: "メールアドレスまたはパスワードが間違っています",
      UserNotConfirmedException:
        "アカウントが確認されていません。メールを確認してください",
      TooManyRequestsException:
        "試行回数が多すぎます。しばらく待ってから再試行してください",
      UsernameExistsException: "このメールアドレスは既に登録されています",
      InvalidPasswordException: "パスワードが要件を満たしていません",
      InvalidParameterException:
        "入力内容に問題があります。すべての項目を正しく入力してください",
      CodeMismatchException: "確認コードが間違っています",
      ExpiredCodeException: "確認コードの有効期限が切れています",
      UserNotFoundException: "ユーザーが見つかりません",
      LimitExceededException:
        "制限を超えました。しばらく待ってから再試行してください",
    };

    return (
      errorMessages[errorName] || error.message || "認証エラーが発生しました"
    );
  }

  /**
   * 成功メッセージを取得
   */
  static getSuccessMessage(action: string): string {
    const messages: Record<string, string> = {
      login: "ログインに成功しました",
      register: "アカウントが作成されました",
      confirm: "アカウントが確認されました",
      resendCode: "確認コードを再送信しました",
      resetPassword: "パスワードリセット用のコードをメールに送信しました",
      confirmResetPassword: "パスワードが正常に変更されました",
    };
    return messages[action] || "操作が完了しました";
  }

  /**
   * ローディングメッセージを取得
   */
  static getLoadingMessage(action: string): string {
    const messages: Record<string, string> = {
      login: "ログイン中...",
      register: "アカウント作成中...",
      confirm: "確認中...",
      resendCode: "再送信中...",
      resetPassword: "送信中...",
      confirmResetPassword: "変更中...",
    };
    return messages[action] || "処理中...";
  }

  /**
   * 複数のエラーメッセージを結合
   */
  static combineErrors(errors: (string | null)[]): string {
    const validErrors = errors.filter((error): error is string => !!error);
    return validErrors.join("\n");
  }
}
