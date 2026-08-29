import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CivicAI — Smart Civic Reporting for Mangaluru",
  description: "AI-powered civic issue reporting for Mangaluru, Karnataka. Submit potholes, streetlight faults, drainage issues and more — routed instantly to the right authority.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Header />
        <main className="min-h-screen bg-background">{children}</main>
        <footer className="border-t border-border bg-[hsl(217,33%,98%)] py-6 px-4">
          <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="font-semibold text-foreground/70">
              CivicAI <span className="font-normal">— Mangaluru, Karnataka</span>
            </div>
            <div>Powered by FastAPI · Supabase · AI Authority Routing</div>
          </div>
        </footer>
      </body>
    </html>
  );
}
