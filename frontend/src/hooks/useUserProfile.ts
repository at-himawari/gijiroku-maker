"use client";
import { useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { UserProfile, UserProfileResponse } from "@/types/user";

const API_BASE_URL = `${process.env.NEXT_PUBLIC_HOST}`;

export function useUserProfile() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/users/profile`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      const data: UserProfileResponse = await response.json();

      if (data.success) {
        setProfile(data.profile);
      } else {
        setError(data.message || "プロフィールの取得に失敗しました");
      }
    } catch (err) {
      console.error("Error fetching profile:", err);
      setError("ネットワークエラーが発生しました");
    } finally {
      setLoading(false);
    }
  }, [token]);

  return {
    profile,
    loading,
    error,
    fetchProfile,
  };
}
