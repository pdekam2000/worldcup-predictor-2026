import React from "react";
import { AlertCircle } from "lucide-react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    const label = this.props.label || "section";
    console.error(`[ErrorBoundary:${label}]`, error, info?.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-100">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">{this.props.fallbackTitle || "This section is temporarily unavailable."}</p>
              {this.props.showDetail && (
                <p className="text-xs text-amber-200/70 mt-1 font-mono">{String(this.state.error?.message || this.state.error)}</p>
              )}
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
