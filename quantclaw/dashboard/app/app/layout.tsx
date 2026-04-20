import type { Metadata } from "next";
import "./globals.css";
import { LangProvider } from "./lang-context";

export const metadata: Metadata = {
  title: "QuantClaw - Quant Trading Dashboard",
  description: "Open-source quant trading superagent harness",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-void text-[#b0bdd0] min-h-screen antialiased circuit-board">
        <LangProvider>{children}</LangProvider>
      </body>
    </html>
  );
}
