/** @type {import('next').NextConfig} */
const backend = process.env.NEXORA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  outputFileTracingRoot: process.cwd(),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
