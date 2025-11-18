# 安装与配置指南

## 系统要求

- Python 3.10 或更高版本
- FFmpeg（系统依赖）
- CUDA（可选，用于GPU加速）
- 至少 8GB 内存（推荐 16GB 或更多）
- 足够的磁盘空间（用于模型和缓存）
- uv 包管理器（用于安装 index-tts 依赖）

## 系统依赖安装

在开始安装 Python 依赖之前，需要先安装系统级依赖。

### FFmpeg 安装

FFmpeg 是音视频处理的核心工具，必须安装。

**Ubuntu/Debian**：

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

**验证安装**：

```bash
ffmpeg -version
ffprobe -version
```

如果命令能正常显示版本信息，说明安装成功。

### 其他系统工具（可选）

**lsof**：用于检查端口占用情况（可选，但推荐安装）

```bash
sudo apt-get install -y lsof
```

## 安装步骤

### 前置步骤：安装 IndexTTS2

**重要**：本项目依赖 IndexTTS2 进行音色克隆功能。在安装主项目依赖之前，必须先完成 IndexTTS2 的安装。

**安装 IndexTTS2**：

1. **在项目根目录执行克隆命令**：
   ```bash
   # 确保您在项目根目录
   # 执行以下命令克隆 IndexTTS2 仓库
   git clone https://github.com/index-tts/index-tts.git
   ```

2. **按照官方文档完成安装**：
   - 官方仓库地址：https://github.com/index-tts/index-tts
   - 请参考官方 README 中的完整安装说明
   - 进入 `index-tts` 目录，按照官方文档执行安装步骤
   - 确保安装完成后，IndexTTS2 的虚拟环境位于 `index-tts/.venv`

**验证 IndexTTS2 安装**：
```bash
# 在项目根目录执行以下命令验证安装
# 检查 index-tts 目录是否存在
ls -la index-tts/

# 检查虚拟环境是否存在
ls -la index-tts/.venv/bin/activate

# 激活虚拟环境并验证 IndexTTS2 可以导入
cd index-tts
source .venv/bin/activate
python -c "from indextts.infer_v2 import IndexTTS2; print('IndexTTS2 安装成功')"
cd ..
```

### 安装主项目依赖

**说明**：完成 IndexTTS2 安装后，需要安装主项目的额外依赖。主项目的依赖文件是 `requirements_project.txt`，包含 IndexTTS2 中没有的依赖（如 faster-whisper、openai-whisper、pyannote 等）。

**重要提示**：
- 默认使用 **faster-whisper** 作为语音识别后端（基于 CTranslate2，速度更快）
- 同时也安装 **openai-whisper** 作为备选后端（基于 PyTorch）
- 可以在 `config.yaml` 中通过 `whisper.backend` 配置项切换后端

**主要依赖说明**：
- **faster-whisper** / **openai-whisper**：语音识别引擎
- **openai**：用于调用阿里云 DashScope API（Qwen 模型）进行文本翻译
- **resemblyzer**：用于说话人分离的语音编码器
- **ninja**：用于编译 IndexTTS2 的 CUDA kernel（加速推理）
- **pyannote.audio**：说话人分离模型
- **demucs**：音频分离模型（用于人声和背景音乐分离）
- **scipy**、**httpx**、**pydub**：其他工具依赖

**安装方式**：提供三种方式，选择其中一种即可：
- **方式一**：使用 uv 安装（推荐，速度最快）
- **方式二**：使用 pip 安装（备选方式）
- **方式三**：使用启动脚本（自动处理）

### 方式一：使用 uv 安装（推荐）

**优势**：uv 比 pip 快 10-100 倍，更可靠。

**前提条件**：确保已按照 [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) 完成 IndexTTS2 的安装。

```bash
# 1. 激活 IndexTTS2 的虚拟环境
cd index-tts
source .venv/bin/activate
cd ..

# 2. 使用 uv 安装主项目额外依赖（推荐）
# uv pip install 会自动使用当前激活的虚拟环境
uv pip install -r requirements_project.txt

# 3. 验证安装
python tools/check_dependencies.py
# 或使用快速验证（根据配置的后端选择）
# 如果使用 faster-whisper（默认）:
python -c "import gradio; import faster_whisper; import scipy; print('依赖安装成功')"
# 如果使用 openai-whisper:
python -c "import gradio; import whisper; import scipy; print('依赖安装成功')"
```

**或者使用便捷脚本**：

```bash
# 使用官方源
./scripts/install/install_with_uv.sh

# 或使用国内镜像源（推荐国内用户）
./scripts/install/install_with_uv_china.sh
```

### 方式二：使用 pip 安装

如果无法使用 uv，也可以使用传统的 pip 方式：

**前提条件**：确保已按照 [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) 完成 IndexTTS2 的安装。

```bash
# 1. 激活 IndexTTS2 的虚拟环境
cd index-tts
source .venv/bin/activate

# 2. 返回项目根目录，安装主项目额外依赖
cd ..
pip install -r requirements_project.txt

# 3. 验证安装
python tools/check_dependencies.py
```

### 方式三：使用启动脚本自动安装

```bash
# 直接运行启动脚本，会自动激活虚拟环境并检查依赖
./run_webui.sh
```

启动脚本会自动：
- 激活 index-tts 虚拟环境
- 检查并安装缺失的主项目额外依赖
- 启动 Web UI

## 环境变量配置

### DASHSCOPE_API_KEY 配置（翻译功能必需）

本项目使用阿里云 DashScope（Qwen）API 进行文本翻译，需要配置 API 密钥。

**获取 API 密钥**：

1. 访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)
2. 注册/登录账号
3. 创建 API 密钥
4. 复制 API 密钥

**配置方式**：

在 `~/.bashrc` 文件中添加：

```bash
export DASHSCOPE_API_KEY='your-api-key-here'
```

然后重新加载配置：

```bash
source ~/.bashrc
```

**验证配置**：

启动脚本会自动从 `~/.bashrc` 读取 `DASHSCOPE_API_KEY`，并在启动时显示是否已设置：

- ✅ 如果已设置：会显示 `✅ DASHSCOPE_API_KEY已设置（长度: XX）`
- ⚠️ 如果未设置：会显示警告信息，翻译功能将无法使用

**注意**：启动脚本使用非交互式 shell，无法直接 source `~/.bashrc`，所以脚本会直接从文件中读取环境变量值。

### HF_ENDPOINT 配置（可选，国内用户推荐）

如果访问 HuggingFace 较慢，可以配置国内镜像源。

**配置方式**：

在 `~/.bashrc` 文件中添加：

```bash
export HF_ENDPOINT="https://hf-mirror.com"
```

启动脚本会自动读取此配置。

## 下一步

安装完成后，您可以：

- 查看 [使用指南](USAGE.md) 了解如何使用系统
- 查看 [流程文档](WORKFLOW.md) 了解系统工作原理

## 参考资源

- [README.md](../README.md) - 项目主文档
- [使用指南](USAGE.md) - 完整的使用方法和示例
- [流程文档](WORKFLOW.md) - 完整的9步骤流程说明
- [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) - 音色克隆子模块官方文档
