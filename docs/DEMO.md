# 比赛演示指南

这份文档面向比赛现场或远程答辩，目标是让工程以最少操作稳定启动，并且让评委能快速看到完整链路。

## 推荐启动方式

在项目根目录执行：

```bash
./service.sh up
```

常用命令：

```bash
./service.sh status
./service.sh restart
./service.sh logs
./service.sh down
```

如果希望服务在 SSH 断线后仍持续运行，推荐用 supervisor：

```bash
./supervisor.sh up
./supervisor.sh status
./supervisor.sh restart
./supervisor.sh down
```

说明：
- 后端默认监听 `8000`
- 前端默认监听 `5173`
- 日志写入 `data/logs/backend.log` 和 `data/logs/frontend.log`
- PID 写入 `data/run/`

## 云服务器访问

如果平台不直接暴露 5173/8000，推荐使用 SSH 端口转发：

```bash
ssh -i <私钥> -p <SSH端口> <用户>@<服务器IP> -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 -N
```

然后在本机访问：

- 前端：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`

## 演示前检查清单

1. 确认 `.env` 中的翻译 LLM 配置已就绪
2. 运行 `./service.sh status`，确认前后端都处于运行中
3. 用浏览器打开 `http://127.0.0.1:5173`
4. 预先准备 1 个英文短视频样例，避免现场临时找素材
5. 确认 `data/outputs/` 有可回放的历史成功结果，便于兜底展示

## 推荐演示顺序

1. 展示前端上传界面
2. 上传英文视频，选择 `English -> 中文`
3. 开始处理，说明流程包括：
   - 音频提取
   - 语音识别
   - LLM 文本翻译
   - IndexTTS2 音色克隆
   - 视频合成
4. 展示输出视频与中间产物目录
5. 如时间允许，展示 API 文档 `http://127.0.0.1:8000/docs`

## 适合答辩强调的点

- 本分支优先适配 AMD/ROCm 环境
- 前后端分离，便于比赛演示和后续部署
- 翻译 LLM 配置支持从 `.env` 读取，不把敏感信息提交到仓库
- 当部分模型组件受网络或硬件限制时，系统会尽量降级而不是直接中断

## 出问题时先看哪里

```bash
./service.sh logs
```

或使用 supervisor：

```bash
./supervisor.sh logs
```

重点关注：
- `data/logs/backend.log`
- `data/logs/frontend.log`
- 具体任务目录下的 `processing_log.txt`
