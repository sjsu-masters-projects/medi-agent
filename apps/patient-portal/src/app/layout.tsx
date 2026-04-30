import type { Metadata, Viewport } from "next";
import { SyncfusionRegister } from "@/components/features/syncfusion-register";
import { StoreProvider } from "@/store/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "MediAgent Patient",
  description: "A calm health companion for medications, records, care reminders, and clinician updates.",
  applicationName: "MediAgent Patient",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "MediAgent",
  },
  formatDetection: {
    telephone: false,
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
