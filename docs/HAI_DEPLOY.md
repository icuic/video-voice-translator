# 腾讯云 HAI 一键部署指南

本项目采用「**HAI 官方 PyTorch 基础镜像 + 浏览器 Web 终端 + 一行部署脚本**」方式，**无需下载 SSH 客户端、无需填 IP/用户名/密码、无需任何客户端**。

**部署耗时：3~8 分钟**（预打包 Docker 镜像，HAI 内网下载极快；若 Docker 路径失败自动回退源码安装 10~20 分钟兜底，100% 成功）。

> 为什么不是「自定义应用镜像」：腾讯云 HAI 目前暂不支持跨账号共享自定义应用镜像（镜像仅限作者账号下使用）。因此选用「预打包 Docker 镜像 + 一行脚本」方案，任何用户从推广链接购买后都能一键安装，且安装源始终是最新版本。
>
> 为什么不用桌面客户端：HAI 自带浏览器 Web 终端，鉴权、连接、IP 全由腾讯云控制台处理，小白只需「点击登录 → 右键粘贴一行命令 → 回车」，比下载客户端更简单。

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
4. 在「**应用名称**」下拉框中选择 **「PyTorch 2.x / 3.x」** 或 **「基础镜像」**（官方通用 PyTorch 基础镜像，已自带 GPU 驱动、CUDA，无需额外配置）
5. 选择算力方案（默认 GPU-32GB 显存即可）和时长（7 天）
6. 点击「立即购买」并完成支付

> ⚠️ **注意**：应用名称不需要选「AI 音视频翻译系统」（因为没做自定义镜像），选官方的 PyTorch 基础镜像就好，下一步的一行命令会自动完成项目安装。

---

## 二、等待实例启动

