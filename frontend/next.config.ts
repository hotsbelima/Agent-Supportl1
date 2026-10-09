import type { NextConfig } from "next";

const PRODUCT_API_ORIGIN = (
  process.env.PRODUCT_API_ORIGIN ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "https://p01--product-api--yxz5y8myjdln.code.run"
)
  .trim()
  .replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/product-api/:path*",
        destination: `${PRODUCT_API_ORIGIN}/:path*`,
      },
    ];
  },
};

export default nextConfig;
