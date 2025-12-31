"use client";

import { useState, useEffect, useCallback } from "react";

/**
 * フォーム入力状態をローカルストレージに保持するカスタムフック
 * 要件: 7.5 - フォーム入力状態保持
 */
export function useFormPersistence<T extends Record<string, any>>(
  key: string,
  initialValues: T,
  options: {
    excludeFields?: (keyof T)[];
    clearOnSubmit?: boolean;
  } = {}
) {
  const { excludeFields = [], clearOnSubmit = true } = options;
  const [values, setValues] = useState<T>(initialValues);
  const [isLoaded, setIsLoaded] = useState(false);

  // ローカルストレージから値を復元
  useEffect(() => {
    try {
      const savedData = localStorage.getItem(`form_${key}`);
      if (savedData) {
        const parsedData = JSON.parse(savedData);
        // 除外フィールドを除いて復元
        const filteredData = Object.keys(parsedData).reduce((acc, field) => {
          if (!excludeFields.includes(field as keyof T)) {
            acc[field as keyof T] = parsedData[field];
          }
          return acc;
        }, {} as Partial<T>);

        setValues((prev) => ({ ...prev, ...filteredData }));
      }
    } catch (error) {
      console.error("フォーム状態の復元に失敗しました:", error);
    } finally {
      setIsLoaded(true);
    }
  }, [key]); // excludeFieldsを依存関係から除外

  // 値が変更されたときにローカルストレージに保存
  useEffect(() => {
    if (!isLoaded) return;

    try {
      // 除外フィールドを除いて保存
      const dataToSave = Object.keys(values).reduce((acc, field) => {
        if (!excludeFields.includes(field as keyof T)) {
          acc[field as keyof T] = values[field as keyof T];
        }
        return acc;
      }, {} as Partial<T>);

      localStorage.setItem(`form_${key}`, JSON.stringify(dataToSave));
    } catch (error) {
      console.error("フォーム状態の保存に失敗しました:", error);
    }
  }, [values, key, isLoaded]); // excludeFieldsを依存関係から除外

  // 値を更新する関数
  const updateValue = useCallback((field: keyof T, value: any) => {
    setValues((prev) => ({ ...prev, [field]: value }));
  }, []);

  // 複数の値を一度に更新する関数
  const updateValues = useCallback((newValues: Partial<T>) => {
    setValues((prev) => ({ ...prev, ...newValues }));
  }, []);

  // フォームをクリアする関数
  const clearForm = useCallback(() => {
    setValues(initialValues);
    try {
      localStorage.removeItem(`form_${key}`);
    } catch (error) {
      console.error("フォーム状態のクリアに失敗しました:", error);
    }
  }, [key, initialValues]);

  // 送信成功時にフォームをクリアする関数
  const handleSubmitSuccess = useCallback(() => {
    if (clearOnSubmit) {
      clearForm();
    }
  }, [clearOnSubmit, clearForm]);

  return {
    values,
    updateValue,
    updateValues,
    clearForm,
    handleSubmitSuccess,
    isLoaded,
  };
}
