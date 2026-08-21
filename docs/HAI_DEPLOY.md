# 腾讯云 HAI 一键部署指南

本项目采用「**HAI 基础镜像 + 一行部署脚本**」方式，无需等待自定义镜像审核，**购买后 SSH 登录 → 粘贴一行命令 → 全自动安装 → 打开浏览器用**。

> 为什么不是「自定义应用镜像」：腾讯云 HAI 目前暂不支持跨账号共享自定义应用镜像（镜像仅限作者账号下使用）。因此选用最通用的脚本化方式，任何用户从作者推广链接购买 HAI 后都能一键安装，且安装源始终是 GitHub 上的最新版本。

---

## 一、购买 HAI 实例

### 推荐配置

**HAI-GPU 进阶型（V100 32GB）**，专为音视频翻译优化：

| 配置项 | 规格 |
|--------|------|
| GPU | NVIDIA Tesla V100-SXM2-32GB（32GB 显存） |
| CPU | 10 核 |
| 内存 | 38GB |
| 系统盘 | 128GB |
| 价格 | **¥49 / 7天**（新人限 1 件，0.8 折，原价 ¥604.8） |

> 💡 上述配置已通过完整测试，Whisper 语音识别 + IndexTTS2 音色克隆均可流畅运行。

### 购买入口（作者推广链接，同价支持项目维护）

