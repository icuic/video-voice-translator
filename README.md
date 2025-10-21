# 视频处理模块

多语言视频翻译工具的核心组件，负责处理视频和音频文件，提取元数据和音频内容。

## 功能特性

- 🎥 **多格式支持**: 支持 MP4, AVI, MOV, MKV, MP3, WAV 等常见格式
- 📊 **元数据提取**: 自动提取视频/音频的详细信息（时长、分辨率、采样率等）
- 🎵 **音频提取**: 从视频文件中提取高质量音频
- 🔧 **格式转换**: 音频格式标准化处理
- 📝 **批量处理**: 支持批量处理多个文件
- ⚡ **高性能**: 基于FFmpeg的高效处理

## 项目结构

```
voice_clone_lingua_shift/
├── src/                          # 源代码目录
│   ├── __init__.py
│   ├── video_processor.py        # 视频处理主类
│   ├── metadata_extractor.py     # 元数据提取器
│   ├── audio_extractor.py        # 音频提取器
│   └── utils.py                  # 工具函数
├── tests/                        # 测试目录
│   ├── __init__.py
│   └── test_video_processor.py   # 测试文件
├── examples/                     # 示例目录
│   └── sample_videos/            # 测试视频目录
├── output/                       # 输出目录
├── requirements.txt              # 项目依赖
├── config.yaml                   # 配置文件
├── example_usage.py              # 使用示例
└── README.md                     # 项目文档
```

## 安装依赖

```bash
# 安装Python依赖
pip install -r requirements.txt

# 确保系统已安装FFmpeg
# Ubuntu/Debian:
sudo apt update
sudo apt install ffmpeg

# CentOS/RHEL:
sudo yum install ffmpeg
```

## 快速开始

### 1. 基本使用

```python
from src.video_processor import VideoProcessor

# 初始化处理器
processor = VideoProcessor()

# 处理单个文件
result = processor.process("input_video.mp4")

if result["success"]:
    print(f"处理成功! 音频文件: {result['audio_path']}")
    print(f"视频时长: {result['processing_info']['duration']} 秒")
else:
    print(f"处理失败: {result['error']}")
```

### 2. 批量处理

```python
# 批量处理多个文件
files = ["video1.mp4", "video2.avi", "audio1.wav"]
results = processor.batch_process(files)

print(f"成功处理: {results['successful']}/{results['total']} 个文件")
```

### 3. 文件验证

```python
# 验证文件是否可处理
validation = processor.validate_input("test_video.mp4")

if validation["valid"]:
    print("文件可以处理")
    if validation["warnings"]:
        print(f"警告: {validation['warnings']}")
else:
    print(f"文件验证失败: {validation['errors']}")
```

## 配置说明

编辑 `config.yaml` 文件来自定义处理参数:

```yaml
# 音频处理配置
audio:
  sample_rate: 16000  # 采样率 (Hz)
  format: "wav"       # 输出格式
  channels: 1         # 声道数
  bit_depth: 16       # 位深度

# 视频处理配置
video:
  supported_formats: ["mp4", "avi", "mov", "mkv", "mp3", "wav"]
  temp_dir: "./temp"

# 默认设置
defaults:
  language: "en"      # 默认语言
  output_dir: "./output"
```

## 运行示例

```bash
# 运行使用示例
python example_usage.py

# 运行测试
python -m pytest tests/ -v
```

## API 参考

### VideoProcessor 类

主要的视频处理类，提供统一的处理接口。

#### 方法

- `process(input_path, output_dir=None, language=None)`: 处理单个文件
- `batch_process(input_paths, output_dir=None, language=None)`: 批量处理文件
- `validate_input(input_path)`: 验证输入文件
- `get_supported_formats()`: 获取支持的文件格式
- `get_processing_info(input_path)`: 获取文件处理信息

### MetadataExtractor 类

元数据提取器，用于获取视频/音频文件的详细信息。

#### 方法

- `extract(file_path)`: 提取文件元数据

### AudioExtractor 类

音频提取器，负责从视频中提取音频或转换音频格式。

#### 方法

- `extract(input_path, output_path)`: 提取音频
- `extract_with_progress(input_path, output_path, progress_callback)`: 带进度回调的提取

## 处理流程

1. **输入验证**: 检查文件存在性和格式支持
2. **元数据提取**: 获取视频/音频的详细信息
3. **音频提取**: 从视频中提取音频或转换音频格式
4. **结果输出**: 生成处理报告和输出文件

## 输出格式

处理结果包含以下信息:

```python
{
    "success": True,
    "input_path": "input_video.mp4",
    "output_dir": "./output",
    "audio_path": "./output/input_video_audio.wav",
    "metadata": {
        "file_info": {...},
        "video": {...},
        "audio": {...},
        "format": {...}
    },
    "audio_result": {...},
    "language": "en",
    "processing_info": {
        "input_size": 1024000,
        "output_size": 512000,
        "duration": 30.5,
        "format": "mp4"
    }
}
```

## 错误处理

模块包含完善的错误处理机制:

- 文件不存在检查
- 格式支持验证
- FFmpeg错误处理
- 内存和磁盘空间检查

## 性能优化

- 使用FFmpeg进行高效的音视频处理
- 支持大文件的分段处理
- 智能缓存机制
- 并行处理支持

## 测试

运行测试套件:

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_video_processor.py::TestVideoProcessor -v
```

## 注意事项

1. **测试文件**: 需要手动添加测试视频到 `examples/sample_videos/` 目录
2. **FFmpeg依赖**: 确保系统已正确安装FFmpeg
3. **文件权限**: 确保对输入和输出目录有读写权限
4. **内存使用**: 处理大文件时注意内存使用情况

## 后续扩展

- [ ] 语言自动检测功能
- [ ] 更多音频格式支持
- [ ] 视频质量分析
- [ ] 处理进度显示
- [ ] Web界面集成

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目。



