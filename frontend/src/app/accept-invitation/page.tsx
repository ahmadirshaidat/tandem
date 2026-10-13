import { Suspense } from "react";
import { InvitationPage } from "@/components/invitation-page";
export default function Page() {
  return (
    <Suspense
      fallback={
        <div role="status" className="loading">
          Loading…
        </div>
      }
    >
      <InvitationPage />
    </Suspense>
  );
}
