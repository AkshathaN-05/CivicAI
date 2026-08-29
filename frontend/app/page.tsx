import Link from "next/link";

const STATS = [
  { value: "7", label: "Govt. Authorities" },
  { value: "10+", label: "Issue Categories" },
  { value: "AI", label: "Smart Routing" },
  { value: "Free", label: "Completely Free" },
];

const FEATURES = [
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z" />
      </svg>
    ),
    title: "Submit with a Photo",
    desc: "Attach a photo of the civic issue for better context and faster resolution.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
      </svg>
    ),
    title: "AI Authority Routing",
    desc: "The AI analyses your issue and recommends the exact Mangaluru authority responsible.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      </svg>
    ),
    title: "You Review First",
    desc: "See the AI recommendation before anything is filed. You stay in control.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 0 1 0 3.75H5.625a1.875 1.875 0 0 1 0-3.75Z" />
      </svg>
    ),
    title: "Track Your Reports",
    desc: "All submitted reports are visible in the civic dashboard with live status updates.",
  },
];

const AUTHORITIES = [
  "Mangaluru City Corporation",
  "MCC Drainage Division",
  "Mangaluru Water Works Dept",
  "MESCOM (Electricity)",
  "NHAI Mangaluru",
  "MUDA",
  "MCC North Zone",
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="bg-[hsl(221,83%,29%)] text-white">
        <div className="max-w-5xl mx-auto px-4 py-20 sm:py-28">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 rounded-full px-3 py-1 text-xs font-medium mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Live in Mangaluru, Karnataka
            </div>
            <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight mb-5">
              Report Civic Issues<br />
              <span className="text-blue-200">Intelligently</span>
            </h1>
            <p className="text-lg text-blue-100 mb-8 leading-relaxed max-w-xl">
              CivicAI uses AI to route your issue to the right Mangaluru authority — instantly.
              Sign up free and submit in minutes, not days.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/login"
                className="inline-flex items-center gap-2 bg-white text-[hsl(221,83%,31%)] font-semibold px-6 py-3 rounded-lg text-base hover:bg-blue-50 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Get Started Free
              </Link>
              <Link
                href="/reports"
                className="inline-flex items-center gap-2 bg-white/10 border border-white/25 text-white font-medium px-6 py-3 rounded-lg text-base hover:bg-white/20 transition-colors"
              >
                View My Reports
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Stats strip */}
      <section className="border-b border-border bg-white">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <div className="text-2xl font-extrabold text-primary">{s.value}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-5xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold mb-3">How It Works</h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            From photo to the right authority in three simple steps.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              className="relative group border border-border rounded-xl p-5 bg-card hover:border-ring/50 hover:shadow-sm transition-all"
            >
              <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center text-primary mb-4">
                {f.icon}
              </div>
              <div className="absolute top-4 right-4 text-3xl font-black text-border">
                {String(i + 1).padStart(2, "0")}
              </div>
              <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Authorities */}
      <section className="bg-[hsl(217,33%,98%)] border-y border-border py-14 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-8">
            <h2 className="text-xl font-bold mb-2">Connected Authorities</h2>
            <p className="text-sm text-muted-foreground">
              AI automatically routes to the correct department.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {AUTHORITIES.map((a) => (
              <span
                key={a}
                className="inline-flex items-center gap-1.5 border border-border rounded-full bg-white px-3 py-1 text-xs font-medium text-muted-foreground"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60" />
                {a}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-3xl mx-auto px-4 py-20 text-center">
        <h2 className="text-2xl sm:text-3xl font-bold mb-4">
          See a civic problem in Mangaluru?
        </h2>
        <p className="text-muted-foreground mb-8 max-w-md mx-auto">
          Create a free account, submit a report in under two minutes. The AI handles authority routing — you just describe the issue.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 bg-primary text-primary-foreground font-semibold px-8 py-3 rounded-lg text-base hover:opacity-90 transition-opacity"
        >
          Sign Up &amp; Report an Issue
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
          </svg>
        </Link>
      </section>
    </div>
  );
}
