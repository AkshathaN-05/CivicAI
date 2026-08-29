"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";

type Mode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function friendlyError(msg: string, context: "signin" | "signup" = "signin"): string {
    if (!msg) return "Something went wrong. Please try again.";
    const m = msg.toLowerCase();

    // "email not confirmed" — account exists but user hasn't clicked the confirmation link.
    if (m.includes("email not confirmed"))
      return "Please confirm your email address before signing in. Check your inbox for the confirmation link.";

    if (m.includes("invalid login") || m.includes("invalid credentials"))
      return "Incorrect email or password.";

    // Signup: duplicate email (Supabase sometimes surfaces this).
    if (m.includes("user already registered") || m.includes("already exists"))
      return "An account with this email already exists. Please sign in instead.";

    if (m.includes("password should be at least") || m.includes("should be at least")) {
      // Extract the actual minimum from the Supabase message if present,
      // e.g. "Password should be at least 6 characters" → keep as-is.
      return msg; // surface Supabase's exact message; do not hard-code a number
    }

    if (m.includes("too many requests") || m.includes("rate limit"))
      return "Too many attempts. Please wait a moment and try again.";

    if (m.includes("network") || m.includes("fetch"))
      return "Network error. Check your connection and try again.";

    if (m.includes("signup") && m.includes("disabled"))
      return "New signups are currently disabled on this project.";

    // Return the raw Supabase message for anything else so nothing is silently swallowed.
    return msg;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    if (mode === "signin") {
      // Send the password exactly as typed — no modification, no minimum check on sign-in.
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      setLoading(false);
      if (signInError) {
        setError(friendlyError(signInError.message, "signin"));
        return;
      }
      router.push("/reports");
    } else {
      const { data: signUpData, error: signUpError } = await supabase.auth.signUp({ email, password });
      setLoading(false);
      if (signUpError) {
        setError(friendlyError(signUpError.message, "signup"));
        return;
      }

      // Supabase returns user.identities=[] when the email already exists
      // and email confirmation is enabled — it silently pretends signup worked.
      const identities = signUpData?.user?.identities;
      if (identities && identities.length === 0) {
        setError("An account with this email already exists. Please sign in instead.");
        return;
      }

      setMessage(
        "Account created! Check your email for a confirmation link before signing in."
      );
    }
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 py-12 bg-[hsl(217,33%,98%)]">
      <div className="w-full max-w-sm">
        {/* Card */}
        <div className="bg-white rounded-2xl border border-border shadow-sm p-8">
          {/* Logo + title */}
          <div className="text-center mb-7">
            <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold">
              {mode === "signin" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              {mode === "signin"
                ? "Sign in to submit and track civic issue reports."
                : "Join CivicAI and start reporting civic issues."}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5 text-foreground" htmlFor="email">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-input rounded-lg px-3 py-2.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-shadow"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5 text-foreground" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-input rounded-lg px-3 py-2.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-shadow"
                placeholder={mode === "signup" ? "Choose a password" : "Your password"}
              />
              {/* Sign-in: no length hint. Sign-up: let Supabase enforce its policy. */}
              {mode === "signup" && (
                <p className="text-xs text-muted-foreground mt-1.5">
                  Choose a password. Supabase enforces its own minimum — if your
                  password is rejected, try a longer one.
                </p>
              )}
            </div>

            {error && (
              <div className="flex items-start gap-2.5 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            {message && (
              <div className="flex items-start gap-2.5 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
                <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
                <span>{message}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary text-primary-foreground font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-60 text-sm"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Please wait…
                </span>
              ) : mode === "signin" ? "Sign In" : "Create Account"}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-border text-center text-sm text-muted-foreground">
            {mode === "signin" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  onClick={() => { setMode("signup"); setError(null); setMessage(null); }}
                  className="text-primary hover:underline font-medium"
                >
                  Create one
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={() => { setMode("signin"); setError(null); setMessage(null); }}
                  className="text-primary hover:underline font-medium"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-5">
          <Link href="/" className="hover:text-foreground transition-colors">← Back to CivicAI</Link>
        </p>
      </div>
    </div>
  );
}
