import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="error-screen" role="alert">
          <h1>Something went wrong</h1>
          <p>Refresh the page to try again.</p>
        </main>
      )
    }

    return this.props.children
  }
}
