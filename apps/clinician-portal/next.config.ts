import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Response headers for every route.
  //
  // The portals previously sent only Vercel's default HSTS. These four cannot affect
  // rendering, so they are safe to apply globally.
  //
  // A Content-Security-Policy is deliberately NOT set here: a correct policy for this app
  // has to account for Next's inline bootstrap and Sentry's ingest origin, and an untested
  // one breaks the page rather than protecting it. That needs its own change, verified in
  // a browser against a production build.
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
            value: "geolocation=(), microphone=(), camera=()",
          },
        ],
      },
    ];
  },
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

export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.CLINICIAN_PORTAL_SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  disableLogger: true,
});
