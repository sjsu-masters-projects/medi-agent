import * as Sentry from "@sentry/nextjs";

const sentryRelease =
  process.env.SENTRY_RELEASE ?? process.env.VERCEL_GIT_COMMIT_SHA ?? undefined;

Sentry.init({
  dsn:
    process.env.CLINICIAN_PORTAL_SENTRY_DSN ??
    process.env.NEXT_PUBLIC_CLINICIAN_PORTAL_SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT,
  release: sentryRelease,
  debug: process.env.SENTRY_DEBUG === "true",
  sendDefaultPii: false,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.0,
});
