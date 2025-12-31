"use client";

import { useState, useCallback } from "react";

export interface LoadingState {
  isLoading: boolean;
  loadingMessage?: string;
  progress?: number;
}

/**
 * ローディング状態管理用カスタムフック
 * 要件: 7.4 - ローディング状態管理
 */
export function useLoadingState(initialMessage?: string) {
  const [state, setState] = useState<LoadingState>({
    isLoading: false,
    loadingMessage: initialMessage,
    progress: undefined,
  });

  // ローディング開始
  const startLoading = useCallback((message?: string, progress?: number) => {
    setState({
      isLoading: true,
      loadingMessage: message,
      progress,
    });
  }, []);

  // ローディング停止
  const stopLoading = useCallback(() => {
    setState({
      isLoading: false,
      loadingMessage: undefined,
      progress: undefined,
    });
  }, []);

  // ローディングメッセージを更新
  const updateMessage = useCallback((message: string) => {
    setState((prev) => ({
      ...prev,
      loadingMessage: message,
    }));
  }, []);

  // プログレスを更新
  const updateProgress = useCallback((progress: number) => {
    setState((prev) => ({
      ...prev,
      progress: Math.max(0, Math.min(100, progress)),
    }));
  }, []);

  // 非同期操作をラップする関数
  const withLoading = useCallback(
    async <T>(operation: () => Promise<T>, message?: string): Promise<T> => {
      try {
        startLoading(message);
        const result = await operation();
        return result;
      } finally {
        stopLoading();
      }
    },
    [startLoading, stopLoading]
  );

  return {
    ...state,
    startLoading,
    stopLoading,
    updateMessage,
    updateProgress,
    withLoading,
  };
}
