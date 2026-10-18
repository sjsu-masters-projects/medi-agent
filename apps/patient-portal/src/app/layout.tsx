import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { StoreProvider } from "@/store/provider";
import { cookies, headers } from "next/headers";
import { PatientLocaleProvider } from "@/contexts/patient-locale-context";
import { PATIENT_LOCALE_COOKIE, PATIENT_LOCALE_HEADER, supportedPatientLocale } from "@/content/patient-locale";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "MediAgent Care",
  description: "A calm health companion for medications, records, care reminders, and clinician updates.",
  applicationName: "MediAgent Care",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "MediAgent Care",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/brand/favicon.svg", type: "image/svg+xml" },
      { url: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/brand/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: { url: "/brand/apple-touch-icon.png", sizes: "180x180" },
  },
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#147465",
  viewportFit: "cover",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Intentional dynamic SSR: the proxy hint keeps the first HTML paint in the resolved locale.
  const locale = supportedPatientLocale((await headers()).get(PATIENT_LOCALE_HEADER))
    ?? supportedPatientLocale((await cookies()).get(PATIENT_LOCALE_COOKIE)?.value);
  return (
    <html lang={locale ?? "en-US"} className={`${geist.variable} ${geistMono.variable}`}>
      <body className="antialiased">
        <PatientLocaleProvider initialLocale={locale}><StoreProvider>{children}</StoreProvider></PatientLocaleProvider>
      </body>
    </html>
  );
}
