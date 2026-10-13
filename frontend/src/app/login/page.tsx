import { Suspense } from "react";
import { AuthPage } from "@/components/auth-page";
export default function Page() {
  return (
    <Suspense
      fallback={
        <div role="status" className="loading">
          Loading…
        </div>
      }
    >
      <AuthPage mode="login" />
    </Suspense>
  );
}
