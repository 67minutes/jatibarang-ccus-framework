import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  /** Region label shown in the fallback. */
  label: string;
  /** Optional custom fallback (e.g. the 2D viewport when 3D crashes). */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Per-region error boundary (design §8). A crash in one panel — most
 * importantly the 3D viewport — never blanks the whole workspace; the region
 * degrades to a readable fallback (or the provided 2D fallback) with a retry.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface for debugging without taking down the app.
    console.error(`[${this.props.label}] region error`, error, info);
  }

  reset = () => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      if (this.props.fallback) return this.props.fallback(error, this.reset);
      return (
        <div className="region-error" role="alert">
          <strong>{this.props.label} failed to render.</strong>
          <p className="region-error-msg mono">{error.message}</p>
          <button type="button" className="btn" onClick={this.reset}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
