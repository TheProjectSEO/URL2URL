import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { GitCompareArrows, LayoutDashboard, Briefcase, PlusCircle, Sparkles } from "lucide-react";

export const metadata: Metadata = {
  title: "URL Matcher | AI Product Matching",
  description: "Semantic product matching between e-commerce websites using AI embeddings",
};

function NavLink({ href, children, icon: Icon }: { href: string; children: React.ReactNode; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <Link
      href={href}
      className="nav-link group flex items-center gap-2"
    >
      <Icon className="w-4 h-4 opacity-60 group-hover:opacity-100 transition-opacity" />
      {children}
    </Link>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="font-display antialiased">
        <div className="min-h-screen bg-[rgb(var(--surface-0))] text-[rgb(var(--text-primary))]">
          {/* Gradient background overlay */}
          <div className="fixed inset-0 bg-gradient-to-br from-[rgba(var(--accent),0.03)] via-transparent to-[rgba(var(--accent),0.02)] pointer-events-none" />

          {/* Navigation */}
          <nav className="sticky top-0 z-50 border-b border-[rgba(var(--border),var(--border-opacity))] backdrop-blur-xl bg-[rgba(var(--surface-1),0.8)]">
            <div className="max-w-7xl mx-auto px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                {/* Logo */}
                <Link href="/" className="flex items-center gap-3 group">
                  <div className="relative">
                    <div className="absolute inset-0 bg-[rgb(var(--accent))] blur-lg opacity-40 group-hover:opacity-60 transition-opacity" />
                    <div className="relative p-2 rounded-xl bg-gradient-to-br from-[rgb(var(--accent))] to-[rgba(var(--accent),0.7)]">
                      <GitCompareArrows className="w-5 h-5 text-white" />
                    </div>
                  </div>
                  <span className="font-semibold text-lg tracking-tight">
                    URL<span className="text-[rgb(var(--accent))]">Matcher</span>
                  </span>
                </Link>

                {/* Navigation Links */}
                <div className="flex items-center gap-1">
                  <NavLink href="/" icon={LayoutDashboard}>Dashboard</NavLink>
                  <NavLink href="/jobs" icon={Briefcase}>Jobs</NavLink>
                  <Link
                    href="/jobs/new"
                    className="ml-2 btn-primary flex items-center gap-2 text-sm"
                  >
                    <PlusCircle className="w-4 h-4" />
                    New Job
                  </Link>
                </div>
              </div>
            </div>
          </nav>

          {/* Main Content */}
          <main className="relative max-w-7xl mx-auto px-6 lg:px-8 py-8">
            <div className="animate-fade-in">
              {children}
            </div>
          </main>

          {/* Footer */}
          <footer className="relative border-t border-[rgba(var(--border),var(--border-opacity))] mt-auto">
            <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-[rgb(var(--text-muted))]">
                  <Sparkles className="w-4 h-4 text-[rgb(var(--accent))]" />
                  <span className="text-sm">Powered by AI semantic matching</span>
                </div>
                <p className="text-sm text-[rgb(var(--text-muted))]">
                  URL-to-URL Product Matcher &copy; {new Date().getFullYear()}
                </p>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
