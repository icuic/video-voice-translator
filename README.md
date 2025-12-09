# AI音视频翻译系统

## 项目简介

Video Voice Translator 是一个基于人工智能技术的多语言音视频翻译系统，能够将视频或音频内容从一种语言翻译成另一种语言，并通过音色克隆技术保持原说话者的声音特征。

系统集成了语音识别、文本翻译、音色克隆、音频处理等多项技术，实现端到端的音视频翻译流程。支持中文与英文之间的双向翻译，适用于视频内容本地化、多语言教学、跨语言内容创作等场景。

## 演示视频

> 📹 **演示视频**：查看 [demo.mp4](data/demo/demo.mp4) 

<!-- 
注意：GitHub 的 Markdown 渲染器不支持 HTML 视频标签，但其他 Markdown 查看器（如 VS Code、Typora、GitLab 等）可能支持。
如果您在 GitHub 上查看，请直接点击上面的链接下载视频。
-->
<video width="800" controls>
  <source src="data/demo/demo.mp4" type="video/mp4">
  您的浏览器不支持视频标签。请直接下载：<a href="data/demo/demo.mp4">demo.mp4</a>
</video>

## 核心功能

### 视频与音频处理
- 支持多种视频格式（MP4、AVI、MOV、MKV等）和音频格式（WAV、MP3、M4A等）
- 自动提取视频中的音频轨道
- 音频格式标准化处理（16kHz、单声道、WAV格式）
- 元数据提取（时长、分辨率、采样率等）

### 智能音频分离
- 使用深度学习模型（Demucs）自动检测并分离人声和背景音乐
- 保留背景音乐轨道，用于最终视频合成
- 频谱分析评估音频复杂度，智能决定是否需要分离

### 高精度语音识别
- 支持两种后端：Faster-Whisper（默认，基于CTranslate2，速度更快）和原生Whisper（基于PyTorch）
- 自动后端选择：如果配置的后端不可用，会自动回退到另一个可用后端
- 支持自动语言检测
- 生成单词级别的时间戳
- 支持两种分段方法：
  - `punctuation`：基于标点符号的分段优化
  - `semantic`：基于标点符号的语义完整分段（默认）

### 文本翻译
- 支持中文与英文之间的双向翻译
- 使用大语言模型（默认：qwen3-max-2025-09-23）进行批量翻译
- 支持多种Qwen模型：qwen-flash、qwen-plus、qwen-max、qwen3-max-2025-09-23等
- 保持翻译结果的上下文连贯性
- 自动跳过相同语言的翻译任务
- 自适应重试策略，提高翻译成功率

### 音色克隆
- 基于 IndexTTS2 模型实现音色克隆
- 保持原说话者的声音特征、语速和情感
- 支持 GPU 加速和 FP16 精度优化
- 批量处理多个音频片段

### 多说话人处理（可选，当前效果有限）
- 说话人分离功能，识别并区分不同说话者
- 为每个说话人生成紧凑拼接音轨（去除静音）
- 构建全局时间与紧凑时间的映射关系
- 多说话人场景下的独立识别和翻译处理
- 支持时间戳映射回全局时间轴
- **注意**：当前说话人分离效果有限，建议使用 `--single-speaker` 选项跳过此步骤以获得更好的处理效果

### 系统特性
- Web UI 界面：基于 Gradio 的可视化操作界面
- 命令行工具：支持批处理和自动化脚本
- 模型预加载：启动时预加载模型，提升处理速度
- GPU 加速支持：关键模块支持 CUDA 加速
- 进度跟踪：实时显示处理进度和状态
- 日志记录：完整的处理日志和错误追踪

## 系统架构

### 核心技术栈

- **Whisper/Faster-Whisper**：语音识别引擎（支持两种后端）
- **Demucs**：音频分离模型
- **PyAnnote**：多说话人识别（说话人分离），使用 `pyannote/speaker-diarization-3.1` 模型
- **Qwen系列**：文本翻译大语言模型（默认qwen3-max-2025-09-23）
- **IndexTTS2**：音色克隆模型
- **FFmpeg**：音视频处理工具

### 处理流程

系统采用九步处理流程完成视频翻译：

1. **视频/音频处理**：提取音频轨道，格式标准化，提取元数据（时长、分辨率、采样率等）
2. **音频分离**：检测并分离人声和背景音乐
3. **多说话人处理（可选）**：识别不同说话者，生成紧凑音轨，构建时间映射关系
4. **语音识别**：使用Whisper/Faster-Whisper进行转录，生成时间戳和分段
5. **文本翻译**：批量翻译文本分段
6. **参考音频提取**：为每个翻译片段提取对应的参考音频（优先从说话人紧凑音轨裁剪）
7. **音色克隆**：为每个翻译片段生成保持原音色的语音
8. **音频合并**：根据时间戳同步合并音频片段
9. **视频合成**：将翻译后的音频与原始视频合成

