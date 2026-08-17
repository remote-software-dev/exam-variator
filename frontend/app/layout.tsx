import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Generator Variasi Soal",
  description: "Indonesian exam question variation generator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id" className="h-full">
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900 antialiased">
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <a href="/" className="text-xl font-bold text-blue-600 hover:text-blue-800">
              Generator Variasi Soal
            </a>
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
