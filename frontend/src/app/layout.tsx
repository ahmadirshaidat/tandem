import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";
export const metadata: Metadata = {
  title: "Tandem — a shared place to build",
  description: "Bring your software team together in one calm workspace.",
  robots: { index: false, follow: false },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};
const themeScript =
  "try{let t=localStorage.getItem('tandem-theme');document.documentElement.classList.toggle('dark',t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))}catch{}";
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
