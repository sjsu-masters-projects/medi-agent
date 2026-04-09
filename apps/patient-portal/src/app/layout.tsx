import type { Metadata } from "next";
import { SyncfusionRegister } from "@/components/features/syncfusion-register";
import { StoreProvider } from "@/store/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "MediAgent – Your Intelligent Health Companion",
  description: "AI-powered health companion for managing medications, obligations, and appointments.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <SyncfusionRegister />
        <StoreProvider>{children}</StoreProvider>
      </body>
    </html>
  );
}
