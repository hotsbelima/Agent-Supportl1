import { ThemeToggle } from "@/components/theme-toggle";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Autonomous L1 Incident Agent",
  description: "Operational console for the 8 Щупалец Scenario 1 demo.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body><ThemeToggle />
        {children}</body>
    </html>
  );
}
