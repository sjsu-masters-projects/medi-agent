import type { Metadata, Viewport } from "next";
import { SyncfusionRegister } from "@/components/features/syncfusion-register";
import { StoreProvider } from "@/store/provider";
import "./globals.css";

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
    icon: "/pwa-icon.svg",
    shortcut: "/pwa-icon.svg",
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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-US">
      <body className="antialiased">
        <SyncfusionRegister />
        <StoreProvider>{children}</StoreProvider>
      </body>
    </html>
  );
}
