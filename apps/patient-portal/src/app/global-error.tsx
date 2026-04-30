"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en-US">
      <body className="antialiased">
        <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f6efe7] px-6 text-center text-[#17233a]">
          <h1 className="text-3xl font-black tracking-[-0.03em]">Something went wrong</h1>
          <p className="max-w-md text-base leading-7 text-[#5b6b83]">
            The patient portal hit an unexpected error. Please try again.
          </p>
          <button
            className="min-h-12 rounded-2xl bg-[#147465] px-5 py-3 text-base font-semibold text-white shadow-[0_14px_30px_rgba(20,116,101,0.24)]"
            onClick={() => reset()}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
