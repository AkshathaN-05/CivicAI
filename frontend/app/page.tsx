import Link from "next/link";

const FEATURES = [
  {
    icon: "📸",
    title: "Submit with a Photo",
    desc: "Attach an optional photo of the civic issue for better context.",
  },
  {
    icon: "🤖",
    title: "AI Authority Routing",
    desc: "The system recommends the correct Mangaluru authority based on issue type and location.",
  },
  {
    icon: "✅",
    title: "You Decide",
    desc: "Review the AI recommendation before submitting. Nothing is filed without your approval.",
  },
  {
    icon: "📋",
    title: "Track Your Reports",
    desc: "All submitted reports are visible in Recent Reports with live status updates.",
  },
];

export default function HomePage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-primary text-primary-foreground py-20 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">
            Report Civic Issues in Mangaluru
          </h1>
          <p className="text-lg sm:text-xl opacity-90 mb-8 max-w-2xl mx-auto">
            Photograph a problem, describe it, and AI will recommend the right
            government authority. You review before anything is submitted.
          </p>
          <Link
            href="/report/new"
            className="inline-block bg-white text-primary font-semibold px-8 py-3 rounded-lg text-lg hover:bg-primary-foreground transition-colors"
          >
            Report an Issue
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-center mb-10">How It Works</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="border border-border rounded-lg p-6 bg-card"
            >
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="font-semibold text-base mb-1">{f.title}</h3>
              <p className="text-sm text-muted-foreground">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA strip */}
      <section className="border-t border-border bg-muted/40 py-10 px-4">
        <div className="max-w-xl mx-auto text-center">
          <p className="text-muted-foreground mb-4">
            Already submitted a report?
          </p>
          <Link
            href="/reports"
            className="inline-block border border-border rounded-lg px-6 py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
          >
            View Recent Reports →
          </Link>
        </div>
      </section>
    </div>
  );
}