支付完成后，前往 [腾讯云 HAI 控制台](https://console.cloud.tencent.com/hai) 查看实例状态：

- 状态显示为「创建中」→ 通常需要 2~3 分钟
- 状态变为「运行中」→ 实例准备完毕

**记录实例的公网 IP**（形如 `1.2.3.4`），下一步部署完成后需要在浏览器打开。

---

## 三、执行部署脚本（Web 终端 3 步 + 一行命令）

> ✨ **全程 0 下载、0 SSH 知识、无需填 IP/密码**：HAI 控制台自带 Web 终端，浏览器里直接开终端，自动鉴权。

### 3.1 打开 Web 终端

1. 在 [HAI 控制台](https://console.cloud.tencent.com/hai) 找到刚才启动的实例卡片
2. 点击卡片右上角的 **「登录」或「Web 终端」** 按钮（位置如下图红框示意）
3. 浏览器会自动弹出一个黑色的终端窗口，且已自动登录到 `ubuntu` 用户——**不需要填任何 IP、用户名、密码**。

> 💡 如果弹出来需要输密码，密码是你创建 HAI 实例时自己设置的那个。

### 3.2 粘贴一行命令（推荐国内加速版）

在黑色的终端窗口里 **右键 → 粘贴** 下面的命令，然后 **回车**：

```bash
bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
```

**备用加速**（如果 ghproxy 不可用，换 GitHub 直链）：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
```

### 3.3 部署脚本自动完成以下工作

你只需等待，不需要做任何交互。脚本会**自动选择最快路径**：

| 阶段 | 说明 | 耗时（典型） |
|------|------|-------------|
| ① 环境检测 | nvidia-smi GPU / Docker / nvidia 运行时 | < 20s |
| ② 系统依赖 | git / curl / ffmpeg / python3 / docker 如缺失自动补 | < 30s |
| ③ 拉取代码 | `git clone` 项目到 `~/video-voice-translator` | < 10s |
| ④ 预置 .env | 复制模板，镜像源已设腾讯云内网 | < 1s |
| ⑤ **路径 A（首选）**：拉取预打包 Docker 镜像<br>　→ 先拉 `ghcr.io`（免费公共镜像）<br>　→ 失败自动 fallback 到 TCR 个人版（内网极速） | 核心耗时，99% 用户走这条 | **3~8 分钟** |
| ⑤ **路径 B（兜底）**：源码现场编译安装<br>　→ `.venv` / 下载模型 / 前端依赖<br>　仅在 Docker 路径全失败时触发 | 稳但慢，100% 能成 | **10~20 分钟** |
| ⑥ MOTD 横幅 | 追加 SSH 登录欢迎语（下次 SSH 登录显示） | < 5s |
| ⑦ 输出访问地址 | 从元数据自动获取公网 IP，打印 8080/8000 地址 | < 1s |

看到下面这个绿色的完成横幅，就说明部署成功了：

```
┌──────────────────────────────────────────────────────────┐
│ 🎉 部署方式： docker / source
│ 🌐 访问地址（首次打开自动跳配置页）                        │
│    前端翻译界面：  http://1.2.3.4:8080                   │
│    后端 API 文档： http://1.2.3.4:8000/docs              │
└──────────────────────────────────────────────────────────┘
```

> 💡 **如果脚本中途报错断了？** 直接把上面的一行命令**再粘贴一遍回车就行**，脚本是幂等的：已拉的代码/模型/依赖不会重复下载，只补跑失败部分。

---

## 四、配置 LLM 翻译密钥（二选一）

本项目使用 OpenAI 兼容 `/v1/chat/completions` 协议做文本翻译，**任何兼容该协议的 LLM 服务商都能接入**。

**首次使用必须完成此步，否则翻译功能不可用。**

### 方式一（👶 推荐新手）：Web UI 引导页配置

浏览器打开终端里打印出来的前端地址：

```
http://<实例公网IP>:8080
```

首次访问会**自动跳转**到 `/setup` 配置页，按提示手填三项必填信息：

| 字段 | 说明 |
|------|------|
| **LLM Base URL** | 完整的 OpenAI 兼容 Base URL（通常以 `/v1` 结尾），示例：`https://api.example.com/v1` |
| **LLM API Key** | 服务商给的 API Key（本地自建无鉴权填 `EMPTY`） |
| **模型名** | 按供应商文档填，如 `qwen2.5-72b-instruct` / `deepseek-chat` / `gpt-4o-mini` 等 |

- 「高级选项」默认折叠（温度、超时、立即重启），初学者不用展开
- 点「保存」成功后 2~3 秒自动跳转到翻译主页

### 方式二：命令行交互式配置（适合习惯 SSH 的用户）

在 Web 终端里执行：

```bash
cd ~/video-voice-translator
./configure.sh
```

按提示依次填写 → 脚本会显示配置摘要（API Key 自动脱敏）→ 确认 `[Y/n]` → 原子写入 `.env`，保留镜像源变量不覆盖 → 可选立即重启服务。

---

## 五、开始使用

访问 `http://<实例公网IP>:8080`，进入 Web UI：

1. **上传文件**：拖拽或点击上传视频（MP4/AVI/MOV/MKV 等）或音频（WAV/MP3/M4A 等）
2. **选择源语言 / 目标语言**（支持中英文双向翻译）
3. 点击「开始翻译」，进度条实时显示 9 步处理流程
4. 翻译完成后，在分段列表中可编辑翻译文本、重新翻译单段、重新合成语音
5. 点击「重新生成最终视频」合并修改，下载翻译后的视频

### 其他访问地址

| 服务 | 地址 |
|------|------|
| 前端 Web UI | `http://<实例公网IP>:8080` |
| 前端备用端口（dev server） | `http://<实例公网IP>:5173` |
| 后端 API 文档（Swagger） | `http://<实例公网IP>:8000/docs` |
| 后端健康检查 | `http://<实例公网IP>:8000/health` |
| 配置页（随时可重进） | `http://<实例公网IP>:8080/setup` |

---

## 六、服务管理命令

根据你部署时使用的模式（Docker / 源码），选择对应的命令。脚本部署成功后终端里也打印了一份。

### Docker 模式（99% 用户，3~8 分钟那条路径）

```bash
sudo docker ps | grep vvt                  # 查看容器状态
sudo docker logs -f vvt                    # 实时查看日志（Ctrl+C 退出）
sudo docker restart vvt                    # 重启（改 .env / 配置后用）
sudo docker stop vvt                       # 停止服务
sudo docker start vvt                      # 再次启动
```

数据（翻译结果、上传文件、.env）存在宿主机的：
- `~/video-voice-translator/vvt-data/`  → 翻译产物、日志
- `~/video-voice-translator/vvt-env/`   → `.env` 配置文件

容器被 `docker rm` 也不会丢。

### 源码模式（Docker 路径失败时才会走）

```bash
cd ~/video-voice-translator
./manage-supervisor.sh start              # 启动
./manage-supervisor.sh stop               # 停止
./manage-supervisor.sh restart            # 重启
./manage-supervisor.sh status             # 进程状态
./manage-supervisor.sh tail all           # 实时日志
```

---

## 七、更新到新版本

### Docker 模式（推荐一行命令重跑）

```bash
# 最简单：重跑 hai-deploy.sh，会自动拉取 latest 镜像并重建容器
bash -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/icuic/video-voice-translator/master/hai-deploy.sh)"
```

或手动：

```bash
cd ~/video-voice-translator
sudo docker pull ghcr.io/icuic/video-voice-translator:latest
sudo docker rm -f vvt
sudo docker compose up -d          # 或 docker compose pull && docker compose up -d
```

### 源码模式

```bash
cd ~/video-voice-translator
./update_project.sh    # 自动 git pull + 同步依赖 + 重启服务，永不碰 .env
```

---

## 八、常见问题 FAQ

### Q1：7 天试用到期后怎么办？

A：返回 [购买页面](https://curl.qcloud.com/9j4S4Hug)，选择「HAI-GPU进阶型 不限购」套餐（¥777.6 / 月，3 折），应用名称选 PyTorch 基础镜像 → 打开 Web 终端 → 粘贴同一行部署命令即可。如果旧实例中有重要翻译结果，可在到期前从 `vvt-data/outputs/` 或 `data/outputs/` 下载到本地。

### Q2：翻译报错「API Key 无效」或「模型不存在」？

A：重新走配置流程检查三项：
- Base URL 是否完全匹配供应商说明（末尾 `/v1` 不能少）
- API Key 是否复制完整，无多余空格
- 模型名是否和供应商文档一致（大小写敏感）

改完后 Docker 模式执行 `sudo docker restart vvt`；源码模式 `./manage-supervisor.sh restart`；或直接在 Web `/setup` 页保存并勾选「立即重启」。

### Q3：可以升级到更高 GPU 配置吗？

A：HAI 不支持原地升级。需要更高 GPU（如 A100）就买更高套餐，同样选 PyTorch 基础镜像后跑同一行部署命令即可。

### Q4：Docker 拉镜像一直断 / 很慢？

A：脚本先拉 `ghcr.io`（全球公共），失败自动切到 TCR 内网极速。如果两条都断（极端情况），脚本自动回退到源码路径 `install.sh`，耐心等 10~20 分钟。

### Q5：部署脚本中途失败（网络超时、Ctrl+C 中断了）？

A：**直接把同一行命令再粘贴一遍回车即可**，脚本是幂等的：
- 仓库已存在 → `git pull --ff-only` 拉最新
- `.env` 已存在 → 保留不覆盖
- Docker 镜像已拉到本地 → 跳过 pull
- 模型/依赖已下载 → 不重复走

### Q6：Web UI 打不开 / 浏览器连不上 8080？

A：按顺序排查：
1. HAI 控制台实例状态是不是「运行中」
2. HAI 安全组是否入方向放行了 **8080**、**8000**、**5173** 端口（HAI 基础镜像默认会放开常用端口，但被你自定义关闭时要手动开启）
3. Docker 模式：`sudo docker ps` 看 `vvt` 容器是否 `Up`，否则 `sudo docker logs --tail 100 vvt` 看报错
4. 源码模式：`./manage-supervisor.sh status` 看 backend / frontend 是否 RUNNING

### Q7：如何停止实例节省费用？

A：去 HAI 控制台选中实例 → 「关机」。关机期间不收取 GPU 算力费，仅收少量系统盘存储费。下次开机即可，`vvt` 容器会 `unless-stopped` 自动起来。

### Q8：如何重新配置 LLM（换供应商 / 换 Key）？

A：两种：
1. Web：随时打开 `http://<实例公网IP>:8080/setup` 保存覆盖
2. 命令行：`cd ~/video-voice-translator && ./configure.sh`

---

## 九、参考资源

- [项目主 README](../README.md)
- [安装指南对比表](INSTALL.md)
- [使用指南](USAGE.md)
- [处理流程说明](WORKFLOW.md)
- [环境变量高级配置（供应商对照表 / 5 档镜像源 / 离线模式）](ENV_ADVANCED.md)
- [腾讯云 HAI 控制台](https://console.cloud.tencent.com/hai)
- [HAI 购买推广链接（作者返佣支持维护，用户价不变）](https://curl.qcloud.com/9j4S4Hug)

