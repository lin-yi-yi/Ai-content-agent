import React from 'react';

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('页面渲染失败', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-fallback">
          <h2>页面渲染遇到问题</h2>
          <p>{this.state.error.message || '请刷新页面后重试。'}</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
