# 环境变量高级配置说明

本文档覆盖 `.env` 文件中全部可选参数的详细说明。普通用户可直接通过 Web UI 引导页或 `./configure.sh` 完成配置，无需阅读本文档。

## 一、加载优先级

项目中环境变量的加载顺序（后面的优先级更高，可以覆盖前面的）：

```
脚本内置默认值  <  ~/.bashrc / ~/.zshrc  <  项目根目录 .env  <  进程环境变量（supervisor/docker/systemd）  <  CLI 参数
```

推荐所有用户配置都放在项目根目录的 `.env` 中，这是唯一的用户配置入口，方便统一管理。

---

## 二、LLM / 翻译配置（必填）

项目统一使用 OpenAI 兼容的 `/v1/chat/completions` 协议，任何兼容此协议的服务都可以直接使用。

### 三件套（必填）

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BASE_URL` | OpenAI 兼容接口的 Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_API_KEY` | 对应接口的 API Key；本地无鉴权部署填 `EMPTY` 或 `none` | `sk-xxxxxxxxxxxxxxxx` |
| `LLM_MODEL` | 模型名，按对应供应商的文档填写 | `qwen-flash` |

### 常见供应商参考值

| 供应商 | LLM_BASE_URL | LLM_MODEL 常用值 | API Key 申请地址 |
|--------|-------------|-----------------|-----------------|
| 阿里云 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-flash` / `qwen-plus` / `qwen-max` / `qwen3-max-2025-09-23` | [dashscope.console.aliyun.com/apiKey](https://dashscope.console.aliyun.com/apiKey) |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` | [cloud.siliconflow.cn/account/ak](https://cloud.siliconflow.cn/account/ak) |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) |
| 官方 OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` / `gpt-4o` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b-instruct`（Key 填 `EMPTY`） | 本地启动后自带，无需申请 |
| 本地 vLLM / LMDeploy / SGLang | `http://127.0.0.1:23333/v1` | 按启动时加载的模型填写 | 本地部署，自带 Key 或留空 |

### 调优参数（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_TEMPERATURE` | `0.1` | 采样温度，范围 0.0~2.0。翻译场景推荐 **0.05~0.2**（越低越保守、越稳定；越高越有创造性、可能不准确）。 |
| `LLM_TIMEOUT` | `300` | 单次翻译请求超时时间（秒）。大批量翻译或长文本翻译建议设置为 300~600。 |

---

## 三、安装阶段 / 镜像源配置

仅在**首次安装**或**手动更新依赖**时生效，HAI 镜像用户无需修改。

### MIRROR_MODE 可选值（推荐在 `.env` 中直接设置）

| 值 | 适用场景 | PyPI 源 | NPM 源 | HF 源 |
|----|---------|---------|--------|-------|
| `auto` | 默认，自动探测 | 分别探测 4 组后选择综合最快 | 同左 | 同左 |
| `tencent-intranet` | ✨ **腾讯云 ECS 同地域部署（推荐）** | `mirrors.tencentyun.com`（内网，免公网流量） | 腾讯云 NPM 镜像 | `hf-mirror.com` |
| `tencent` | 腾讯云公网 ECS / 其他使用腾讯云镜像的机器 | `mirrors.cloud.tencent.com/pypi` | 腾讯云 NPM 镜像 | `hf-mirror.com` |
| `china` | 国内通用（阿里云 + 清华 Nodesource） | 阿里云 PyPI | npmmirror | `hf-mirror.com` |
| `official` | 海外服务器 / 可直连国际网的本地开发机 | PyPI 官方 | NPM 官方 | HF 官方直连 |

### 强制覆盖镜像源（一般不用填）

| 变量 | 作用 | 示例 |
|------|------|------|
| `UV_DEFAULT_INDEX` | 强制指定 uv/pip 的 PyPI 源 | `http://mirrors.tencentyun.com/pypi/simple` |
| `NPM_REGISTRY` | 强制指定 NPM registry | `https://mirrors.cloud.tencent.com/npm/` |
| `NODE_SETUP_URL` | 强制指定 Node.js 20.x setup 脚本下载地址 | `https://mirrors.tuna.tsinghua.edu.cn/nodesource/setup_20.x` |
| `HF_ENDPOINT` | 强制指定 HuggingFace 镜像 | `https://hf-mirror.com`（国内推荐） |
| `USE_MODELSCOPE` | IndexTTS2 辅助模型是否走 ModelScope 下载 | `true`（国内推荐，HF 偶发断连时务必开启） |
| `UV_HTTP_TIMEOUT` | 安装阶段 uv 下载超时（秒），默认 `120` | `300`（海外网络不稳可调大） |

---

## 四、离线模式（可选）

当所有模型都已下载完成、部署环境需要**完全断网运行**时，可以开启以下两个变量，彻底禁止 transformers / huggingface_hub 联网：

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

开启前请确认所有必需的模型文件都已在本地缓存中（`~/.cache/huggingface/` 等目录），否则启动会报错。

---

## 五、DASHSCOPE_API_KEY（向后兼容兜底）

旧版本项目使用 `DASHSCOPE_API_KEY` 作为唯一的翻译配置入口。为了不破坏老用户的 `.env`，代码中保留了此兜底逻辑：

- 当且仅当 `LLM_BASE_URL` 和 `LLM_API_KEY` **全部留空**，且 `DASHSCOPE_API_KEY` 被填写时，自动启用 DashScope 兼容模式：
  - `LLM_BASE_URL` = `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - `LLM_API_KEY` = `DASHSCOPE_API_KEY`
  - `LLM_MODEL` = `qwen-flash`（也可以用 `LLM_MODEL` 单独覆盖）

**新用户建议直接使用三件套，不要再填 DASHSCOPE_API_KEY。**
