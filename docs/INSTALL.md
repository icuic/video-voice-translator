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

## 项目架构说明

本项目依赖 `index-tts` 子模块，使用子模块的虚拟环境运行。这是为了：

1. **依赖隔离**：index-tts 有严格的依赖版本要求，使用其虚拟环境可避免冲突
2. **简化部署**：子模块已管理了大部分核心依赖
3. **版本一致性**：确保 AI 模型库的版本匹配

## 安装步骤

### 方式一：推荐方式（使用 uv 安装，与 index-tts 管理方式一致）

**优势**：uv 比 pip 快 10-100 倍，更可靠，与 index-tts 的依赖管理方式一致。

```bash
# 1. 首先安装 index-tts 的依赖（包含 Web UI 支持）
cd index-tts
uv sync --extra webui

# 2. 使用 uv 安装主项目额外依赖（推荐）
# uv pip install 会自动使用 index-tts 的虚拟环境
uv pip install -r ../requirements_project.txt

# 3. 验证安装
cd ..
source index-tts/.venv/bin/activate
python tools/check_dependencies.py
# 或使用快速验证
python -c "import gradio; import whisper; import scipy; print('依赖安装成功')"
```

**或者使用便捷脚本**：

```bash
# 使用官方源
./scripts/install/install_with_uv.sh

# 或使用国内镜像源（推荐国内用户）
./scripts/install/install_with_uv_china.sh
```

### 方式二：使用 pip 安装（备选方式）

如果无法使用 uv，也可以使用传统的 pip 方式：

```bash
# 1. 首先安装 index-tts 的依赖（包含 Web UI 支持）
cd index-tts
uv sync --extra webui

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 返回项目根目录，安装主项目额外依赖
cd ..
pip install -r requirements_project.txt

# 4. 验证安装
python tools/check_dependencies.py
```

### 方式三：使用启动脚本（自动处理）

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

## 依赖文件说明

| 文件 | 用途 | 何时使用 |
|------|------|----------|
| `index-tts/pyproject.toml` | index-tts 子模块的完整依赖定义 | 子模块安装时使用 |
| `requirements_project.txt` | **主项目额外依赖**（子模块中没有的） | 在主项目安装时使用 |
| `tools/check_dependencies.py` | 依赖检查脚本 | 验证依赖安装状态时使用 |

## 依赖管理策略

### 为什么这样设计？

1. **index-tts 是子模块**：有自己的依赖管理（`pyproject.toml`），使用 `uv sync` 管理，虚拟环境在 `index-tts/.venv`
2. **主项目共享虚拟环境**：通过激活子模块的虚拟环境来运行，避免创建重复的虚拟环境
3. **只管理增量依赖**：主项目的 `requirements_project.txt` 只包含子模块中没有的依赖
4. **为什么不用 `uv add`**：
   - `uv add` 需要 `pyproject.toml`，会在主项目根目录创建新的虚拟环境（`.venv`）
   - 这会与共享 `index-tts/.venv` 的架构冲突
   - `uv pip install` 可以指定虚拟环境路径，更适合当前架构

### 两个 pyproject.toml 的关系

- **`index-tts/pyproject.toml`**：index-tts 子模块的依赖定义，使用 `uv sync` 管理
- **主项目不使用 `pyproject.toml`**：避免创建独立的虚拟环境，保持架构简单
- **`requirements_project.txt`**：主项目的增量依赖列表，使用 `uv pip install` 安装到共享虚拟环境

### 依赖分类

#### 已在 index-tts 中（无需重复安装）

以下依赖已在 index-tts 的 `pyproject.toml` 中定义，安装 index-tts 时会自动安装：

- torch, torchaudio
- transformers, accelerate
- librosa, soundfile, numpy
- ffmpeg-python, opencv-python
- resemblyzer
- gradio（在 optional-dependencies.webui 中）

**注意**：虽然 `demucs` 在 index-tts 的依赖列表中，但实际可能需要单独安装。如果遇到 `No module named 'demucs'` 错误，请参考下面的安装方法。

#### 主项目额外需要

以下依赖需要在主项目中单独安装：

- `openai-whisper`：主项目使用，index-tts 用的是 faster-whisper
- `scipy`：用于音频分析
- `pyannote.audio`, `speechbrain`：说话人分离
- `httpx`：HTTP 客户端
- `pydub`：音频处理增强
- `tiktoken`：文本处理
- `demucs`：音频分离（可能需要单独安装，见下方说明）

### Demucs 模块安装

虽然 `demucs` 在 index-tts 的依赖列表中，但实际安装时可能需要单独安装。

**如果遇到 `No module named 'demucs'` 错误**：

```bash
cd index-tts
source .venv/bin/activate
python -m pip install demucs -i http://mirrors.tencentyun.com/pypi/simple --trusted-host mirrors.tencentyun.com
```

**验证安装**：

```bash
python -m demucs --help
```

如果命令能正常显示帮助信息，说明安装成功。

## 常见问题

### Q: 为什么不创建主项目自己的虚拟环境？

A: 因为主项目代码直接导入 `from indextts.infer_v2 import IndexTTS2`，需要在同一个 Python 环境中。使用子模块的虚拟环境可以：

- 避免依赖版本冲突
- 简化部署流程
- 确保 AI 模型库版本匹配

### Q: 为什么不使用 `uv add` 来安装主项目依赖？

A: `uv add` 需要 `pyproject.toml` 文件，会在主项目根目录创建新的虚拟环境（`.venv`），这与当前架构冲突：

