import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "USDA Grant Assist - Voice Agent",
  description:
    "Ask about USDA grants, programs, or local offices using voice or text",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var saved = localStorage.getItem('theme');
                  var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
                  document.documentElement.setAttribute('data-theme', theme);
                } catch(e) {}
              })();
            `,
          }}
        />
        {/* Inline critical CSS variables so styles never disappear on reload.
            These are duplicated from globals.css @theme / [data-theme="dark"]
            to guarantee they are available before the external stylesheet loads. */}
        <style
          dangerouslySetInnerHTML={{
            __html: `
              :root, html {
                --color-bg-primary: #f4f7f4;
                --color-bg-secondary: #ffffff;
                --color-bg-tertiary: #eef2ee;
                --color-text-primary: #1a1d1a;
                --color-text-secondary: #4a5568;
                --color-text-tertiary: #a0aeb0;
                --color-accent: #3c5a3e;
                --color-accent-light: #e8f5e9;
                --color-border: #d7e0d8;
                --color-success: #3c5a3e;
                --color-error: #c06c5d;
                --color-warning: #d9a036;
              }
              [data-theme="dark"] {
                --color-bg-primary: #1a1d1a;
                --color-bg-secondary: #242824;
                --color-bg-tertiary: #2e332e;
                --color-text-primary: #e8ebe8;
                --color-text-secondary: #b8beb8;
                --color-text-tertiary: #7a827a;
                --color-accent: #6db070;
                --color-accent-light: #2e3d2e;
                --color-border: #3a3f3a;
                --color-success: #6db070;
                --color-error: #c06c5d;
                --color-warning: #d9a036;
              }
              html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background: var(--color-bg-primary);
                color: var(--color-text-primary);
                font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
                  Roboto, "Helvetica Neue", Arial, sans-serif;
              }
            `,
          }}
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
