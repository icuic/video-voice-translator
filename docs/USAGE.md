# Video Voice Translator - 使用指南

## 目录

- [快速开始](#快速开始)
- [使用方法](#使用方法)
  - [Web UI 方式](#web-ui-方式推荐)
  - [命令行方式](#命令行方式)
  - [批量处理](#批量处理)

---

## 快速开始

如果您还没有安装系统，请先参考 [安装指南](INSTALL.md) 完成安装和配置。

安装完成后，您可以：

**Web UI 方式**（推荐）：

```bash
./run_webui.sh
```

启动后访问 `http://localhost:7861`

**命令行方式**：

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

### Web UI 方式（推荐）

Web UI 提供了友好的图形界面，适合不熟悉命令行的用户使用。

#### 启动 Web UI

```bash
./run_webui.sh
```

启动脚本会自动：
- 激活 index-tts 虚拟环境
- 检查并安装缺失的主项目额外依赖
- 设置必要的环境变量
- 启动 Web UI 服务器

#### 访问 Web UI

启动成功后，访问 `http://localhost:7861`（如果在本机）或 `http://<服务器IP>:7861`（如果在远程服务器）。

#### Web UI 功能

- **视频文件上传**：支持拖拽或点击上传视频/音频文件
- **源语言和目标语言选择**：选择源语言和目标语言
- **模型预加载状态显示**：显示模型加载状态
- **处理进度实时显示**：实时显示处理进度和当前步骤
- **结果预览和下载**：预览翻译结果并下载最终视频

#### 停止 Web UI

在终端中按 `Ctrl+C` 停止 Web UI 服务器。

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

如果直接使用 `python media_translation_cli.py`，需要先手动激活虚拟环境并设置环境变量：

```bash
# 1. 激活虚拟环境
cd index-tts
source .venv/bin/activate
cd ..

# 2. 设置环境变量
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HOME="${PWD}/index-tts/.cache/hf"
export PYTHONUNBUFFERED=1

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

