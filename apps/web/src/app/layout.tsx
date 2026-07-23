import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { siteConfig } from "./site-config";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.siteUrl),
  title: {
    default: "Stonegate Home Buyers | Sell Your Georgia House As-Is",
    template: "%s",
  },
  description: "Request a no-obligation, direct cash offer review for a Georgia property. Sell as-is without listing prep or showings.",
  applicationName: siteConfig.name,
  openGraph: {
    type: "website",
    siteName: siteConfig.name,
    title: "Stonegate Home Buyers | Georgia Direct Home Offers",
    description: "A clear, as-is home sale option for Georgia property owners.",
    images: [{ url: "/images/stonegate-georgia-home-hero.jpg", width: 1672, height: 941, alt: "Red-brick Georgia home surrounded by mature trees" }],
  },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <ClerkProvider>{children}</ClerkProvider>
      </body>
    </html>
  );
}
