import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { EmptyState } from "@/components/ui/empty-state";

interface ErrorBoundaryProps {
  children: ReactNode;
}

/** Catches render crashes below it; remount it (via `key`) to reset. */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Render error:", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <EmptyState
        icon="⚠️"
        title="Something went wrong"
        description="This page hit an unexpected error. Reloading usually fixes it."
        action={{ label: "Reload page", onClick: () => window.location.reload() }}
        className="container mx-auto px-4"
      />
    );
  }
}
