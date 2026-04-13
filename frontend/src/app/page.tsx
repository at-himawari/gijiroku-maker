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
      <main className="min-h-screen p-4 md:p-8">
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
      </main>
    </ProtectedRoute>
  );
}
