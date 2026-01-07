import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/toaster";

const inter = Inter({ subsets: ["latin"] });
const favicon = "/logo.png";

export const metadata: Metadata = {
  title: "議事録メーカー",
  description: "議事録の作成が苦手なあなた！文字起こしを行い、要約を簡単に行うことができます！",
  icons: {
    icon: favicon,
  },
  openGraph: {
    title: "議事録メーカー",
    description: "議事録の作成が苦手なあなた！文字起こしを行い、要約を簡単に行うことができます！",
    images: [
      {
        url: "https://gijiroku-maker.at-himawari.com/logo.png",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className={inter.className}>
        <AuthProvider>
          {children}
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  );
}
