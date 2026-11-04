import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './design-tokens.css';
import './globals.css';

export const metadata: Metadata = { title: 'Quant Lab', description: 'Shaxsiy kvant savdo tadqiqot platformasi' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="uz">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=Inter+Tight:ital,wght@0,100..900;1,100..900&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}
