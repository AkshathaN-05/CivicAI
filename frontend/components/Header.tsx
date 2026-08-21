import Link from "next/link";

export default function Header() {
  return (
    <header className="border-b border-border bg-white sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-bold text-primary">CivicAI</span>
          <span className="hidden sm:inline text-sm text-muted-foreground">
            Mangaluru, Karnataka
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          <Link
            href="/report/new"
            className="px-3 py-1.5 text-sm font-medium rounded-md hover:bg-secondary transition-colors"
          >
            Report Issue
          </Link>
          <Link
            href="/reports"
            className="px-3 py-1.5 text-sm font-medium rounded-md hover:bg-secondary transition-colors"
          >
            Recent Reports
          </Link>
        </nav>
      </div>
    </header>
  );
}
