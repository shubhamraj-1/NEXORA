/** @type {import('next').NextConfig} */
const backend = process.env.NEXORA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  outputFileTracingRoot: process.cwd(),
  poweredByHeader: false,
  // Hostname only, no scheme or port. Update if the LAN IP changes.
  allowedDevOrigins: ["172.20.10.3"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
