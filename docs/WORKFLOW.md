# 音视频翻译系统 - 完整翻译流程总结

## 概述

本系统实现了一个**9步骤的完整音视频翻译流程**，支持将视频/音频从一种语言翻译成另一种语言，并使用音色克隆技术保持原说话者的声音特征。

**核心技术栈:**
- Whisper / Faster-Whisper (语音识别)
- Demucs (音频分离)
- PyAnnote (多说话人分离)
- Qwen系列 (文本翻译，默认qwen3-max-2025-09-23)
- IndexTTS2 (音色克隆)
- FFmpeg (音视频处理)

---

## 完整流程总览

```
原始视频/音频
    ↓
[步骤1] 音频提取
    ↓
[步骤2] 音频分离 (人声/背景音乐)
    ↓
[步骤3] 多说话人处理（可选）
    ↓
[步骤4] 语音识别 + 分段优化
    ↓
[步骤5] 文本翻译
    ↓
[步骤6] 参考音频提取
    ↓
[步骤7] 音色克隆
    ↓
[步骤8] 时间同步音频合并
    ↓
[步骤9] 视频合成
    ↓
最终翻译视频
```

---

## 详细步骤说明

### 📹 步骤1: 视频/音频处理

**模块**: `EnhancedMediaProcessor` (`src/enhanced_media_processor.py`)

**输入**:
- 视频文件: `mp4`, `avi`, `mov`, `mkv`
- 音频文件: `wav`, `mp3`, `m4a`

**处理内容**:
1. 检测文件类型和有效性
2. 如果是视频，提取音频轨道（使用FFmpeg）
3. 提取元数据：
   - 时长 (`duration`)
   - 分辨率 (`width`, `height`) - 仅视频
   - 帧率 (`fps`) - 仅视频
   - 采样率 (`sample_rate`)
4. 音频格式标准化：
   - 转换为 16kHz
   - 单声道 (mono)
   - WAV 格式

**输出文件**:
- `<文件名>_01_audio.wav` - 提取并标准化的音频文件

**生成位置**: 主任务目录
```
<任务目录>/
  └── <文件名>_01_audio.wav
```

---

### 🎵 步骤2: 音频分离 (人声/背景音乐)

**模块**: `AudioSeparator` (`src/audio_separator.py`)

**输入**:
- `<文件名>_01_audio.wav` (步骤1的输出)

**处理内容**:
1. 使用 Demucs htdemucs 模型分析音频特征
2. 检测是否包含背景音乐（基于频谱特征）
3. 如果有背景音乐，分离人声和伴奏：
   - 人声轨道（用于后续识别和翻译）
   - 背景音乐轨道（用于最终合成）
4. 评估分离质量

**输出文件**:
- `<文件名>_02_vocals.wav` - **人声轨道**（必需）
- `<文件名>_02_accompaniment.wav` - **背景音乐轨道**（可选，仅当检测到背景音乐时）

**生成位置**: 主任务目录
```
<任务目录>/
  ├── <文件名>_02_vocals.wav
  └── <文件名>_02_accompaniment.wav (可选)
```

---

### 🗣️ 步骤3: 多说话人处理（可选）

**模块**: `SpeakerTrackBuilder` (`src/pipeline/speaker_track_builder.py`)

**输入**:
- `<文件名>_02_vocals.wav` (人声轨道)

**处理内容**:
1. 使用说话人分离技术（PyAnnote）识别不同说话者
2. 为每个说话人生成紧凑音轨：
   - 去除静音段
   - 拼接所有该说话人的音频片段
3. 构建全局时间与紧凑时间的映射关系
4. 可选：对重叠区域使用TSE（目标说话人增强）进行优化

**重要说明**: 
- **此步骤只负责音频处理，不包含语音识别（ASR）**
- ASR处理统一在步骤4进行

**输出文件**:
- `speakers/<speaker_id>/<speaker_id>.wav` - 各说话人的紧凑音轨
- `speakers/<speaker_id>/<speaker_id>.json` - 时间映射表（全局时间 ↔ 紧凑时间）

**生成位置**: 主任务目录的子目录
```
<任务目录>/
  └── speakers/
      ├── SPEAKER_00/
      │   ├── SPEAKER_00.wav          (紧凑音轨)
      │   └── SPEAKER_00.json         (时间映射表)
      ├── SPEAKER_01/
      │   ├── SPEAKER_01.wav
      │   └── SPEAKER_01.json
      └── ...
```

