import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Catches a crash while a page is drawing so one bad screen never blanks the whole app. The menu stays,
 * and moving to another page (the boundary is keyed by address in Shell) clears the message.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page failed to draw", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="card card-pad mx-auto max-w-xl text-center" role="alert">
        <h1 className="text-xl">Something went wrong on this page</h1>
        <p className="mt-2 mb-0 text-muted">Your data is safe. Reload the page, or pick another page from the menu. If it keeps happening, tell your administrator what you were doing.</p>
        <button type="button" className="btn btn-primary mt-4" onClick={() => window.location.reload()}>Reload page</button>
      </div>
    );
  }
}
