"use client";

import { useEffect } from "react";
import TranscriptionApp from "@/components/TranscriptionApp";
import { ProtectedRoute } from "@/components/ProtectedRoute";

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

export default function Home() {
  useEffect(() => {
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (error) {
      console.error("AdSenseの初期化に失敗しました:", error);
    }
  }, []);

  return (
    <ProtectedRoute>
      <main className="flex min-h-screen flex-col p-4 md:p-8">
        <TranscriptionApp />
        <section className="mt-8" aria-label="広告">
          <ins
            className="adsbygoogle"
            style={{ display: "block" }}
            data-ad-client="ca-pub-6651283997191475"
            data-ad-slot="4759075102"
            data-ad-format="auto"
            data-full-width-responsive="true"
          />
        </section>
        <footer className="mt-auto pt-8 text-center text-sm text-gray-500">
          &copy; 2026 Himawari Project All rights reserved.
        </footer>
      </main>
    </ProtectedRoute>
  );
}
