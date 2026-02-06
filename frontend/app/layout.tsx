import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smith & Sons — Lead Generation",
  description: "Automated lead generation from London planning applications",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
