import type { NextConfig } from "next";

const config: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/document-sync/:path*",
        destination: `${process.env.DOCUMENT_SYNC_URL ?? "http://127.0.0.1:8002"}/api/document-sync/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Tandem-Project", value: "tandem-workspace-v1" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};
export default config;
