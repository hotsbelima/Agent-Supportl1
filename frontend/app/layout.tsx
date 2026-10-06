import { ThemeToggle } from "@/components/theme-toggle";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Автономный L1-агент по инцидентам",
  description:
    "Публичное демо расследования инцидентов: три сценария, наблюдения, решение человека и сохранённая хронология.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <ThemeToggle />
        {children}
      </body>
    </html>
  );
}
