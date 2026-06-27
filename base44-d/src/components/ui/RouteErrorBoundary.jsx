import React from "react";
import { Link } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary — keeps app shell alive; recoverable navigation.
 */
export default class RouteErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    const label = this.props.label || "route";
    console.error(`[RouteErrorBoundary:${label}]`, error, info?.componentStack);
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      const msg = String(this.state.error?.message || this.state.error);
      return (
        <div className="max-w-2xl mx-auto rounded-xl border border-red-500/30 bg-red-500/5 p-6 space-y-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-6 h-6 text-red-400 shrink-0" />
            <div>
              <h2 className="text-lg font-semibold text-red-200">
                {this.props.title || "This page could not be loaded"}
              </h2>
              <p className="text-sm text-red-200/80 mt-1">
                The app shell is still active — use Back or Match Center to continue.
              </p>
              {this.props.showDetail && (
                <p className="text-xs font-mono text-red-200/60 mt-2 break-all">{msg}</p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button asChild variant="default" size="sm">
              <Link to="/matches">Match Center</Link>
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
