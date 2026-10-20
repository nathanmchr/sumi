import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies, headers } from "next/headers";
import { Noto_Sans_JP, Public_Sans } from "next/font/google";
import "@/styles/globals.css";
import { LocaleProvider } from "@/lib/i18n";
import type { Locale } from "@/lib/types";

const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-ui" });
const notoSansJP = Noto_Sans_JP({ subsets: ["latin"], variable: "--font-jp" });

export const metadata: Metadata = {
  title: "Sumi 墨",
  description: "JLPT learning with spaced repetition, kanji detail pages, and a structured study flow.",
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const cookieStore = await cookies();
  const requestHeaders = await headers();
  const storedLocale = cookieStore.get("mirai_locale")?.value;
  const initialLocale: Locale = storedLocale === "en" || storedLocale === "fr"
    ? storedLocale
    : requestHeaders.get("accept-language")?.toLowerCase().startsWith("fr") ? "fr" : "en";

  return (
    <html lang={initialLocale}>
      <body className={`${publicSans.className} ${publicSans.variable} ${notoSansJP.variable}`}>
        <LocaleProvider initialLocale={initialLocale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