详细流程说明请参考：[流程文档](docs/WORKFLOW.md)

### 支持的语言

- 中文（简体）
- 英文

## 项目结构

```
video_voice_translator/
├── src/                          # 源代码目录
│   ├── media_processor.py        # 媒体处理主类
│   ├── enhanced_media_processor.py # 增强媒体处理器（支持音频分离）
│   ├── audio_separator.py        # 音频分离器
│   ├── whisper_processor.py      # Whisper语音识别处理器
│   ├── text_translator.py        # 文本翻译器
│   ├── voice_cloner.py           # 音色克隆器
│   ├── timestamped_audio_merger.py # 时间同步音频合并器
│   ├── speaker_diarizer.py       # 说话人分离器
│   ├── model_preloader.py        # 模型预加载器
│   └── ...                       # 其他工具模块
├── index-tts/                    # IndexTTS2 音色克隆子模块
├── data/                         # 数据目录
│   ├── outputs/                  # 输出文件目录
│   ├── temp/                     # 临时文件目录
│   └── logs/                     # 日志文件目录
├── docs/                         # 文档目录
├── media_translation_webui.py    # Web UI 入口
├── media_translation_cli.py      # 命令行入口
├── install_all.sh                # 一键安装脚本（推荐）
├── run_webui.sh                  # Web UI 启动脚本
├── run_cli.sh                    # CLI 翻译启动脚本
├── scripts/                      # 脚本目录
│   ├── install/                  # 安装脚本
│   ├── batch_translate.sh        # 批量翻译脚本
│   └── preload_models.sh         # 模型预加载脚本
├── tools/                        # 工具脚本目录
│   └── check_dependencies.py     # 依赖检查脚本
├── requirements_project.txt      # 主项目额外依赖
├── config.yaml                   # 配置文件
└── README.md                     # 项目文档
```

## 快速开始

### 系统要求

- **系统内存（RAM）**：至少 8GB（推荐 16GB 或更多）
- **磁盘空间**：至少 30GB（用于模型文件约 5.5GB、虚拟环境约 9GB、依赖和缓存等）
- **GPU**：NVIDIA GPU，显存至少 8GB（推荐 RTX 3060/4060 或更高型号，CPU 模式运行会很慢）

详细系统要求和推荐配置请参考：[安装指南](docs/INSTALL.md)

### 安装

**推荐方式：一键安装**

使用一键安装脚本自动完成所有安装步骤（包括系统依赖、IndexTTS2、主项目依赖、模型下载等）：

```bash
./install_all.sh
```

**手动安装**

如果您希望手动控制安装过程，请参考：[安装指南](docs/INSTALL.md)

详细安装步骤请参考：[安装指南](docs/INSTALL.md)

### 环境变量配置

本项目需要使用阿里云 DashScope（Qwen）API 进行文本翻译，需要配置 API 密钥：

```bash
# Linux/macOS - 添加到 ~/.bashrc 或 ~/.zshrc
echo 'export DASHSCOPE_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**获取 API 密钥**：访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)

详细配置说明请参考：[安装指南](docs/INSTALL.md)

### 使用

**方式一：Gradio Web UI**（推荐新手）：

```bash
./run_webui.sh
```

启动后访问 `http://localhost:7861`

**方式二：前后端分离模式**：

```bash
./start.sh
```

- 前端界面：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

**方式三：命令行方式**：

```bash
# 自动检测语言并翻译
./run_cli.sh input.mp4

# 指定源语言和目标语言
./run_cli.sh input.mp4 --source-lang zh --target-lang en
```

详细使用方法请参考：[使用指南](docs/USAGE.md)

## 文档导航

### 用户文档
- **[安装指南](docs/INSTALL.md)** - 详细的安装和配置说明
- **[使用指南](docs/USAGE.md)** - 完整的使用方法和示例
- **[流程文档](docs/WORKFLOW.md)** - 完整的9步骤流程说明和设计要点

### 开发者文档
- **[贡献指南](docs/CONTRIBUTING.md)** - 如何参与项目贡献

### 其他
- **[IndexTTS2 官方文档](https://github.com/index-tts/index-tts)** - 音色克隆子模块官方文档

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！

详细的贡献指南请参考：[CONTRIBUTING.md](docs/CONTRIBUTING.md)
