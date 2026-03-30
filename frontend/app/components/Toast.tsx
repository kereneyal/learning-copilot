"use client"

export default function Toast({
  message,
  type = "info",
  onClose,
}: {
  message: string
  type?: "info" | "success" | "error"
  onClose: () => void
}) {
  const styles =
    type === "success"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
      : type === "error"
      ? "border-red-300 bg-red-50 text-red-800"
      : "border-blue-300 bg-blue-50 text-blue-800"

  return (
    <div className={`fixed bottom-6 left-6 z-50 min-w-[280px] rounded-2xl border px-4 py-3 shadow-lg ${styles}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="text-sm">{message}</div>
        <button onClick={onClose} className="text-xs opacity-70 hover:opacity-100">
          סגור
        </button>
      </div>
    </div>
  )
}
