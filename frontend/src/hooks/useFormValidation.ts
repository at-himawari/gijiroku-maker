"use client";

import { useState, useCallback, useMemo } from "react";

export type ValidationRule<T = any> = {
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: RegExp;
  custom?: (value: T) => string | null;
  message?: string;
};

export type ValidationRules<T extends Record<string, any>> = {
  [K in keyof T]?: ValidationRule<T[K]>;
};

export type ValidationErrors<T extends Record<string, any>> = {
  [K in keyof T]?: string;
};

/**
 * フォームバリデーション用カスタムフック
 * 要件: 7.3 - リアルタイムバリデーション
 */
export function useFormValidation<T extends Record<string, any>>(
  rules: ValidationRules<T>
) {
  const [errors, setErrors] = useState<ValidationErrors<T>>({});
  const [touched, setTouched] = useState<Partial<Record<keyof T, boolean>>>({});

  // 単一フィールドのバリデーション
  const validateField = useCallback(
    (field: keyof T, value: any): string | null => {
      const rule = rules[field];
      if (!rule) return null;

      // 必須チェック
      if (
        rule.required &&
        (!value || (typeof value === "string" && !value.trim()))
      ) {
        return rule.message || `${String(field)}は必須項目です`;
      }

      // 値が空の場合、必須でなければバリデーションをスキップ
      if (!value || (typeof value === "string" && !value.trim())) {
        return null;
      }

      // 最小長チェック
      if (
        rule.minLength &&
        typeof value === "string" &&
        value.length < rule.minLength
      ) {
        return (
          rule.message ||
          `${String(field)}は${rule.minLength}文字以上で入力してください`
        );
      }

      // 最大長チェック
      if (
        rule.maxLength &&
        typeof value === "string" &&
        value.length > rule.maxLength
      ) {
        return (
          rule.message ||
          `${String(field)}は${rule.maxLength}文字以下で入力してください`
        );
      }

      // パターンチェック
      if (
        rule.pattern &&
        typeof value === "string" &&
        !rule.pattern.test(value)
      ) {
        return rule.message || `${String(field)}の形式が正しくありません`;
      }

      // カスタムバリデーション
      if (rule.custom) {
        return rule.custom(value);
      }

      return null;
    },
    [rules]
  );

  // フィールドの値を検証し、エラー状態を更新
  const validate = useCallback(
    (field: keyof T, value: any) => {
      const error = validateField(field, value);
      setErrors((prev) => ({
        ...prev,
        [field]: error || undefined,
      }));
      return error === null;
    },
    [validateField]
  );

  // フォーム全体を検証
  const validateAll = useCallback(
    (values: T): boolean => {
      const newErrors: ValidationErrors<T> = {};
      let isValid = true;

      Object.keys(rules).forEach((field) => {
        const error = validateField(field as keyof T, values[field as keyof T]);
        if (error) {
          newErrors[field as keyof T] = error;
          isValid = false;
        }
      });

      setErrors(newErrors);
      return isValid;
    },
    [rules, validateField]
  );

  // フィールドがタッチされたことを記録
  const touch = useCallback((field: keyof T) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }, []);

  // 複数フィールドをタッチ
  const touchAll = useCallback(() => {
    const allTouched = Object.keys(rules).reduce((acc, field) => {
      acc[field as keyof T] = true;
      return acc;
    }, {} as Record<keyof T, boolean>);
    setTouched(allTouched);
  }, [rules]);

  // エラーをクリア
  const clearErrors = useCallback(() => {
    setErrors({});
  }, []);

  // タッチ状態をクリア
  const clearTouched = useCallback(() => {
    setTouched({});
  }, []);

  // すべてをクリア
  const clearAll = useCallback(() => {
    clearErrors();
    clearTouched();
  }, [clearErrors, clearTouched]);

  // フォームが有効かどうか
  const isValid = useMemo(() => {
    return Object.keys(errors).length === 0;
  }, [errors]);

  // タッチされたフィールドのエラーのみを取得
  const touchedErrors = useMemo(() => {
    const result: ValidationErrors<T> = {};
    Object.keys(errors).forEach((field) => {
      if (touched[field as keyof T] && errors[field as keyof T]) {
        result[field as keyof T] = errors[field as keyof T];
      }
    });
    return result;
  }, [errors, touched]);

  return {
    errors,
    touchedErrors,
    touched,
    isValid,
    validate,
    validateAll,
    validateField,
    touch,
    touchAll,
    clearErrors,
    clearTouched,
    clearAll,
  };
}
