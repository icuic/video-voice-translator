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
./install.sh
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

### 五、环境变量配置（.env 文件）

本项目的所有用户配置（API 密钥 / 镜像源 / HuggingFace 镜像）统一存放在项目根目录的 **`.env` 文件** 中，**不再写入 `~/.bashrc` 或 `~/.zshrc`**。安装脚本和运行时都会自动加载它。

> 编辑 `.env` 后立即生效，无需重新登录 shell。
> 对正在运行的服务：执行 `./manage-supervisor.sh restart` 即可重新加载配置。

#### `.env` 文件生成

```bash
cd /path/to/video-voice-translator
cp .env.example .env
```

#### 必填项

| 变量 | 说明 | 示例 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key，文本翻译必需（Qwen 系列模型） | `sk-xxxxxxxxxxxxxxxx` |

获取地址：<https://dashscope.console.aliyun.com/apiKey>

#### 腾讯云 ECS 部署推荐（必看）

腾讯云同地域 ECS 可以直接使用内网镜像，**不走公网流量，速度最快**。将 `.env` 中设置为：

```
MIRROR_MODE=tencent-intranet
```

#### 完整镜像模式可选值（.env 中 `MIRROR_MODE`，或 CLI `--mirror`）

| 值 | 场景 | 说明 |
|----|------|------|
| `tencent-intranet` | ✨ **腾讯云 ECS 同地域部署** | PyPI：`mirrors.tencentyun.com`（内网，免流）；NPM：腾讯公云 npm 镜像；HF：`hf-mirror.com` |
| `tencent` | 腾讯云公网（或其他使用腾讯云镜像的机器） | PyPI：`mirrors.cloud.tencent.com/pypi`；NPM：腾讯 npm；HF：`hf-mirror.com` |
| `china` | 国内通用（阿里云 + 清华 Nodesource） | PyPI：阿里云；NPM：npmmirror；HF：`hf-mirror.com` |
| `official` | 海外服务器 / 本地开发机可直连国际网 | 全部走 PyPI / NPM / HF / NodeSource 官方 |
| `auto` | **默认** | 脚本分别探测 4 组源的综合平均延迟，选择综合最快的 |

#### 可选高级覆盖（一般不用填）

| 变量 | 作用 |
|------|------|
| `UV_DEFAULT_INDEX` | 强制指定 PyPI 源，会覆盖 `MIRROR_MODE` 的预设 |
| `NPM_REGISTRY` | 强制指定 NPM registry |
| `NODE_SETUP_URL` | 强制指定 Node.js setup_20.x 脚本下载地址 |
| `HF_ENDPOINT` | 强制指定 HuggingFace 镜像 |
| `UV_HTTP_TIMEOUT` | 下载超时（秒），默认 120 |

## 下一步

安装完成后，您可以：

- **使用前后端分离服务模式（推荐）**（基于 supervisord，崩溃自动重启）：
  ```bash
  ./manage-supervisor.sh start   # 启动所有服务
  ./manage-supervisor.sh status  # 查看服务状态
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