**映射表格式** (`speakers/<speaker_id>/<speaker_id>.json`):
```json
[
  {
    "compact_start": 0.0,      // 紧凑时间轴的开始时间
    "compact_end": 5.2,        // 紧凑时间轴的结束时间
    "global_start": 12.5,      // 全局（原始）时间轴的开始时间
    "global_end": 17.7         // 全局（原始）时间轴的结束时间
  },
  ...
]
```

---

### 🎤 步骤4: 语音识别 + 分段优化（统一ASR处理）

**模块**: `WhisperProcessor` (`src/whisper_processor.py`)

#### 4.1 统一ASR处理

**输入**:
- **单说话人场景**: `<文件名>_02_vocals.wav` (人声轨道)
- **多说话人场景**: `speakers/<speaker_id>/<speaker_id>.wav` (说话人紧凑音轨，如果启用了步骤3)
- **多说话人场景（可选）**: `speakers/<speaker_id>/<speaker_id>.json` (时间映射表，用于将紧凑时间映射回全局时间)

**处理内容**:

**单说话人场景**:
- 直接对 `02_vocals.wav` 运行 Whisper/Faster-Whisper ASR
- 生成单词级别的时间戳 (word timestamps)
- 识别语言和文本内容

**多说话人场景**:
- 对每个说话人紧凑音轨分别运行 ASR
- **保存每个说话人的ASR结果**到 `speakers/<speaker_id>/` 目录（使用紧凑时间）
- 将紧凑时间映射回全局时间（使用步骤3生成的映射表）
- 合并所有说话人的 ASR 结果，按全局时间排序
- 每个 segment 包含 `speaker_id` 字段标识说话人

#### 4.2 分段优化

**输入**:
- 4.1 统一ASR处理的输出结果（Whisper原始分段、单词时间戳、转录文本）
  - 单说话人场景：来自 `02_vocals.wav` 的ASR结果
  - **多说话人场景**：已映射到全局时间并合并的所有说话人分段（使用全局时间戳）

**处理内容**:

**重要说明**：在多说话人场景下，分段优化在合并所有说话人分段**之后**进行，使用**全局时间戳**进行优化，确保分段时间戳不包含静音段。

两种分段策略（可配置）:

1. **基于标点符号** (`punctuation`): 根据句号、问号、感叹号等标点符号分段，结合单词时间戳计算每个句子的起止时间，智能合并过短的分段 (< 1.5秒)，拆分过长的分段 (> 15秒)
2. **语义分段** (`semantic`): 基于语义相似度的智能分段，结合多种优化策略
   - 自动检测时间连续性：如果单词间间隔 > 1.5秒，会自动拆分分段，避免包含静音段

**输出文件**:

#### 4.1 统一ASR处理生成的文件:

**主任务目录**（合并后的结果，全局时间）:
- `<文件名>_04_whisper_raw.json` - **Whisper 原始输出**（JSON格式，调试用）
- `<文件名>_04_whisper_raw_segments.txt` - **Whisper 原始分段文本**（可读格式，调试用）
- `<文件名>_04_whisper_raw_transcription.txt` - **完整转录文本**（从Whisper结果中提取）
- `<文件名>_04_whisper_raw_word_timestamps.txt` - **单词级时间戳**（从Whisper原始结果中提取，调试用）

**多说话人场景 - speakers目录**（各说话人的原始结果，紧凑时间）:
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw.json` - **说话人的Whisper原始输出**（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_segments.txt` - **说话人的Whisper原始分段文本**（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_transcription.txt` - **说话人的转录文本**（紧凑时间）
- `speakers/<speaker_id>/<speaker_id>_04_whisper_raw_word_timestamps.txt` - **说话人的单词级时间戳**（紧凑时间）

**注意**: 多说话人场景下，speakers目录中的文件使用**紧凑时间**，主任务目录中的文件使用**全局时间**。

#### 4.2 分段优化生成/更新的文件:
- `<文件名>_04_segments.txt` - **分段文本**（可读格式，带时间戳）
  - 如果启用分段优化：保存优化后的分段
  - 如果未启用分段优化：保存Whisper原始分段
- `<文件名>_04_segments.json` - **分段数据**（JSON格式，统一保存在主任务目录）
  - 如果启用分段优化：保存优化后的分段
  - 如果未启用分段优化：保存Whisper原始分段

**生成位置**: 主任务目录和speakers子目录

**单说话人场景**:
```
<任务目录>/
  ├── <文件名>_04_whisper_raw_transcription.txt
  ├── <文件名>_04_whisper_raw_word_timestamps.txt
  ├── <文件名>_04_segments.txt
  ├── <文件名>_04_segments.json
  ├── <文件名>_04_whisper_raw.json
  └── <文件名>_04_whisper_raw_segments.txt
