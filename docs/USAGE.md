# Video Voice Translator - 使用指南

## 目录

- [快速开始](#快速开始)
- [使用方法](#使用方法)
  - [前后端分离模式](#前后端分离模式推荐)
  - [命令行方式](#命令行方式)
  - [批量处理](#批量处理)

---

## 快速开始

如果您还没有安装系统，请先参考 [安装指南](INSTALL.md) 完成安装和配置。

安装完成后，您可以：

**方式一：前后端分离服务模式（推荐，基于 supervisord）**：

```bash
./manage-supervisor.sh start
```

- 前端界面：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

查看服务状态：`./manage-supervisor.sh status`

**方式二：命令行方式**：

```bash
# 自动检测语言并翻译
./run_cli.sh input.mp4

# 指定源语言和目标语言
./run_cli.sh input.mp4 --source-lang zh --target-lang en
```

---

**配置说明**：系统通过 `config.yaml` 文件进行配置。详细配置说明请参考 `config.yaml` 文件中的注释。

---

## 使用方法

### 前后端分离服务模式（推荐，基于 supervisord）

前后端分离模式提供了基于 React 的现代化 Web 界面，适合需要良好用户体验的场景。服务通过 **supervisord** 进行管理，具备：
- 崩溃自动重启
- 日志自动轮转
- 独立控制前端/后端启停
- 关闭终端后服务仍在后台运行

#### 前置要求

- Node.js v20 或更高版本（安装脚本会自动安装）
- 前端依赖已安装（安装脚本会自动安装）
- supervisord 已安装（一键安装脚本会自动安装）

#### 管理服务（最常用命令）

```bash
# 启动所有服务（后端 + 前端）
./manage-supervisor.sh start

# 查看服务状态、端口、日志路径
./manage-supervisor.sh status

# 重启所有服务
./manage-supervisor.sh restart

# 停止所有服务并退出 supervisord
./manage-supervisor.sh stop

# 实时查看后端日志
./manage-supervisor.sh logs-backend

# 实时查看前端日志
./manage-supervisor.sh logs-frontend
```

更多命令（单服务启停、热加载配置、透传 supervisorctl 等）：
```bash
./manage-supervisor.sh help
```

#### 启动流程

`./manage-supervisor.sh start` 会自动完成：
1. 创建必要的数据目录（`data/run/`、`data/logs/supervisor/`）
2. 导出环境变量（ENV_USER、ENV_PROJECT_ROOT）
3. 启动 supervisord 守护进程
4. supervisord 依次启动后端（`vvt-backend`，priority 90）和前端（`vvt-frontend`，priority 100）
5. 服务默认在后台存活，即使关闭终端也不影响

#### 访问服务

- **前端界面**：`http://localhost:5173` 或 `http://<服务器IP>:5173`
- **后端 API**：`http://localhost:8000`
- **API 文档**：`http://localhost:8000/docs`（Swagger UI）

#### 功能特性

- **视频文件上传**：支持拖拽或点击上传视频/音频文件
- **源语言和目标语言选择**：选择源语言和目标语言
- **模型预加载状态显示**：显示模型加载状态
- **处理进度实时显示**：实时显示处理进度和当前步骤
- **结果预览和下载**：预览翻译结果并下载最终视频

#### 单独启动 / 停止单个服务

```bash
# 仅重启后端（不会影响前端）
./manage-supervisor.sh restart-backend

# 仅停止前端
./manage-supervisor.sh ctl stop vvt-frontend

# 仅启动前端
./manage-supervisor.sh ctl start vvt-frontend
```

#### 修改配置后热加载（不停服务）

如果您修改了 `supervisor/supervisord.conf` 或 `supervisor/conf.d/*.ini`：
```bash
./manage-supervisor.sh reload
```
这会重新读取配置并按需重启受影响的服务。

#### API 使用

后端提供了 RESTful API，可以用于集成到其他系统：

- 查看 API 文档：访问 `http://localhost:8000/docs`
- 健康检查：`GET /health`
- 其他 API 端点请参考 API 文档

---

### 命令行方式

命令行方式适合批量处理和自动化场景。

#### 单个文件翻译

**推荐方式：使用启动脚本**（自动激活虚拟环境并设置环境变量）

```bash
# 自动检测语言并翻译
./run_cli.sh input.mp4

# 指定源语言和目标语言
./run_cli.sh input.mp4 --source-lang zh --target-lang en

# 英文视频翻译成中文
./run_cli.sh input.mp4 --source-lang en --target-lang zh

# 中文视频翻译成英文
./run_cli.sh input.mp4 --source-lang zh --target-lang en

# 指定输出目录
./run_cli.sh input.mp4 --output-dir my_output

# 启用详细日志
./run_cli.sh input.mp4 --verbose

# 指定仅一人说话（推荐：跳过说话人分离，提升处理速度和准确性）
./run_cli.sh input.mp4 --source-lang en --target-lang zh --single-speaker

# 步骤4后暂停，允许编辑分段
./run_cli.sh input.mp4 --pause-after step4

# 步骤5后暂停，允许编辑翻译结果
./run_cli.sh input.mp4 --pause-after step5

# 从步骤5继续（使用编辑后的分段）
./run_cli.sh input.mp4 --continue-from step5 --task-dir data/outputs/2025-01-15_14-30-25_input_video

# 从步骤6继续（使用编辑后的翻译结果）
./run_cli.sh input.mp4 --continue-from step6 --task-dir data/outputs/2025-01-15_14-30-25_input_video
```

#### 命令行参数说明

**基本参数**：
- `input_file`：输入视频或音频文件路径（必需）
- `--source-lang`：源语言（auto、zh、en），默认 auto
- `--target-lang`：目标语言（auto、zh、en），默认 auto
- `--output-dir`：输出目录，默认 `data/outputs`
- `--voice-model`：音色克隆模型（index-tts2、xtts），默认 index-tts2
- `--single-speaker`：仅一人说话，跳过说话人分离步骤（**推荐启用**，当前说话人分离效果有限，启用此选项可提升处理速度和准确性）
- `--verbose, -v`：显示详细日志

**编辑和继续执行参数**：
- `--pause-after`：在指定步骤完成后暂停，允许手动编辑文件
  - 可选值：`step4`（步骤4：语音识别后）、`step5`（步骤5：文本翻译后）
  - 示例：`--pause-after step4` 在语音识别完成后暂停，允许编辑分段
- `--continue-from`：从指定步骤继续执行（需要配合 `--task-dir` 使用）
  - 可选值：`step5`（从步骤5继续）、`step6`（从步骤6继续）
  - 示例：`--continue-from step5 --task-dir <任务目录>`
- `--task-dir`：任务目录路径（用于 `--continue-from` 参数）
  - 指定要继续的任务目录路径
  - 必须与 `--continue-from` 一起使用

#### 手动方式（需要先激活虚拟环境）

如果直接使用 `python media_translation_cli.py`，需要先手动激活虚拟环境；`.env` 中的变量也会被自动加载（前提是安装了 `python-dotenv`：

```bash
# 1. 激活虚拟环境
cd index-tts
source .venv/bin/activate
cd ..

# 2. 设置环境变量（也可不设；如果你在 .env 里填了 HF_ENDPOINT/DASHSCOPE_API_KEY 等，会被自动加载
#    没装 python-dotenv 才手动设一下
pip install -q python-dotenv

# 3. 运行翻译命令
python media_translation_cli.py input.mp4 --source-lang en --target-lang zh
```

⚠️ **注意**：直接运行 `python media_translation_cli.py` 会漏掉以下重要步骤：
- 激活 IndexTTS2 虚拟环境
- 设置 HuggingFace 镜像地址
- 配置 CUDA/CuDNN 运行时库路径
- 检查并安装缺失的依赖

因此，**强烈推荐使用启动脚本** `./run_cli.sh`。

---

### 批量处理

批量处理功能适合需要处理多个文件的场景，支持模型预加载以提升处理速度。

#### 方式一：使用批量处理脚本（推荐，自动预加载模型）

```bash
# 批量翻译多个文件（自动预加载模型，顺序处理）
./batch_translate.sh file1.mp4 file2.mp4 file3.mp4 --source-lang en --target-lang zh

# 批量翻译时指定其他选项
./batch_translate.sh file1.mp4 file2.mp4 --source-lang en --target-lang zh --single-speaker

# 仅预加载模型，不执行翻译
./batch_translate.sh --preload-only

# 跳过预加载，直接翻译（每个任务都会加载模型）
./batch_translate.sh --no-preload file1.mp4 file2.mp4 --source-lang en --target-lang zh
```

#### 批量处理脚本参数

- `--preload-only`：仅预加载模型，不执行翻译
- `--no-preload`：跳过模型预加载，直接翻译
- `--help, -h`：显示帮助信息

#### 方式二：手动预加载后顺序处理

```bash
# 步骤1: 预加载所有模型（只需执行一次）
./preload_models.sh

# 步骤2: 顺序执行多个翻译任务（自动复用预加载的模型）
./run_cli.sh file1.mp4 --source-lang en --target-lang zh
./run_cli.sh file2.mp4 --source-lang en --target-lang zh
./run_cli.sh file3.mp4 --source-lang en --target-lang zh
```

#### 模型预加载的优势

- 🚀 **提升速度**：后续翻译任务无需重复加载模型，显著减少处理时间
- 💾 **节省内存**：通过单例模式复用已加载的模型实例
- 📊 **批量处理**：特别适合顺序处理多个翻译任务

#### 注意事项

- 预加载的模型状态保存在 `/tmp/voice_clone_preloader_available` 文件中
- 如果进程重启或模型需要更新，请删除该文件后重新预加载
- 批量处理脚本会在开始时自动检查并预加载模型

---

## 参考资料

- [README.md](../README.md) - 项目主文档
- [安装指南](INSTALL.md) - 详细的安装和配置说明
- [流程文档](WORKFLOW.md) - 完整的9步骤流程说明和设计要点
