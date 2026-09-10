import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0b1a",
          color: "#e2d9c4",
          fontFamily: "'Inter', sans-serif",
          padding: "2rem",
          textAlign: "center",
        }}>
          <div style={{ maxWidth: 480 }}>
            <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem", color: "#d4af37" }}>
              Something went wrong
            </h1>
            <p style={{ opacity: 0.7, marginBottom: "1.5rem" }}>
              An unexpected error occurred. Please try refreshing the page.
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "0.75rem 1.5rem",
                background: "linear-gradient(135deg, #d4af37, #b8962e)",
                color: "#0a0b1a",
                border: "none",
                borderRadius: 8,
                fontWeight: 600,
                cursor: "pointer",
                fontSize: "0.95rem",
              }}
            >
              Refresh Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
