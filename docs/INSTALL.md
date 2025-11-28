# 安装与配置指南

## 系统要求

- **系统内存（RAM）**：至少 8GB（推荐 16GB 或更多）
- **磁盘空间**：至少 30GB（用于模型文件约 5.5GB、虚拟环境约 9GB、依赖和缓存等）
- **GPU**：NVIDIA GPU，显存至少 8GB（推荐 RTX 3060/4060 或更高型号，CPU 模式运行会很慢）

## 推荐配置

以下配置已通过测试，可流畅运行本项目：

- **系统内存（RAM）**：38GB
- **磁盘空间**：128GB
- **GPU**：NVIDIA Tesla V100-SXM2-32GB（32GB 显存）
- **CPU**：10 核
- **Python**：3.10.11

## 一键安装（推荐）

强烈推荐使用以下脚本，一键完成所有安装步骤：

```bash
./install_all.sh
```

**一键安装脚本会自动处理：**
- ✅ 安装系统依赖（FFmpeg、lsof）
- ✅ 安装 IndexTTS2
- ✅ 安装主项目依赖
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

### 四、环境变量配置

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

## 下一步

安装完成后，您可以：

- 查看 [使用指南](USAGE.md) 了解如何使用系统
- 查看 [流程文档](WORKFLOW.md) 了解系统工作原理

## 参考资源

- [README.md](../README.md) - 项目主文档
- [使用指南](USAGE.md) - 完整的使用方法和示例
- [流程文档](WORKFLOW.md) - 完整的9步骤流程说明
- [IndexTTS2 官方文档](https://github.com/index-tts/index-tts) - 音色克隆子模块官方文档
