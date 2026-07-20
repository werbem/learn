import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 竞品分析助手",
  description: "自动生成互联网产品竞品分析报告",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
          <div className="container flex h-14 items-center">
            <a href="/" className="flex items-center gap-2 font-semibold text-lg">
              <svg className="h-6 w-6 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
              AI 竞品分析助手
            </a>
          </div>
        </header>
        <main className="">{children}</main>
      </body>
    </html>
  );
}
