"use client";

import React, { Suspense } from "react";
import { useRouter } from "next/navigation";
import { EmailPasswordResetForm } from "@/components/EmailPasswordResetForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Image from "next/image";

function ResetPasswordPageContent() {
  const router = useRouter();

  const handleSuccess = () => {
    router.push("/email-auth?message=password-reset-success");
  };

  const handleBackToLogin = () => {
    router.push("/email-auth");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <Card>
          <CardHeader className="text-center">
            <div className="flex justify-center mb-4">
              <Image
                className="h-12 w-auto"
                src="/logo.png"
                alt="議事録メーカー"
                width={48}
                height={48}
              />
            </div>
            <CardTitle className="text-3xl font-bold text-gray-900">
              議事録メーカー
            </CardTitle>
          </CardHeader>
          <CardContent>
            <EmailPasswordResetForm
              onSuccess={handleSuccess}
              onBackToLogin={handleBackToLogin}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ResetPasswordPageContent />
    </Suspense>
  );
}
