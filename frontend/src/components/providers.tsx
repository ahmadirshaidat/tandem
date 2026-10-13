"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: (count, error) =>
              !(error instanceof ApiError && error.status < 500) && count < 1,
          },
          mutations: { retry: false },
        },
      }),
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      const choice = localStorage.getItem("tandem-theme");
      document.documentElement.classList.toggle(
        "dark",
        choice === "dark" || (!choice && media.matches),
      );
    };
    media.addEventListener("change", sync);
    window.addEventListener("storage", sync);
    return () => {
      media.removeEventListener("change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
