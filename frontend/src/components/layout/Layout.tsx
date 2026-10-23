import { Link, useLocation } from "react-router-dom";
import { ConnectionStatus } from "@/components/ui/connection-status";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useGlobalToasts } from "@/hooks/useStatusToasts";

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  // Enable dynamic page titles
  usePageTitle();

  // Single app-wide listener for completion/failure/401 toasts
  useGlobalToasts();

  const navigation = [
    { name: "Home", href: "/", current: location.pathname === "/" },
    {
      name: "Dashboard",
      href: "/dashboard",
      current: location.pathname === "/dashboard",
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-8">
              <Link to="/" className="flex items-center gap-2">
                <span className="text-2xl">🧠</span>
                <div>
                  <h1 className="text-2xl font-bold text-foreground">
                    CodeSage
                  </h1>
                  <p className="text-xs text-muted-foreground">
                    AI-Powered Code Discovery
                  </p>
                </div>
              </Link>

              <nav className="hidden md:flex items-center gap-4">
                {navigation.map((item) => (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      item.current
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    {item.name}
                  </Link>
                ))}
              </nav>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground hidden sm:block">
                Powered by Algolia MCP
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="border-t mt-16">
        <div className="container mx-auto px-4 py-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              Built with React, TypeScript, TailwindCSS, and Algolia MCP Server
            </p>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <a
                href="https://github.com/ntanwir10/codesage-algolia-challenge"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                GitHub
              </a>
              <a
                href="https://algolia.com"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                Algolia
              </a>
            </div>
          </div>
        </div>
      </footer>

      {/* Connection Status Component */}
      <ConnectionStatus />
    </div>
  );
}