```

**多说话人场景**:
```
<任务目录>/
  ├── <文件名>_04_segments.txt        (合并后的结果，全局时间)
  ├── <文件名>_04_segments.json       (合并后的结果，全局时间)
  └── speakers/
      ├── SPEAKER_00/
      │   ├── SPEAKER_00.wav                              (步骤3生成的紧凑音轨)
      │   ├── SPEAKER_00.json                             (步骤3生成的时间映射表)
      │   ├── SPEAKER_00_04_whisper_raw.json              (步骤4的ASR原始输出，紧凑时间)
      │   ├── SPEAKER_00_04_whisper_raw_segments.txt
      │   ├── SPEAKER_00_04_whisper_raw_transcription.txt
      │   └── SPEAKER_00_04_whisper_raw_word_timestamps.txt
      ├── SPEAKER_01/
      │   └── ...
      └── ...
```

**数据结构**（单说话人场景）:
```json
[
  {
    "start": 0.0,
    "end": 5.2,
    "text": "Hello, this is a test.",
    "words": [
      {"word": "Hello", "start": 0.0, "end": 0.5},
      {"word": "this", "start": 0.6, "end": 0.8},
      ...
    ]
  },
  ...
]
```

**数据结构**（多说话人场景，包含 `speaker_id`）:
```json
[
  {
    "start": 0.0,
    "end": 5.2,
    "text": "Hello, this is a test.",
    "speaker_id": "SPEAKER_00",
    "words": [
      {"word": "Hello", "start": 0.0, "end": 0.5},
      {"word": "this", "start": 0.6, "end": 0.8},
      ...
    ]
  },
  ...
]
```

**重要说明**:
- `04_segments.json` **始终保存在主任务目录**，无论是否启用步骤3
- 多说话人场景下，所有 segments 按全局时间排序，并包含 `speaker_id` 字段

---

### 🌐 步骤5: 文本翻译

**模块**: `TextTranslator` (`src/text_translator.py`)

**输入**:
- 步骤4的分段数据 (`04_segments.json`)，包含原文和时间戳

**处理内容**:
1. **智能跳过**: 如果源语言 = 目标语言，跳过翻译
2. **批量翻译**: 使用 Qwen 系列大模型批量翻译（默认qwen3-max-2025-09-23）
   - 每批最多 20 个分段（可配置）
   - 确保翻译结果数量与输入一致
   - 自动重试机制（自适应策略）
3. 为每个分段添加 `translated_text` 字段

**输出文件**:
- `<文件名>_05_translation.txt` - **翻译结果** (带时间戳，可读格式)
- `<文件名>_05_llm_interaction.txt` - **LLM 交互记录** (请求+响应，调试用)

**生成位置**: 主任务目录
```
<任务目录>/
  ├── <文件名>_05_translation.txt
  └── <文件名>_05_llm_interaction.txt
```

**优化特性**:
- 语言检测: 自动跳过相同语言翻译
- 批量处理: 提升翻译效率和上下文连贯性
- 错误恢复: 翻译失败时使用原文

**输出数据结构** (在内存中的 `translated_segments`):
```json
[
  {
    "start": 0.0,
    "end": 5.2,
    "text": "Hello, this is a test.",           // 原文
    "translated_text": "你好，这是一个测试。",     // 译文
    "speaker_id": "SPEAKER_00",                 // 多说话人场景
    "words": [...]
  },
  ...
]
```

---

### 📝 步骤6: 参考音频提取

**模块**: 在 `media_translation_cli.py` 中实现

**输入**:
- 翻译后的分段数据（带时间戳，来自步骤5）
- `<文件名>_02_vocals.wav` (人声轨道) 或
- `speakers/<speaker_id>.wav` (说话人紧凑音轨，优先使用)

**处理内容**:
1. 为每个翻译片段提取对应的参考音频
2. **多说话人场景**: 优先从说话人紧凑音轨裁剪
   - 根据全局时间到紧凑时间的映射关系精确提取
   - 使用步骤3生成的映射表进行时间转换
3. **单说话人场景**: 从完整人声轨道裁剪
4. 保存为独立的参考音频文件

**输出文件**:
- `ref_audio/<文件名>_06_ref_segment_000.wav` - 片段0的参考音频
- `ref_audio/<文件名>_06_ref_segment_001.wav` - 片段1的参考音频
- `ref_audio/<文件名>_06_ref_segment_002.wav` - 片段2的参考音频
- ...

**生成位置**: 主任务目录的 `ref_audio/` 子目录
```
<任务目录>/
  └── ref_audio/
      ├── <文件名>_06_ref_segment_000.wav
      ├── <文件名>_06_ref_segment_001.wav
      ├── <文件名>_06_ref_segment_002.wav
      └── ...
