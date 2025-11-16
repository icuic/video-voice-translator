# Voice Clone Lingua Shift - 使用指南

## 目录

- [项目概述](#项目概述)
- [系统要求](#系统要求)
- [安装步骤](#安装步骤)
- [配置说明](#配置说明)
- [使用方法](#使用方法)
  - [Web UI 方式](#web-ui-方式推荐)
  - [命令行方式](#命令行方式)
  - [批量处理](#批量处理)
- [处理流程](#处理流程)
- [输出文件说明](#输出文件说明)
- [性能优化](#性能优化)
- [故障排除](#故障排除)
- [常见问题](#常见问题)

---

## 项目概述

**Voice Clone Lingua Shift** 是一个基于人工智能技术的多语言音视频翻译系统，能够将视频或音频内容从一种语言翻译成另一种语言，并通过音色克隆技术保持原说话者的声音特征。

### 核心功能

- **视频与音频处理**：支持多种视频格式（MP4、AVI、MOV、MKV等）和音频格式（WAV、MP3、M4A等）
- **智能音频分离**：自动检测并分离人声和背景音乐
- **高精度语音识别**：支持 Whisper 和 Faster-Whisper 两种后端
- **文本翻译**：使用大语言模型（Qwen系列）进行批量翻译
- **音色克隆**：基于 IndexTTS2 模型实现音色克隆，保持原说话者的声音特征
- **多说话人处理**：支持说话人分离，识别并区分不同说话者（可选，当前效果有限，建议使用 `--single-speaker` 选项）

### 支持的语言

- 中文（简体）
- 英文

---

## 系统要求

### 硬件要求

- **CPU**：支持现代多核处理器
- **内存**：至少 8GB RAM（推荐 16GB 或更多）
- **存储**：足够的磁盘空间（用于模型和缓存，建议至少 20GB）
- **GPU**：可选，支持 NVIDIA GPU 和 CUDA（用于 GPU 加速）

### 软件要求

- **操作系统**：Linux（推荐）、macOS、Windows
- **Python**：3.10 或更高版本
- **FFmpeg**：系统依赖，用于音视频处理
- **CUDA**：可选，用于 GPU 加速（如果使用 GPU）
- **uv 包管理器**：用于安装 index-tts 依赖

### 网络要求

- 需要访问阿里云 DashScope API（用于文本翻译）
- 需要访问 HuggingFace 或镜像站（用于下载模型）

---

## 安装步骤

### 步骤 1：安装 index-tts 依赖（包含 Web UI 支持）

```bash
cd index-tts
uv sync --extra webui
```

**注意**：如果系统未安装 `uv`，请先安装：

```bash
# 安装 uv
pip install uv

# 或者使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 步骤 2：激活虚拟环境并安装主项目额外依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 返回项目根目录
cd ..

# 安装主项目额外依赖
pip install -r requirements_project.txt
```

### 步骤 3：安装 FFmpeg（如果未安装）

```bash
# Ubuntu/Debian:
sudo apt update && sudo apt install ffmpeg

# CentOS/RHEL:
sudo yum install ffmpeg

# macOS:
brew install ffmpeg

# Windows:
# 下载 FFmpeg 并添加到系统 PATH
```

### 步骤 4：配置 API 密钥

本项目使用阿里云 DashScope（Qwen）API 进行文本翻译，需要配置 API 密钥。

#### 获取 API 密钥

1. 访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)
2. 注册/登录账号
3. 创建 API 密钥
4. 复制 API 密钥

#### 设置环境变量

**Linux/macOS**：

```bash
# 临时设置（当前终端会话有效）
export DASHSCOPE_API_KEY='your-api-key-here'

# 持久化配置（推荐）- 添加到 ~/.bashrc 或 ~/.zshrc
echo 'export DASHSCOPE_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell)**：

```powershell
# 临时设置
$env:DASHSCOPE_API_KEY="your-api-key-here"

# 持久化配置 - 添加到系统环境变量
[System.Environment]::SetEnvironmentVariable("DASHSCOPE_API_KEY", "your-api-key-here", "User")
```

**Windows (CMD)**：

```cmd
REM 临时设置
set DASHSCOPE_API_KEY=your-api-key-here

REM 持久化配置 - 通过系统设置添加环境变量
```

### 步骤 5：验证安装

```bash
# 检查依赖安装状态
python tools/check_dependencies.py

# 或者快速验证关键模块
python -c "import torch; import gradio; import whisper; import scipy; print('所有依赖已正确安装')"
```

如果所有依赖都已正确安装，将显示成功消息。

---

## 配置说明

系统通过 `config.yaml` 文件进行配置。主要配置项包括：

### 音频处理配置

```yaml
audio:
  sample_rate: 16000  # 采样率 (Hz)
  format: "wav"       # 输出格式
  channels: 1         # 声道数 (单声道)
  bit_depth: 16      # 位深度
```

### Whisper 语音识别配置

```yaml
whisper:
  backend: "faster-whisper"  # 后端选择: "whisper" 或 "faster-whisper"
  model_size: "medium"       # 模型大小: tiny, base, small, medium, large, large-v2, large-v3
  language: "auto"           # 语言检测: auto 或具体语言代码
  device: "cuda"             # 设备类型: auto, cpu, cuda
  fp16: false                # FP16精度加速（需要GPU支持）
  
  # Faster-Whisper 专用参数
  faster_whisper_params:
    beam_size: 5                      # 束搜索大小
    condition_on_previous_text: false # 关闭跨段上下文
    vad_filter: true                  # 启用VAD过滤
  
  # 分段优化配置
  segmentation:
    method: "semantic"         # 分段方法: "punctuation" 或 "semantic"
    min_segment_duration: 1.5  # 最小分段时长（秒）
    max_segment_duration: 8.0  # 最大分段时长（秒）
```

### 文本翻译配置

```yaml
translation:
  source_language: "zh"
  target_language: "en"
  model: "qwen-flash"              # 翻译模型（支持 qwen-plus、qwen-max、qwen3-max-2025-09-23 等）
  retry_strategy: "adaptive"       # 重试策略: "simple" 或 "adaptive"
  max_batch_size: 20               # 批量翻译时一次最多处理的段落数
  max_retries: 3                   # 简单重试策略的最大重试次数
  enable_content_validation: true  # 启用内容验证
```

### 音色克隆配置

```yaml
voice_cloning:
  model_path: "./index-tts"    # IndexTTS2模型目录
  device: "cuda"               # 设备类型
  sample_rate: 16000           # 采样率
  max_text_tokens: 600         # 最大文本token数
  max_mel_tokens: 1815         # 最大mel token数
  enable_parallel: true         # 启用并行处理
  max_parallel_workers: 2       # 最大并行工作线程数
```

### 音频分离配置

```yaml
audio_separation:
  enable_gpu: true           # 启用GPU加速
  quality_threshold: 0.3     # 背景音乐检测阈值
  model: "2stems-16kHz"      # 分离模型
```

### 说话人分离配置

```yaml
speaker_tracks:
  enabled: true              # 启用多说话人处理
  compact_concat: true       # 紧凑拼接音轨
  min_gap_merge_ms: 100      # 最小间隔合并（毫秒）
```

**完整配置说明请参考 `config.yaml` 文件中的注释。**

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

## 处理流程

系统采用九步处理流程完成视频翻译：

```
原始视频/音频
    ↓
[步骤1] 视频/音频处理 - 提取音频轨道，格式标准化
    ↓
[步骤2] 音频分离 - 检测并分离人声和背景音乐
    ↓
[步骤3] 多说话人处理（可选）- 识别不同说话者，生成紧凑音轨
    ↓
[步骤4] 语音识别 + 分段优化 - 使用Whisper/Faster-Whisper进行转录
    ↓
[步骤5] 文本翻译 - 批量翻译文本分段
    ↓
[步骤6] 参考音频提取 - 为每个翻译片段提取对应的参考音频
    ↓
[步骤7] 音色克隆 - 为每个翻译片段生成保持原音色的语音
    ↓
[步骤8] 时间同步音频合并 - 根据时间戳同步合并音频片段
    ↓
[步骤9] 视频合成 - 将翻译后的音频与原始视频合成
    ↓
最终翻译视频
```

### 详细步骤说明

#### 步骤 1：视频/音频处理

- **输入**：视频文件（MP4、AVI、MOV、MKV等）或音频文件（WAV、MP3、M4A等）
- **处理**：提取音频轨道，格式标准化（16kHz、单声道、WAV格式），提取元数据
- **输出**：`*_01_audio.wav` - 提取并标准化的音频文件

#### 步骤 2：音频分离

- **输入**：`*_01_audio.wav`
- **处理**：使用 Demucs 模型分析音频特征，检测并分离人声和背景音乐
- **输出**：
  - `*_02_vocals.wav` - 人声轨道（必需）
  - `*_02_accompaniment.wav` - 背景音乐轨道（可选，仅当检测到背景音乐时）

#### 步骤 3：多说话人处理（可选，当前效果有限）

- **输入**：`*_02_vocals.wav`（人声轨道）
- **处理**：使用说话人分离技术（PyAnnote）识别不同说话者，为每个说话人生成紧凑音轨，构建全局时间与紧凑时间的映射关系
- **注意**：当前说话人分离效果有限，建议使用 `--single-speaker` 选项跳过此步骤
- **输出**：
  - `speakers/<speaker_id>/<speaker_id>.wav` - 各说话人的紧凑音轨
  - `speakers/<speaker_id>/<speaker_id>.json` - 时间映射表（全局时间 ↔ 紧凑时间）

#### 步骤 4：语音识别 + 分段优化

- **输入**：
  - 单说话人场景：`*_02_vocals.wav`
  - 多说话人场景：`speakers/<speaker_id>/<speaker_id>.wav`
- **处理**：使用 Whisper/Faster-Whisper 进行转录，生成单词级别的时间戳，分段优化（基于标点符号或语义）
- **输出**：
  - `*_04_whisper_raw_transcription.txt` - 完整转录文本
  - `*_04_whisper_raw_word_timestamps.txt` - 单词级时间戳
  - `*_04_segments.txt` - 分段文本
  - `*_04_segments.json` - 分段数据（JSON格式，包含时间戳和文本）

#### 步骤 5：文本翻译

- **输入**：`*_04_segments.json`（分段数据）
- **处理**：使用 Qwen 大语言模型批量翻译文本分段，自动跳过相同语言的翻译任务
- **输出**：
  - `*_05_translation.txt` - 翻译结果（带时间戳）
  - `*_05_llm_interaction.txt` - LLM 交互记录（调试用）

#### 步骤 6：参考音频提取

- **输入**：翻译后的分段数据（带时间戳），`*_02_vocals.wav` 或 `speakers/<speaker_id>.wav`
- **处理**：为每个翻译片段提取对应的参考音频（多说话人场景优先从说话人紧凑音轨裁剪）
- **输出**：`ref_audio/*_06_ref_segment_*.wav` - 各片段的参考音频

#### 步骤 7：音色克隆

- **输入**：`ref_audio/*_06_ref_segment_*.wav`（参考音频片段），翻译后的文本分段
- **处理**：使用 IndexTTS2 模型进行音色克隆，保持原说话者的音色、语速、情感特征
- **输出**：`cloned_audio/*_07_segment_*.wav` - 各片段的克隆音频

#### 步骤 8：时间同步音频合并

- **输入**：所有片段的克隆音频，每个片段的时间戳信息，原始音频总时长
- **处理**：根据时间戳将每个片段插入到正确位置，处理时长调整和重叠问题，混合背景音乐（如果存在）
- **输出**：`*_08_final_voice.wav` - 完整的翻译配音轨道

#### 步骤 9：视频合成

- **输入**：原始视频文件，`*_08_final_voice.wav`（翻译配音），`*_02_accompaniment.wav`（背景音乐，可选）
- **处理**：使用 FFmpeg 将翻译后的音频与原始视频合成
- **输出**：`*_09_translated.mp4` - 最终翻译视频

---

## 输出文件说明

处理完成后，系统会在输出目录中按任务创建独立目录（格式：`时间戳_文件名`），并生成以下文件：

### 步骤 1：音频提取

- `<文件名>_01_audio.wav` - 提取的原始音频（16kHz，单声道）

### 步骤 2：音频分离

- `<文件名>_02_vocals.wav` - 分离后的人声轨道
- `<文件名>_02_accompaniment.wav` - 背景音乐轨道（如果存在）

### 步骤 3：多说话人处理（如果启用）

- `speakers/<speaker_id>/<speaker_id>.wav` - 各说话人的紧凑音轨
- `speakers/<speaker_id>/<speaker_id>.json` - 时间映射表（全局时间 ↔ 紧凑时间）

### 步骤 4：语音识别

**主任务目录**（合并后的结果，全局时间）：
- `<文件名>_04_whisper_raw_transcription.txt` - 完整转录文本
- `<文件名>_04_whisper_raw_word_timestamps.txt` - 单词级时间戳（调试用）
- `<文件名>_04_whisper_raw_segments.txt` - Whisper 原始分段文本（可读格式，调试用）
- `<文件名>_04_segments.txt` - 分段文本
- `<文件名>_04_segments.json` - 分段数据（JSON格式，包含时间戳和文本）
- `<文件名>_04_whisper_raw.json` - Whisper 原始输出（调试用）

**多说话人场景 - speakers目录**（各说话人的原始结果，紧凑时间）：
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw.json` - 说话人的 Whisper 原始输出（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_segments.txt` - 说话人的 Whisper 原始分段文本（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_transcription.txt` - 说话人的转录文本（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_word_timestamps.txt` - 说话人的单词级时间戳（紧凑时间）

**注意**：多说话人场景下，speakers 目录中的文件使用**紧凑时间**，主任务目录中的文件使用**全局时间**。

### 步骤 5：文本翻译

- `<文件名>_05_translation.txt` - 翻译结果（带时间戳）
- `<文件名>_05_llm_interaction.txt` - LLM 交互记录（调试用）

### 步骤 6：参考音频提取

- `ref_audio/<文件名>_06_ref_segment_000.wav` - 片段0的参考音频
- `ref_audio/<文件名>_06_ref_segment_001.wav` - 片段1的参考音频
- `ref_audio/<文件名>_06_ref_segment_*.wav` - 其他片段的参考音频

### 步骤 7：音色克隆

- `cloned_audio/<文件名>_07_segment_000.wav` - 片段0的克隆音频
- `cloned_audio/<文件名>_07_segment_001.wav` - 片段1的克隆音频
- `cloned_audio/<文件名>_07_segment_*.wav` - 其他片段的克隆音频

### 步骤 8：音频合并

- `<文件名>_08_final_voice.wav` - 完整的翻译配音轨道

### 步骤 9：视频合成

- `<文件名>_09_translated.mp4` - 最终翻译视频

### 其他文件

- `processing_log.txt` - 处理日志
- `translation_stats.json` - 性能统计（JSON格式）
- `translation_stats.csv` - 性能统计（CSV格式）

### 完整目录结构示例

```
data/outputs/
└── 2025-01-15_14-30-25_input_video/
    ├── input_video_01_audio.wav              # 步骤1: 音频提取
    ├── input_video_02_vocals.wav             # 步骤2: 人声轨道
    ├── input_video_02_accompaniment.wav      # 步骤2: 背景音乐（可选）
    │
    ├── speakers/                             # 步骤3: 多说话人处理（可选）
    │   ├── SPEAKER_00/
    │   │   ├── SPEAKER_00.wav
    │   │   └── SPEAKER_00.json
    │   └── SPEAKER_01/
    │       ├── SPEAKER_01.wav
    │       └── SPEAKER_01.json
    │
    ├── input_video_04_whisper_raw_transcription.txt      # 步骤4: 完整转录文本
    ├── input_video_04_whisper_raw_word_timestamps.txt    # 步骤4: 单词级时间戳
    ├── input_video_04_segments.txt           # 步骤4: 分段文本
    ├── input_video_04_segments.json          # 步骤4: 分段数据（JSON）
    │
    ├── input_video_05_translation.txt        # 步骤5: 翻译结果
    ├── input_video_05_llm_interaction.txt    # 步骤5: LLM交互记录
    │
    ├── ref_audio/                            # 步骤6: 参考音频
    │   ├── input_video_06_ref_segment_000.wav
    │   ├── input_video_06_ref_segment_001.wav
    │   └── ...
    │
    ├── cloned_audio/                          # 步骤7: 克隆音频
    │   ├── input_video_07_segment_000.wav
    │   ├── input_video_07_segment_001.wav
    │   └── ...
    │
    ├── input_video_08_final_voice.wav        # 步骤8: 完整配音轨道
    ├── input_video_09_translated.mp4         # 步骤9: 最终翻译视频
    │
    ├── processing_log.txt                    # 处理日志
    ├── translation_stats.json                # 性能统计（JSON）
    └── translation_stats.csv                 # 性能统计（CSV）
```

---

## 性能优化

### 模型预加载

启动时预加载模型，避免首次使用延迟：

```bash
# 预加载所有模型
./preload_models.sh

# 或使用批量处理脚本自动预加载
./batch_translate.sh --preload-only
```

### GPU 加速

在 `config.yaml` 中启用 GPU 加速：

```yaml
whisper:
  device: "cuda"  # 使用 GPU 加速

voice_cloning:
  device: "cuda"  # 使用 GPU 加速

audio_separation:
  enable_gpu: true  # 启用 GPU 加速
```

### FP16 精度

在 `config.yaml` 中启用 FP16 精度（需要 GPU 支持）：

```yaml
whisper:
  fp16: true  # 启用 FP16 精度加速

voice_cloning:
  # IndexTTS2 默认使用 FP16 精度
```

### 批量处理

文本翻译采用批量处理，在 `config.yaml` 中调整批量大小：

```yaml
translation:
  max_batch_size: 20  # 批量翻译时一次最多处理的段落数
```

### 并行处理

音色克隆支持并行处理，在 `config.yaml` 中调整并行工作线程数：

```yaml
voice_cloning:
  enable_parallel: true        # 启用并行处理
  max_parallel_workers: 2      # 最大并行工作线程数
```

### 使用 Faster-Whisper 后端

Faster-Whisper（基于 CTranslate2）比原生 Whisper 更快：

```yaml
whisper:
  backend: "faster-whisper"  # 使用 Faster-Whisper 后端
```

---

## 故障排除

### 常见问题

#### 1. 依赖安装失败

**问题**：运行 `pip install -r requirements_project.txt` 失败

**解决方案**：
- 确保已激活 `index-tts/.venv` 虚拟环境
- 运行 `python tools/check_dependencies.py` 检查依赖状态
- 升级 pip：`pip install --upgrade pip`
- 使用国内镜像源（如果网络较慢）：
  ```bash
  pip install -r requirements_project.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```

#### 2. GPU 加速不可用

**问题**：系统提示 GPU 加速不可用

**解决方案**：
- 检查 CUDA 是否安装：`nvidia-smi`
- 检查 PyTorch 是否支持 CUDA：
  ```bash
  python -c "import torch; print(torch.cuda.is_available())"
  ```
- 如果返回 False，需要重新安装支持 CUDA 的 PyTorch
- 或者在配置文件中设置 `device: "cpu"` 使用 CPU 模式

#### 3. 处理速度慢

**问题**：翻译处理速度很慢

**解决方案**：
- 启用模型预加载：`./preload_models.sh`
- 使用 GPU 加速（如果可用）
- 调整批量处理大小
- 使用 Faster-Whisper 后端（默认）
- 启用 FP16 精度（需要 GPU 支持）

#### 4. 内存不足

**问题**：处理过程中出现内存不足错误

**解决方案**：
- 减小批量处理大小（在 `config.yaml` 中调整 `max_batch_size`）
- 使用较小的 Whisper 模型（如 `small` 或 `base`）
- 关闭不必要的功能模块（如音频分离）
- 使用 CPU 模式（如果 GPU 内存不足）

#### 5. 翻译结果不准确

**问题**：翻译结果不准确或错误

**解决方案**：
- 检查源语言识别是否正确
- 调整翻译模型参数
- 检查音频质量（清晰度、背景噪音等）
- 尝试使用更大的 Whisper 模型（如 `large` 或 `large-v3`）

#### 6. API 密钥错误

**问题**：系统提示 API 密钥错误或未设置

**解决方案**：
- 检查环境变量 `DASHSCOPE_API_KEY` 是否已设置：
  ```bash
  echo $DASHSCOPE_API_KEY
  ```
- 确保 API 密钥正确且有效
- 重新设置环境变量并重启终端

#### 7. FFmpeg 未找到

**问题**：系统提示 FFmpeg 未安装或未找到

**解决方案**：
- 安装 FFmpeg（参考安装步骤）
- 确保 FFmpeg 在系统 PATH 中：
  ```bash
  which ffmpeg
  ```
- 如果已安装但未在 PATH 中，添加到 PATH 或重新安装

#### 8. 虚拟环境激活失败

**问题**：无法激活虚拟环境

**解决方案**：
- 确保已安装 index-tts 依赖：
  ```bash
  cd index-tts
  uv sync --extra webui
  ```
- 检查虚拟环境是否存在：
  ```bash
  ls -la index-tts/.venv/bin/activate
  ```
- 如果不存在，重新创建虚拟环境

---

## 常见问题

### Q: 为什么使用 index-tts 子模块的虚拟环境？

A: 因为主项目代码直接导入 `from indextts.infer_v2 import IndexTTS2`，需要在同一个 Python 环境中。使用子模块的虚拟环境可以：
- 避免依赖版本冲突
- 简化部署流程
- 确保 AI 模型库版本匹配

### Q: 可以修改 index-tts 的依赖吗？

A: **不建议**。index-tts 的依赖版本是经过严格测试的，修改可能导致：
- 模型推理失败
- CUDA 加速失效
- 其他不可预期的问题

### Q: 如何更新依赖？

```bash
# 更新 index-tts 依赖
cd index-tts
uv sync --upgrade

# 更新主项目额外依赖
source .venv/bin/activate
pip install --upgrade -r ../requirements_project.txt
```

### Q: 如何处理多说话人场景？

A: **推荐使用 `--single-speaker` 选项**。当前说话人分离效果有限，建议在大多数情况下启用此选项以获得更好的处理效果和准确性：

```bash
# 推荐：跳过说话人分离，提升处理速度和准确性
./run_cli.sh input.mp4 --source-lang en --target-lang zh --single-speaker
```

如果确实需要处理多说话人场景，可以省略 `--single-speaker` 参数，系统会尝试进行说话人分离，但效果可能不理想。

### Q: 如何查看处理日志？

A: 处理日志保存在任务目录中的 `processing_log.txt` 文件中。Web UI 方式还会在终端和日志文件中显示实时日志。

### Q: 输出文件在哪里？

A: 输出文件默认保存在 `data/outputs/` 目录中，按任务创建独立目录（格式：`时间戳_文件名`）。可以通过 `--output-dir` 参数指定自定义输出目录。

### Q: 支持哪些视频格式？

A: 支持多种视频格式（MP4、AVI、MOV、MKV等）和音频格式（WAV、MP3、M4A等）。系统会自动检测文件类型并处理。

### Q: 如何提高翻译质量？

A: 
- 使用更大的 Whisper 模型（如 `large` 或 `large-v3`）
- 确保音频质量清晰，减少背景噪音
- 使用合适的翻译模型（如 `qwen-max` 或 `qwen3-max-2025-09-23`）
- 检查源语言识别是否正确

### Q: 处理时间需要多久？

A: 处理时间取决于多个因素：
- 视频/音频时长
- 使用的模型大小
- 是否使用 GPU 加速
- 系统硬件性能

一般来说，使用 GPU 加速时，处理 1 分钟的视频大约需要 2-5 分钟（取决于模型大小和系统性能）。

---

## 参考资料

- [README.md](../README.md) - 项目主文档
- [INSTALL.md](INSTALL.md) - 详细安装指南
- [流程文档](WORKFLOW.md) - 完整流程说明和设计要点
- [开发指南](DEVELOPER_GUIDE.md) - 技术实现细节和开发参考

---

## 许可证

本项目采用 MIT 许可证。

---

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目。

---

**最后更新**：2025-01-15