👉 **[点击进入腾讯云购买页面](https://curl.qcloud.com/9j4S4Hug)**

### 购买流程

1. 点击上方链接进入腾讯云 GPU 算力活动页
2. 选择 **「高性能应用服务 HAI」** Tab（页面上方第二个蓝色卡片）
3. 选择 **「HAI-GPU进阶型 限1个」**（¥49 / 7天）卡片
4. 在「**应用名称**」下拉框中选择 **「PyTorch 2.x / 3.x」** 或 **「基础镜像」**（即官方提供的通用 PyTorch 基础镜像，已自带 GPU 驱动、CUDA、conda 等，无需额外配置）
5. 选择算力方案（默认 GPU-32GB 显存即可）和时长（7 天）
6. 点击「立即购买」并完成支付

> ⚠️ **注意**：应用名称不需要选「AI 音视频翻译系统」（因为没有上架镜像），选官方的 PyTorch 基础镜像就好，下一步的一行命令会自动完成项目安装。

---

## 二、等待实例启动

支付完成后，前往 [腾讯云 HAI 控制台](https://console.cloud.tencent.com/hai) 查看实例状态：

- 状态显示为「创建中」→ 通常需要 2~3 分钟
- 状态变为「运行中」→ 实例准备完毕

**记录实例的公网 IP**（形如 `1.2.3.4`），下一步需要用到。

---

## 三、执行部署脚本（一行命令）

### 3.1 SSH 登录实例

使用 HAI 控制台设置的密码或 SSH 密钥登录：

```bash
ssh ubuntu@<你的实例公网IP>
```

> 用户名通常为 `ubuntu`，如果失败可以尝试 `root`。

### 3.2 粘贴一行命令

登录成功后，直接在终端粘贴下面的命令并回车：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
```

**国内加速备用（如果 GitHub 下载慢，用这个）：**

```bash
bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
```

### 3.3 部署脚本自动完成以下工作

你只需等待，不需要任何交互：

| 步骤 | 说明 | 耗时 |
|------|------|------|
| 1. 系统依赖检查 | git / curl / ffmpeg / python3 / supervisor | < 30s |
| 2. 拉取代码仓库 | 从 GitHub 拉项目到 `~/video-voice-translator` | < 10s |
| 3. 预置 `.env` 模板 | 从 `.env.example` 复制，已预填 MIRROR_MODE=内网源 | < 1s |
| 4. **主安装** | 创建虚拟环境 / 下载 Whisper + TTS 模型 / 前端 npm install / 启动 supervisord | **10~20 分钟** |
| 5. MOTD 横幅 | 追加 SSH 登录欢迎语，下次登录自动显示 | < 5s |

部署完成后终端会打印出你的访问地址（自动从元数据拿公网 IP 填充）：

```
┌──────────────────────────────────────────────────────────┐
│ 🌐 访问地址（默认端口，首次访问自动跳转配置页）           │
│    前端翻译界面：  http://1.2.3.4:8080                   │
│    后端 API 文档： http://1.2.3.4:8000/docs              │
└──────────────────────────────────────────────────────────┘
```

> 💡 **8080 vs 5173？** 生产环境通过 supervisord 跑的前端是构建后的静态资源，监听 **8080**（由 nginx-like 脚本或 vite preview 提供，具体以你的项目 supervise 配置为准）。如果实际配置监听 5173，终端也会给出相应端口。

---

## 四、配置 LLM 翻译密钥（二选一）

本项目使用 OpenAI 兼容协议进行文本翻译，任何符合 `/v1/chat/completions` 协议的 LLM 服务都可以使用。

**首次使用必须完成此步，否则翻译功能不可用。**

### 方式一（推荐）：Web UI 引导页配置

浏览器访问实例的 Web 界面地址：

```
http://<实例公网IP>:8080
```

首次访问会**自动跳转**到初始化配置页 `/setup`，按提示填写三项必填信息：

| 字段 | 说明 |
|------|------|
| **API Base URL** | OpenAI 兼容接口地址（以 `/v1` 结尾，如供应商未特别说明通常都有） |
| **API Key** | 对应供应商的 API Key（本地无鉴权服务填 `EMPTY`） |
| **模型名** | 按对应供应商文档填写 |

「高级选项」默认折叠（温度、超时、立即重启），初学者不用展开，点「保存并启动」即可。保存成功后 2~3 秒自动跳转主页。

### 方式二：SSH 交互式脚本配置

回到 SSH 终端执行：

```bash
cd ~/video-voice-translator
./configure.sh
```

按提示依次填写 API Base URL → API Key → 模型名，脚本会给出最终配置摘要（API Key 自动脱敏显示为 `sk-****xxxx`），确认 `[Y/n]` 后：

- 自动 **原子写入 `.env`**（防止半写入损坏配置）
- 保留 **镜像源**（MIRROR_MODE / HF_ENDPOINT / USE_MODELSCOPE）不被覆盖
- 可选 **立即重启服务**（默认 yes）

配置完成后访问 `http://<实例公网IP>:8080` 即可使用。

---

## 五、开始使用

访问 `http://<实例公网IP>:8080`，进入 Web UI：

1. **上传文件**：拖拽或点击上传视频（MP4/AVI/MOV/MKV 等）或音频（WAV/MP3/M4A 等）
2. **选择源语言 / 目标语言**（支持中英文双向翻译）
3. 点击「开始翻译」，进度条实时显示 9 步处理流程
4. 翻译完成后，在分段列表中可编辑翻译文本、重新翻译单个片段、重新合成语音
5. 点击「重新生成最终视频」合并所有修改，下载翻译后的视频

### 其他访问地址

| 服务 | 地址 |
|------|------|
| 前端 Web UI | `http://<实例公网IP>:8080` |
| 后端 API 文档（Swagger） | `http://<实例公网IP>:8000/docs` |
| 后端健康检查 | `http://<实例公网IP>:8000/health` |
| 配置页（随时可重进） | `http://<实例公网IP>:8080/setup` |

---

## 六、服务管理命令

所有服务通过 `supervisord` 管理，进程崩溃会自动重启。在项目根目录执行：

```bash
./manage-supervisor.sh start      # 启动全部服务（后端 + 前端）
./manage-supervisor.sh stop       # 停止全部服务并退出 supervisord
./manage-supervisor.sh restart    # 重启全部服务（修改 .env 后需要此步）
./manage-supervisor.sh status     # 查看各进程状态
./manage-supervisor.sh tail all   # 实时查看服务日志
./manage-supervisor.sh help       # 查看完整命令列表
```

### 命令行批处理翻译

除了 Web UI，也支持命令行批处理：

```bash
./run_cli.sh input.mp4                              # 自动检测语言
./run_cli.sh input.mp4 --source-lang zh --target-lang en  # 指定源/目标语言
```

---

## 七、更新项目代码

如果项目发布了新版本，一行命令即可完成升级：

```bash
cd ~/video-voice-translator
./update_project.sh
```

脚本会自动：
1. 拉取项目最新代码（`git pull --ff-only`，失败会提示手动 stash）
2. 增量更新 Python 依赖（uv → 系统 pip 多级回退）
3. 增量更新前端依赖（`npm install`）
4. 重启所有服务

> 💡 更新脚本**绝不触碰 `.env` 文件**，您的 LLM 密钥会安全保留。

---

## 八、常见问题 FAQ

### Q1：7 天试用到期后怎么办？

A：返回 [购买页面](https://curl.qcloud.com/9j4S4Hug)，选择「HAI-GPU进阶型 不限购」套餐（¥777.6 / 月，3 折），应用名称选 PyTorch 基础镜像 → SSH 登录 → 粘贴同一行部署命令即可。如果旧实例中有重要的翻译结果，可以在到期前从 `data/outputs/` 目录下载到本地。

### Q2：翻译报错「API Key 无效」或「模型不存在」？

A：重新执行配置流程，检查三项必填：
- Base URL 是否与供应商完全一致（注意末尾是否有 `/v1`）
- API Key 是否完整复制，没有多余空格
- 模型名是否与供应商文档一致（大小写敏感）

修改配置后执行 `./manage-supervisor.sh restart` 重启服务，或直接在 Web `/setup` 页面保存并勾选重启。

### Q3：可以升级到更高配置吗？

A：当前 HAI 实例暂不支持原地升级配置。如果需要更高 GPU（如 A100），可以在购买页面选择更高规格的 HAI 套餐，同样选 PyTorch 基础镜像后运行同一行部署命令，配置流程与本文档完全一致。

### Q4：部署脚本中途失败（比如网络超时导致模型下载断了）？

A：**直接重跑一遍同一行命令即可**，脚本是幂等的：
- 仓库已拉取 → 自动 `git pull --ff-only` 拉最新
- `.env` 已存在 → 自动保留不覆盖
- 依赖、模型已下载 → 跳过重复步骤
- 真正只增量补跑失败的部分

如果反复在 `install.sh` 阶段失败，可以手动缩小镜像档位：
```bash
cd ~/video-voice-translator
./install.sh --mirror tencent      # 内网慢就切公网
./install.sh --mirror china        # 公网也慢切通用
```

### Q5：Web UI 无法访问？

A：按顺序排查：
1. HAI 控制台确认实例状态为「运行中」
2. 安全组是否放行了 **8080** 和 **8000** 端口（如前端实际跑在其他端口，放行对应端口）
3. SSH 登录后执行 `./manage-supervisor.sh status`，确认 backend 和 frontend 进程是 `RUNNING` 状态
4. 如均已停止，执行 `./manage-supervisor.sh start`

### Q6：如何停止实例以节省费用？

A：前往 HAI 控制台，选中实例后点击「关机」。关机期间不收取 GPU 算力费用，仅收取少量系统盘存储费用。下次需要使用时开机即可，所有数据和配置都保留。

### Q7：如何重新配置 LLM 信息（换供应商或换 Key）？

A：两种方式二选一：
1. **Web 方式**：访问 `http://<实例公网IP>:8080/setup` 可强制打开配置页（即使已配置过），填完保存即可覆盖
2. **命令行**：重新执行 `./configure.sh`，按提示输入新配置后会自动重启服务

---

## 九、参考资源

- [项目主 README](../README.md)
- [安装指南](INSTALL.md)
- [使用指南](USAGE.md)
- [流程文档](WORKFLOW.md)
- [环境变量高级配置](ENV_ADVANCED.md)
- [HAI 控制台](https://console.cloud.tencent.com/hai)
