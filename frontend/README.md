# React 前端

## 安装依赖

首先需要安装 Node.js 和 npm。然后：

```bash
cd frontend
npm install
```

## 运行

```bash
npm run dev
```

前端将在 http://localhost:5173 启动。

## 构建

```bash
npm run build
```

## 环境变量

创建 `.env` 文件：

```
VITE_API_BASE_URL=http://localhost:8000
```

## 项目结构

- `src/components/`: React 组件
- `src/hooks/`: 自定义 Hooks
- `src/services/`: API 服务
- `src/stores/`: Zustand 状态管理
- `src/types/`: TypeScript 类型定义
- `src/utils/`: 工具函数