- **当前架构**：主项目共享 `index-tts/.venv` 虚拟环境
- **使用 `uv add` 的问题**：会创建独立的 `.venv`，导致：
  - 主项目和 index-tts 使用不同的虚拟环境
  - 无法直接导入 `from indextts.infer_v2 import IndexTTS2`
  - 需要维护两个虚拟环境，增加复杂性

**推荐方式**：使用 `uv pip install -r requirements_project.txt`，它会：
- 自动使用 `index-tts/.venv` 虚拟环境（在 index-tts 目录下运行）
- 保持架构简单，只维护一个虚拟环境
- 与 `uv sync` 的管理方式一致（都是 uv 工具）

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

# 更新主项目额外依赖（推荐使用 uv）
cd index-tts
uv pip install --upgrade -r ../requirements_project.txt

# 或使用 pip（备选）
source .venv/bin/activate
pip install --upgrade -r ../requirements_project.txt
```

### Q: 如果遇到依赖冲突怎么办？

1. 使用依赖检查脚本：`python tools/check_dependencies.py`
2. 检查是否在正确的虚拟环境中：`which python` 应指向 `index-tts/.venv/bin/python`
3. 检查版本冲突：`pip check`
4. 如需要，可以创建隔离环境测试新版本

### Q: 如何检查依赖安装状态？

```bash
# 激活虚拟环境后运行检查脚本
cd index-tts
source .venv/bin/activate
cd ..
python tools/check_dependencies.py
```

脚本会自动检查：

- index-tts 核心依赖（torch, transformers, gradio 等）
- 主项目额外依赖（scipy, whisper, pyannote 等）
- 虚拟环境状态

### Q: 如何确认安装成功？

安装完成后，可以通过以下方式验证：

```bash
# 1. 检查系统依赖
ffmpeg -version  # 应显示版本信息

# 2. 检查环境变量（启动脚本会自动检查）
# 启动时会显示 DASHSCOPE_API_KEY 是否已设置

# 3. 检查依赖
cd index-tts
source .venv/bin/activate
cd ..
python tools/check_dependencies.py

# 4. 测试关键模块导入
python -c "import torch; import gradio; import whisper; import scipy; print('所有依赖已正确安装')"

# 5. 检查 Demucs（如果使用音频分离功能）
python -c "import demucs; print('demucs已安装')"

# 6. 启动 Web UI 测试
./run_webui.sh
```

如果 Web UI 能够正常启动并显示界面，说明安装成功。

## 开发建议

- **使用** `requirements_project.txt` 管理主项目额外依赖
- **保持** index-tts 依赖不变（除非子模块更新）
- **记录** 任何版本冲突和解决方案
- **不要** 直接修改 index-tts 的依赖文件
- **不要** 在主项目创建独立虚拟环境

## 故障排除

### 问题：uv 命令未找到

**解决方案**：

```bash
# 安装 uv
pip install uv

# 或者使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 问题：虚拟环境激活失败

**解决方案**：

```bash
# 确保已安装 index-tts 依赖
cd index-tts
uv sync --extra webui

# 检查虚拟环境是否存在
ls -la .venv/bin/activate

# 如果不存在，重新创建
uv sync --extra webui
```

### 问题：依赖安装失败

**解决方案**：

**推荐：使用 uv 安装（更快更可靠）**

```bash
cd index-tts
# 使用官方源
uv pip install -r ../requirements_project.txt

# 或使用国内镜像源（推荐国内用户）
uv pip install -r ../requirements_project.txt --index-url https://mirrors.aliyun.com/pypi/simple
```

**备选：使用 pip 安装**

```bash
# 确保已激活虚拟环境
source index-tts/.venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 使用国内镜像源（如果网络较慢）
pip install -r requirements_project.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题：FFmpeg 未安装导致音频处理失败

**错误信息**：`ffmpeg: command not found` 或音频提取/处理失败

**解决方案**：

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg

# 验证安装
ffmpeg -version
```

### 问题：翻译功能无法使用，提示未设置 DASHSCOPE_API_KEY

**错误信息**：`ERROR:src.text_translator:qwen3-max-2025-09-23翻译引擎初始化失败: 未设置DASHSCOPE_API_KEY环境变量`

**解决方案**：

1. 获取 API 密钥：访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)
2. 在 `~/.bashrc` 中添加：
   ```bash
   export DASHSCOPE_API_KEY='your-api-key-here'
   ```
3. 重新加载配置：`source ~/.bashrc`
4. 重启 Web UI

启动脚本会自动从 `~/.bashrc` 读取环境变量，启动时会显示是否已设置。

### 问题：Demucs 模块未找到

**错误信息**：`No module named 'demucs'` 或 `ModuleNotFoundError: No module named 'demucs'`

**解决方案**：

```bash
cd index-tts
source .venv/bin/activate
python -m pip install demucs -i http://mirrors.tencentyun.com/pypi/simple --trusted-host mirrors.tencentyun.com
```

**验证安装**：

```bash
python -m demucs --help
```

**注意**：虽然 demucs 在 index-tts 的依赖列表中，但实际可能需要单独安装。如果不需要音频分离功能，可以忽略此错误。

### 问题：GPU 加速不可用

**解决方案**：

1. 检查 CUDA 是否安装：`nvidia-smi`
2. 检查 PyTorch 是否支持 CUDA：`python -c "import torch; print(torch.cuda.is_available())"`
3. 如果返回 False，需要重新安装支持 CUDA 的 PyTorch
4. 或者在配置文件中设置 `device: "cpu"` 使用 CPU 模式

## 参考资源

- [README.md](README.md) - 项目主文档
- [开发指南](docs/DEVELOPER_GUIDE.md) - 技术实现细节和开发参考
- [IndexTTS2 文档](index-tts/README.md) - 子模块文档