```

**重要说明**:
- 参考音频文件保存在**主任务目录**的 `ref_audio/` 子目录中
- **不会**在说话人子目录中创建 `ref_audio/` 目录
- 多说话人场景下，优先使用说话人紧凑音轨以获得更准确的参考音频

---

### 🎭 步骤7: 音色克隆（逐片段处理）

**模块**: `VoiceCloner` (`src/voice_cloner.py`)

**输入**:
- `ref_audio/<文件名>_06_ref_segment_*.wav` (参考音频片段，来自步骤6)
- 翻译后的文本分段（来自步骤5）

**处理内容**:
1. 使用 IndexTTS2 模型进行音色克隆
2. **并行处理**多个翻译片段（推荐方式）
3. 保持原说话者的音色、语速、情感特征
4. 使用 FP16 精度 + CUDA 加速（如果可用）

**输出文件**:
- `cloned_audio/<文件名>_07_segment_000.wav` - 片段0的克隆音频
- `cloned_audio/<文件名>_07_segment_001.wav` - 片段1的克隆音频
- `cloned_audio/<文件名>_07_segment_002.wav` - 片段2的克隆音频
- ...

**生成位置**: 主任务目录的 `cloned_audio/` 子目录
```
<任务目录>/
  └── cloned_audio/
      ├── <文件名>_07_segment_000.wav
      ├── <文件名>_07_segment_001.wav
      ├── <文件名>_07_segment_002.wav
      └── ...
```

**关键技术**:
- IndexTTS2 模型（音色克隆）
- FP16 精度 + CUDA 加速
- 单例模式（避免重复加载模型）
- 并行处理（提升处理速度）

**重要说明**:
- 克隆音频文件保存在**主任务目录**的 `cloned_audio/` 子目录中
- **不会**在说话人子目录中创建 `cloned_audio/` 目录

---

### 🔊 步骤8: 时间同步音频合并

**模块**: `TimestampedAudioMerger` (`src/timestamped_audio_merger.py`)

**输入**:
- 所有片段的克隆音频 (`cloned_audio/<文件名>_07_segment_*.wav`)
- 每个片段的时间戳信息 (`start`, `end`，来自步骤4和5)
- 原始音频总时长

**处理内容**:
1. 创建静音轨道（与原视频同长）
2. 根据时间戳将每个片段插入到正确位置
3. **时长调整**: 如果克隆音频过长，使用 FFmpeg 倍速压缩
   - 最大倍速限制: 2.0 倍
   - 保持语音自然度
4. **重叠处理**: 检测并修复时间重叠问题
5. **背景音乐合成**: 如果存在背景音乐，混合到最终音频

**输出文件**:
- `<文件名>_08_final_voice.wav` - **完整的翻译配音轨道**（与原视频同长）

**生成位置**: 主任务目录
```
<任务目录>/
  └── <文件名>_08_final_voice.wav
```

**核心算法**:
- librosa 音频处理
- 音量匹配算法
- 时长控制（倍速/裁剪）
- 背景音乐混合

---

### 🎬 步骤9: 视频合成

**模块**: FFmpeg 命令行工具（在 `media_translation_cli.py` 中调用）

**输入**:
- 原始视频文件
- `<文件名>_08_final_voice.wav` (翻译配音)
- `<文件名>_02_accompaniment.wav` (背景音乐，可选)

**处理内容**:

**情况A: 有背景音乐**
```bash
ffmpeg -i 原视频 -i 中文配音 -i 背景音乐 \
  -c:v copy \  # 视频轨道直接复制
  -filter_complex '[1:a][2:a]amix=inputs=2' \  # 混合配音和背景音乐
  -map 0:v:0 -map [aout] \
  输出视频.mp4
```

**情况B: 无背景音乐**
```bash
ffmpeg -i 原视频 -i 中文配音 \
  -c:v copy \  # 视频轨道直接复制
  -c:a aac \   # 音频编码
  -map 0:v:0 -map 1:a:0 \
  输出视频.mp4
```

**输出文件**:
- `<文件名>_09_translated.mp4` - **最终翻译视频**

**生成位置**: 主任务目录
```
<任务目录>/
  └── <文件名>_09_translated.mp4
```

**关键特性**:
- 视频轨道直接复制（保持原视频质量）
- 音频混合（配音 + 背景音乐）
- 支持多种视频格式

---

## 输出文件汇总

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


