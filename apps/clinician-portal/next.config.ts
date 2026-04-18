import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/dashboard/settings/mfa",
        destination: "/settings/mfa",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
