import type React from "react";
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'

// HAI 生产部署：禁用 StrictMode
// 原因：开发期 StrictMode 会 double-invoke effects，叠加 vite/supervisor 重启期 setup/status 502，
//       很容易触发 React 19 渲染层未捕获 throw，再叠加路由守卫同栈 setState/replaceState 触发白屏。
//       ErrorBoundary 已兜底捕获所有渲染层 throw，因此此处不再需要 StrictMode。

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
)
