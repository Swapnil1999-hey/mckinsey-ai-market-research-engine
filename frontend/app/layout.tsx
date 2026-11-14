import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'McKinsey & Company — AI Market Research & Strategy Engine',
  description: 'Evidence-backed AI market research engine that turns complex business questions into traceable strategic briefs.',
  icons: {
    icon: [
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/favicon.ico', sizes: '32x32' },
    ],
    shortcut: '/icon.svg',
    apple: '/apple-touch-icon.png',
  },
  openGraph: {
    title: 'McKinsey & Company — AI Market Research & Strategy Engine',
    description: 'Evidence-backed AI market research engine with automated planning, browsing, extraction, and validation.',
    siteName: 'McKinsey AI Market Research Engine',
    images: [{ url: '/icon.svg', width: 64, height: 64 }],
  },
};

export const viewport: Viewport = {
  themeColor: '#001e38',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="alternate icon" href="/favicon.ico" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      </head>
      <body>{children}</body>
    </html>
  );
}
