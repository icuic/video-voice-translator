# FastAPI 后端

## 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

## 运行

```bash
# 方式1: 使用 uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 方式2: 直接运行
python -m app.main
```

## API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 架构说明

- `app/main.py`: FastAPI 应用入口
- `app/api/`: API 路由模块
- `app/services/`: 业务服务层（调用 `./src/` 中的现有代码）
- `app/models/`: 数据模型（Pydantic）

## 重要说明

后端**不重复实现**业务逻辑，而是调用 `../src/` 目录中的现有类：
- `TextTranslator` - 文本翻译
- `VoiceCloner` - 音色克隆
- `TimestampedAudioMerger` - 音频合并
- 等等...


