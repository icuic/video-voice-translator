# 贡献指南

感谢您对 Video Voice Translator 项目的关注！我们欢迎所有形式的贡献。

## 如何贡献

### 报告问题

如果您发现了 bug 或有功能建议，请通过以下方式提交：

1. **检查现有问题**：在提交新问题之前，请先查看项目的 Issues 列表，确认问题尚未被报告。

2. **创建 Issue**：
   - Bug 报告：请提供详细的错误描述、复现步骤、环境信息（Python 版本、操作系统等）
   - 功能建议：请描述功能需求和使用场景

3. **Issue 模板**：请使用相应的 Issue 模板，以便我们更好地理解和处理问题。

### 提交代码

#### 开发流程

1. **Fork 项目**：在 GitHub 上 Fork 本项目到您的账户

2. **克隆仓库**：
   ```bash
   git clone https://github.com/YOUR_USERNAME/video_voice_translator.git
   cd video_voice_translator
   ```
   注意：将 `YOUR_USERNAME` 替换为您的 GitHub 用户名

3. **创建分支**：
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

4. **设置开发环境**：
   ```bash
   # 安装 index-tts 依赖
   cd index-tts
   uv sync --extra webui
   
   # 激活虚拟环境并安装主项目依赖
   source .venv/bin/activate
   cd ..
   pip install -r requirements_project.txt
   ```

5. **进行修改**：
   - 编写清晰的代码
   - 添加必要的注释和文档字符串
   - 遵循项目的代码风格（见下方"代码规范"部分）

6. **测试**：
   - 确保您的修改不会破坏现有功能
   - 如果可能，添加新的测试用例
   - 运行依赖检查：`python tools/check_dependencies.py`

7. **提交更改**：
   ```bash
   git add .
   git commit -m "描述您的更改"
   ```

8. **推送并创建 Pull Request**：
   ```bash
   git push origin feature/your-feature-name
   ```
   然后在 GitHub 上创建 Pull Request。

#### Pull Request 指南

- **标题**：清晰描述 PR 的内容
- **描述**：详细说明更改的原因、内容和影响
- **关联 Issue**：如果修复了某个 Issue，请在描述中使用 `Fixes #issue-number` 或 `Closes #issue-number`
- **测试**：说明您如何测试了这些更改
- **检查清单**：
  - [ ] 代码遵循项目规范
  - [ ] 已添加必要的注释和文档
  - [ ] 已测试功能正常工作
  - [ ] 已更新相关文档（如 README、docs/USAGE.md 等）

### 代码规范

#### Python 代码风格

- 遵循 PEP 8 代码风格指南
- 使用 4 个空格缩进（不使用 Tab）
- 行长度限制为 120 字符
- 使用有意义的变量和函数名
- 添加适当的类型提示（如可能）

#### 文档字符串

- 为所有公共函数和类添加文档字符串
- 使用 Google 风格的文档字符串格式：

```python
def process_audio(audio_path: str, output_dir: str) -> str:
    """处理音频文件。
    
    Args:
        audio_path: 输入音频文件路径
        output_dir: 输出目录路径
        
    Returns:
        处理后的音频文件路径
        
    Raises:
        FileNotFoundError: 如果输入文件不存在
    """
    pass
```

#### 提交信息规范

提交信息应清晰描述更改内容：

- **格式**：`<类型>: <简短描述>`
- **类型**：
  - `feat`: 新功能
  - `fix`: Bug 修复
  - `docs`: 文档更新
  - `style`: 代码格式调整（不影响功能）
  - `refactor`: 代码重构
  - `test`: 测试相关
  - `chore`: 构建/工具链相关

**示例**：
```
feat: 添加批量处理功能
fix: 修复音频分离时的内存泄漏问题
docs: 更新安装指南
```

### 开发建议

1. **保持代码简洁**：编写清晰、可读的代码
2. **添加注释**：为复杂逻辑添加注释说明
3. **错误处理**：添加适当的错误处理和日志记录
4. **性能考虑**：注意代码性能，特别是处理大文件时
5. **向后兼容**：尽量保持 API 的向后兼容性

### 项目结构

了解项目结构有助于更好地贡献。详细项目结构请参考：[README.md - 项目结构](../README.md#项目结构)

### 获取帮助

如果您在贡献过程中遇到问题：

1. 查看项目文档（README.md、docs/INSTALL.md、docs/USAGE.md）
2. 搜索现有的 Issues 和 Pull Requests
3. 创建新的 Issue 描述您的问题（请使用 Issue 模板）

### 行为准则

- 尊重所有贡献者
- 建设性的反馈和讨论
- 专注于改进项目
- 保持专业和友善

## 感谢

再次感谢您对项目的贡献！每一个贡献，无论大小，都让这个项目变得更好。

