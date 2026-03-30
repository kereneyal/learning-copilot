"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

export default function TopNav() {
  const pathname = usePathname()

  const isChat = pathname === "/"
  const isKnowledge = pathname.startsWith("/knowledge")

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <div>
          <h1 className="text-xl font-bold">AI Learning Copilot</h1>
          <p className="text-sm text-slate-500">Workspace ללמידה, חיפוש וניתוח ידע</p>
        </div>

        <nav className="flex items-center gap-2 rounded-xl bg-slate-100 p-1">
          <Link
            href="/"
            className={`rounded-lg px-4 py-2 text-sm transition ${
              isChat ? "bg-white shadow-sm" : "text-slate-600"
            }`}
          >
            עוזר הלמידה
          </Link>
          <Link
            href="/knowledge"
            className={`rounded-lg px-4 py-2 text-sm transition ${
              isKnowledge ? "bg-white shadow-sm" : "text-slate-600"
            }`}
          >
            מרכז הידע
          </Link>
        </nav>
      </div>
    </header>
  )
}
