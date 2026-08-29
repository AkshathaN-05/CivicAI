"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import type { Session } from "@supabase/supabase-js";

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    // Get the stored session first for fast initial render, then refresh
    // to ensure the JWT contains current app_metadata (e.g. admin role).
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      // Refresh in the background so app_metadata.role is up-to-date.
      if (data.session) {
        supabase.auth.refreshSession().then(({ data: rd }) => {
          if (rd?.session) setSession(rd.session);
        });
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => subscription.unsubscribe();
  }, []);

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  const isAdmin = session?.user?.app_metadata?.role === "admin";

  const navLink = (href: string, label: string) => {
    const active = pathname === href;
    return (
      <Link
        href={href}
        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
          active
            ? "bg-accent text-accent-foreground"
            : "hover:bg-secondary text-muted-foreground hover:text-foreground"
        }`}
        onClick={() => setMenuOpen(false)}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="border-b border-border bg-white/95 sticky top-0 z-50 backdrop-blur-sm">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
            </svg>
          </div>
          <div>
            <span className="font-bold text-foreground text-sm">CivicAI</span>
            <span className="hidden sm:inline text-xs text-muted-foreground ml-1.5">Mangaluru</span>
          </div>
        </Link>

        {/* Desktop nav — role-aware */}
        <nav className="hidden sm:flex items-center gap-1 flex-1">
          {isAdmin ? (
            // Admin nav: Dashboard + Manage Reports (no "Report Issue")
            <>
              {navLink("/admin", "Dashboard")}
              {navLink("/admin", "Manage Reports")}
            </>
          ) : (
            // Citizen nav
            <>
              {navLink("/reports", "My Reports")}
            </>
          )}
        </nav>

        {/* Right actions — role-aware */}
        <div className="hidden sm:flex items-center gap-2">
          {session ? (
            <>
              {/* Citizen: show "Report Issue". Admin: show admin badge instead */}
              {isAdmin ? (
                <span className="inline-flex items-center gap-1.5 bg-amber-50 border border-amber-200 text-amber-700 text-xs font-semibold px-3 py-1.5 rounded-md">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                  </svg>
                  Admin
                </span>
              ) : (
                <Link
                  href="/report/new"
                  className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground text-sm font-medium px-3 py-1.5 rounded-md hover:opacity-90 transition-opacity"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                  </svg>
                  Report Issue
                </Link>
              )}
              <div className="flex items-center gap-1 text-xs text-muted-foreground border border-border rounded-md px-2 py-1.5">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                </svg>
                <span className="max-w-[120px] truncate">{session.user.email}</span>
              </div>
              <button
                onClick={handleSignOut}
                className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md transition-colors"
              >
                Sign Out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/report/new"
                className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground text-sm font-medium px-3 py-1.5 rounded-md hover:opacity-90 transition-opacity"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Report Issue
              </Link>
              <Link
                href="/login"
                className="px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md transition-colors"
              >
                Sign In
              </Link>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="sm:hidden p-1.5 rounded-md hover:bg-secondary transition-colors"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Toggle menu"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            {menuOpen
              ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            }
          </svg>
        </button>
      </div>

      {/* Mobile menu — role-aware */}
      {menuOpen && (
        <div className="sm:hidden border-t border-border bg-white px-4 py-3 space-y-1">
          {isAdmin ? (
            // Admin mobile menu: no "Report Issue"
            <>
              <Link href="/admin" className="block px-3 py-2 text-sm font-medium text-primary rounded-md hover:bg-accent transition-colors" onClick={() => setMenuOpen(false)}>
                Dashboard
              </Link>
              <Link href="/admin" className="block px-3 py-2 text-sm rounded-md hover:bg-secondary transition-colors" onClick={() => setMenuOpen(false)}>
                Manage Reports
              </Link>
            </>
          ) : (
            // Citizen mobile menu
            <>
              <Link href="/report/new" className="block px-3 py-2 text-sm font-medium text-primary rounded-md hover:bg-accent transition-colors" onClick={() => setMenuOpen(false)}>
                + Report Issue
              </Link>
              <Link href="/reports" className="block px-3 py-2 text-sm rounded-md hover:bg-secondary transition-colors" onClick={() => setMenuOpen(false)}>
                My Reports
              </Link>
            </>
          )}
          {session ? (
            <>
              <div className="px-3 py-1.5 text-xs text-muted-foreground truncate">{session.user.email}</div>
              <button onClick={handleSignOut} className="w-full text-left px-3 py-2 text-sm text-muted-foreground rounded-md hover:bg-secondary transition-colors">
                Sign Out
              </button>
            </>
          ) : (
            <Link href="/login" className="block px-3 py-2 text-sm font-medium rounded-md hover:bg-secondary transition-colors" onClick={() => setMenuOpen(false)}>
              Sign In
            </Link>
          )}
        </div>
      )}
    </header>
  );
}
