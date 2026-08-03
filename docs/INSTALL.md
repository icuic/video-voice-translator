# 安装与配置指南

## 系统要求

- **系统内存（RAM）**：至少 8GB（推荐 16GB 或更多）
- **磁盘空间**：至少 30GB（用于模型文件约 5.5GB、虚拟环境约 9GB、依赖和缓存等）
- **GPU**：推荐 8GB 及以上显存的独立 GPU；本分支优先支持 AMD Radeon/ROCm，NVIDIA CUDA 仍可运行，CPU 模式会明显变慢

## 推荐配置

以下配置已通过测试，可流畅运行本项目：

- **系统内存（RAM）**：38GB
- **磁盘空间**：128GB
- **GPU**：8GB 以上显存的 AMD Radeon / AMD Instinct / NVIDIA GPU
- **CPU**：10 核
- **Python**：3.10.11

## AMD / ROCm 说明

- 本分支默认将 `config.yaml` 中的 `whisper.backend` 设为 `whisper`，以便优先复用 PyTorch 的 ROCm 能力
- 如果在 AMD/ROCm 环境中运行，`IndexTTS2` 的 CUDA kernel 会默认关闭，避免误用 NVIDIA 专用优化
- ROCm 下 PyTorch 仍通过 `torch.cuda` 命名空间暴露 GPU，因此日志中看到 `cuda` 设备字符串是正常现象

## 一键安装（推荐）

强烈推荐使用以下脚本，一键完成所有安装步骤：

```bash
./install_all.sh
```

**一键安装脚本会自动处理：**
- ✅ 安装系统依赖（FFmpeg、lsof、Node.js）
- ✅ 安装 IndexTTS2
- ✅ 安装主项目依赖
- ✅ 安装前端依赖
- ✅ 验证安装（包括依赖、IndexTTS2、模型文件）
- ✅ 配置环境变量（DASHSCOPE_API_KEY）

**注意**：
- 模型文件较大（约 5.5GB），下载可能需要一些时间
- 脚本会优先使用 ModelScope（国内用户），如果失败会尝试 HuggingFace
- 安装完成后会提示配置 DASHSCOPE_API_KEY（翻译功能需要）

---

**以下内容为手动安装步骤，如果您已使用一键安装，可以跳过。**

## 手动安装

### 一、系统依赖安装

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

### Node.js 安装（必需）

Node.js 是系统必需依赖，一键安装脚本会自动安装。如果需要手动安装：

**Ubuntu/Debian**：

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs
```

**验证安装**：

```bash
node --version
npm --version
```

如果命令能正常显示版本信息，说明安装成功。

### 二、安装 IndexTTS2

本项目依赖 IndexTTS2 进行音色克隆功能。在安装主项目依赖之前，必须先完成 IndexTTS2 的安装。

**安装 IndexTTS2**：提供两种安装方式，选择其中一种即可。

#### 方式一（推荐）：使用项目提供的便捷脚本

```bash
./scripts/install/install_index_tts.sh
```

**脚本会自动处理：**
- ✅ 检查并安装 uv（如果未安装）
- ✅ 克隆 IndexTTS2 仓库（如果不存在）
- ✅ 安装 IndexTTS2 依赖（使用国内镜像源）
- ✅ 验证安装
- ✅ 下载模型文件（必需，约 5.5GB）

**重要提示：**
- 脚本会自动使用国内镜像源（适合国内用户）
- 模型文件会自动下载，下载完成后音色克隆功能即可正常使用
- 如果下载失败，请参考 [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) 手动下载

#### 方式二：按照官方文档手动安装

如果您希望手动控制安装过程，可以按照官方文档进行安装：

- **官方文档链接**：https://github.com/index-tts/index-tts

请参考 [IndexTTS2 官方 README.md](https://github.com/index-tts/index-tts) 中的完整安装说明。

**验证 IndexTTS2 安装**：
```bash
# 在项目根目录执行以下命令验证安装
cd index-tts
source .venv/bin/activate
python -c "from indextts.infer_v2 import IndexTTS2; print('IndexTTS2 安装成功')"
cd ..
```

### 三、安装主项目依赖

**说明**：完成 IndexTTS2 安装后，需要安装主项目的额外依赖。主项目的依赖文件是 `requirements_project.txt`，包含 IndexTTS2 中没有的依赖。

```bash
# 使用国内镜像源（推荐国内用户）
./scripts/install/install_with_uv_china.sh

# 或使用官方源
./scripts/install/install_with_uv.sh
```

**验证安装**：

```bash
python tools/check_dependencies.py
```

### 四、安装前端依赖（必需）

前端依赖是系统必需依赖，一键安装脚本会自动安装。如果需要手动安装：

```bash
cd frontend
npm install
cd ..
```

### 五、环境变量配置

### 翻译 LLM 配置（必需）

推荐把翻译模型配置放在项目根目录的 `.env` 中。该文件默认不会被 git 跟踪。

示例：

```dotenv
LLM_BASE_URL=https://developer.amd.com.cn/radeon/api/v1
LLM_MODEL=DeepSeek-V4-Flash
LLM_API_KEY=your-api-key-here
LLM_TIMEOUT=300.0
```

如果你不想把 key 直接写进 `.env`，也可以这样：

```dotenv
LLM_BASE_URL=https://developer.amd.com.cn/radeon/api/v1
LLM_MODEL=DeepSeek-V4-Flash
LLM_API_KEY_ENV=RADEON_API_KEY
```

然后在 shell 环境中设置：

```bash
export RADEON_API_KEY='your-api-key-here'
```

## 下一步

安装完成后，您可以：

- **使用 Gradio Web UI**（推荐新手）：
  ```bash
  ./run_webui.sh
  ```
  访问 `http://localhost:7861`

- **使用前后端分离模式**（需要 Node.js 和前端依赖）：
  ```bash
  ./service.sh up
  ```
  前端：`http://localhost:5173`，后端 API：`http://localhost:8000`

- **使用命令行方式**：
  ```bash
  ./run_cli.sh input.mp4
  ```

- 查看 [使用指南](USAGE.md) 了解如何使用系统
- 查看 [流程文档](WORKFLOW.md) 了解系统工作原理

## 参考资源

- [README.md](../README.md) - 项目主文档
- [使用指南](USAGE.md) - 完整的使用方法和示例
- [流程文档](WORKFLOW.md) - 完整的9步骤流程说明
- [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) - 音色克隆子模块官方文档
