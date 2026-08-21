import React from 'react';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  resetKey: number;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, resetKey: 0 };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, resetKey: 0 };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // 只在浏览器环境里上报
    try {
      // eslint-disable-next-line no-console
      console.error('[ErrorBoundary] React 渲染层抛出异常（白屏已阻止）：', error, info?.componentStack ?? '');
    } catch (_) {
      // noop
    }
    // 2 秒后自动 reload 跳 /（除非用户点了再试）
    try {
      window.setTimeout(() => {
        try {
          if (typeof window !== 'undefined') {
            if (window.location.pathname !== '/') {
              window.location.replace('/');
            } else {
              window.location.reload();
            }
          }
        } catch (_) {
          if (typeof window !== 'undefined') window.location.href = '/';
        }
      }, 2000);
    } catch (_) {
      // noop
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, resetKey: (this.state.resetKey || 0) + 1 });
    try {
      window.setTimeout(() => {
        try { window.location.reload(); } catch (_) { /* noop */ }
      }, 100);
    } catch (_) { /* noop */ }
  };

  render() {
    if (this.state.hasError) {
      const message = this.state.error?.message || '发生了未预期的错误';
      return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center p-6 text-white">
          <div className="w-full max-w-2xl bg-slate-800/60 backdrop-blur rounded-2xl border border-slate-700 shadow-2xl p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 bg-rose-500/90 rounded-xl flex items-center justify-center text-2xl">
                ⚠️
              </div>
              <div>
                <h2 className="text-2xl font-bold">页面遇到临时问题</h2>
                <p className="text-slate-300 text-sm mt-1">
                  2 秒后会自动刷新并跳回首页；如果仍然报错，请点击下方按钮重新加载
                </p>
              </div>
            </div>
            <div className="bg-slate-900/60 rounded-lg p-4 text-sm text-slate-300 border border-slate-700 mb-6 whitespace-pre-wrap break-all max-h-48 overflow-auto font-mono">
              {message}
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={this.handleRetry}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 transition text-white font-medium"
              >
                立即重新加载
              </button>
              <button
                onClick={() => { try { window.location.href = '/setup'; } catch (_) { /* noop */ } }}
                className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 transition text-slate-100 border border-slate-600"
              >
                回到 LLM 配置页 /setup
              </button>
            </div>
            <p className="mt-6 text-xs text-slate-400">
              错误 ID: {String(this.state.resetKey || 0)} — 如持续报错，请截图联系作者排查
            </p>
          </div>
        </div>
      );
    }
    // 给 children 加 key，让用户点重试时强制整棵子树重建
    return (
      <React.Fragment key={this.state.resetKey || 0}>
        {this.props.children}
      </React.Fragment>
    );
  }
}
