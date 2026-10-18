import { NextResponse, type NextRequest } from "next/server";
import { isAuthEntryPath, PATIENT_LOCALE_COOKIE, PATIENT_LOCALE_HEADER, supportedPatientLocale } from "@/content/patient-locale";

export function proxy(request: NextRequest) {
  const entry = isAuthEntryPath(request.nextUrl.pathname);
  const queryLocale = entry ? supportedPatientLocale(request.nextUrl.searchParams.get("lang")) : null;
  const locale = queryLocale ?? supportedPatientLocale(request.cookies.get(PATIENT_LOCALE_COOKIE)?.value);
  const headers = new Headers(request.headers);
  // Never trust a caller-supplied presentation header.
  headers.delete(PATIENT_LOCALE_HEADER);
  if (locale) headers.set(PATIENT_LOCALE_HEADER, locale);
  const response = NextResponse.next({ request: { headers } });
  if (queryLocale) response.cookies.set(PATIENT_LOCALE_COOKIE, queryLocale, {
    path: "/", maxAge: 31536000, sameSite: "lax", secure: request.nextUrl.protocol === "https:",
  });
  return response;
}

export const config = { matcher: ["/((?!api|_next|brand|.*\\..*).*)"] };
