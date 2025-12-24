"use client";

import TranscriptionApp from "@/components/TranscriptionApp";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export default function Home() {
  return (
    <ProtectedRoute>
      <main className="min-h-screen p-4 md:p-8">
        <TranscriptionApp />
      </main>
    </ProtectedRoute>
  );
}
