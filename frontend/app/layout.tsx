import "./globals.css"
import TopNav from "./components/TopNav"

export const metadata = {
  title: "AI Learning Copilot",
  description: "Academic AI workspace",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="he" dir="rtl">
      <body>
        <div className="min-h-screen bg-slate-100 text-slate-900">
          <TopNav />
          <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
        </div>
      </body>
    </html>
  )
}
