# zonos3-mini-open-tts

[English](./README.md) · **中文**

基于 [Open TTS 规范](https://github.com/OpenTTSGroup/open-tts-spec) 的
[Zyphra/ZONOS3-Mini](https://github.com/Zyphra/ZONOS3-Mini) 适配。
使用官方 **原生 PyTorch 参考实现** `zonos3.reference`，不使用 WebGPU、GGUF、ggml 或 MLX。
本项目没有采用 Mini-SGLang 优化服务，性能与显存需求不能直接套用其指标，也不承诺实时速度。

## 功能

- OpenAI 兼容语音接口、文件音色目录、multipart 上传克隆。
- CUDA 音频前缀克隆，以及 CUDA/CPU 说话人嵌入克隆。
- 从上游注册表读取原生语言代码，包括中文 `cmn`、英语 `en_us`、日语 `ja` 等。
- MP3、Opus、AAC、FLAC、WAV、PCM 六种完整音频输出。
  原生为 44,100 Hz 单声道；Opus 在编码边界转换为其支持的 48,000 Hz；PCM 为有符号 16 位小端格式。
- 后台加载期间 `/healthz` 返回 `loading`；并发闸门、可选队列上限和超时、CORS 开关、临时上传清理。
- 不提供内置音色 ID、流式接口或自然语言声音设计接口。
  接受但忽略 `speed`、`instructions`、`model` 和参考转录文本。

## 快速开始（Docker）

以下是供部署时使用的命令，本次开发未执行。镜像名假定发布至 OpenTTSGroup，
自行发布时请替换 owner；此次改动没有实际发布镜像。

```bash
docker pull ghcr.io/openttsgroup/zonos3-mini-open-tts:latest
docker run --rm --gpus all -p 8000:8000 \
  -v "$PWD/voices:/voices:ro" -v "$PWD/cache:/root/.cache" \
  -e ZONOS3_LANGUAGE=cmn \
  ghcr.io/openttsgroup/zonos3-mini-open-tts:latest
```

CPU 部署移除 `--gpus all`，加入 `-e ZONOS3_DEVICE=cpu`，自动选择嵌入克隆与 FP32。
音频前缀编码需要 CUDA，在 CPU 上显式配置 `reference` 会在启动时失败。
上游前缀编码器内部使用 BF16，与语言模型 dtype 设置无关，需使用支持相应计算的 CUDA 硬件。
本项目尚未进行硬件验证或性能测试。

权重仅在**服务启动时**通过上游 Hugging Face SDK 下载到 `/root/.cache/huggingface`，
包括语言模型、额外文本行、解码器和选定的参考音频/说话人编码器。镜像构建不下载权重。
请持久挂载 `/root/.cache`；完整缓存就绪后可用 `HF_HUB_OFFLINE=1` 离线运行。
加载失败会退出进程，避免永久假就绪。仅挂载本地 LM 目录并不能替代注册表引用的全部编码器和解码器资源。

Compose 示例：`docker compose -f docker/docker-compose.example.yml up`。
CPU 使用时移除其 GPU `deploy` 段，设置 `ZONOS3_DEVICE=cpu`。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ZONOS3_MODEL` | `Zyphra/ZONOS3-Mini` | HF 仓库 ID 自动展开为 `hf://<repo>/lm/zonos3_mini`；也可填完整 `hf://` LM 目录或含 `params.json`、`model.pth` 的本地目录 |
| `ZONOS3_DEVICE` | `auto` | `auto`、`cuda`、`cpu` |
| `ZONOS3_CUDA_INDEX` | `0` | 可见 GPU 的索引 |
| `ZONOS3_DTYPE` | `auto` | `auto`、`bfloat16`、`float32`；支持 BF16 的 CUDA 上自动选 BF16，否则 FP32；CPU 固定 FP32；只控制 LM |
| `ZONOS3_SPEAKER_MODE` | `auto` | CUDA 自动用 `reference`，CPU 自动用 `embedding`；也可显式选择，受硬件约束 |
| `ZONOS3_LANGUAGE` | `en_us` | 默认原生语言代码，通过 `/v1/audio/languages` 查询 |
| `ZONOS3_MAX_TOKENS` | `2000` | 生成音频行数预算，1–8192，还受模型上下文容量限制，不是文本字符数 |
| `ZONOS3_TEXT_ROWS` | 未设置 | 默认发布 LM 自动加载音素/起始/停顿文本行；其他 LM 可指定文件或 `hf://` URI；空字符串禁用 |
| `VOICES_DIR` | `/voices` | 只读文件音色目录 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | HTTP 监听地址与端口 |
| `LOG_LEVEL` | `info` | 日志级别 |
| `MAX_INPUT_CHARS` | `8000` | 文本长度限制，超限返回 413 |
| `MAX_AUDIO_BYTES` | `52428800` | 参考音频文件大小限制 |
| `DEFAULT_RESPONSE_FORMAT` | `mp3` | 未指定格式或 JSON null 时使用 |
| `MAX_CONCURRENCY` | `1` | 只能为 1，共享参考模型状态不可重入 |
| `MAX_QUEUE_SIZE` | `0` | 等待队列容量，0 不限制 |
| `QUEUE_TIMEOUT` | `0` | 等待超时秒数，0 不限制 |
| `CORS_ENABLED` | `false` | true 时允许所有 origin、method、header |
| `HF_HOME` | `/root/.cache/huggingface` | Docker 中的 SDK 缓存目录 |
| `HF_HUB_OFFLINE` | 未设置 | 设为 1 后仅使用本地缓存 |

仅使用**一个 Uvicorn worker**。entrypoint 无参数时读取监听与日志配置；传入命令时原样执行。
队列满或等待超时返回 503。阻塞推理在工作线程中执行；取消请求时等待线程结束，
再释放并发令牌并删除参考文件，避免同一模型仍在计算时接入下一次请求。

## API 参考

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 加载状态、能力、设备、LM dtype、队列计数 |
| GET | `/v1/audio/voices` | `{ "voices": [...] }`，文件音色 ID 带 `file://` |
| GET | `/v1/audio/voices/preview?id=alice` | 参考 WAV 试听，id 不带 URI 前缀 |
| GET | `/v1/audio/languages` | `{ "languages": [{ "key", "name" }] }`，来自固定上游版本的注册表 |
| POST | `/v1/audio/speech` | JSON 请求，返回完整编码音频 |
| POST | `/v1/audio/clone` | multipart 上传，返回完整编码音频 |

`/v1/audio/design`、`/v1/audio/realtime` 未注册，返回 404。
`/healthz.capabilities` 中 clone/languages 为 true，streaming/design/builtin_voices 为 false。
未知 JSON 字段忽略；非法格式或语言返回 422，找不到文件音色返回 404，
不带 `file://` 的普通音色名返回 422，不支持的远程 URI 返回 501。
音频内容由上游解码校验，不能通过 voice 参数选择目录外的本地路径。
`/docs` 提供自动生成的接口文档。

### POST /v1/audio/speech

| 字段 | 类型 | 默认值 | 状态 | 说明 |
|---|---|---|---|---|
| `input` | string | — | required | 非空白待合成文本 |
| `voice` | string | — | required | 目录中的 `file://alice` |
| `response_format` | string/null | `mp3`（服务配置） | supported | `mp3`、`opus`、`aac`、`flac`、`wav`、`pcm` |
| `model` | string/null | null | ignored | OpenAI 兼容，不切换权重 |
| `speed` | number | 1.0 | ignored | 接受 0.25–4.0，不改变语速或做时间伸缩 |
| `instructions` | string/null | null | ignored | 不做自由文本风格映射 |
| `language` | string/null | `ZONOS3_LANGUAGE` | extension | 原生语言代码 |
| `seed` | integer/null | 随机 | extension | 0–2147483647 |
| `temperature` | number/null | 0.75 | extension | 0–5 |
| `top_k` | integer/null | 80 | extension | 1–4096，映射到上游 `topk` |
| `top_p` | number/null | 0.69 | extension | 大于 0 且不超过 1 |
| `max_tokens` | integer/null | `ZONOS3_MAX_TOKENS` | extension | 1–8192 个音频行，另受剩余上下文限制 |

```bash
curl http://localhost:8000/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"你好，这是语音合成示例。","voice":"file://alice","language":"cmn","seed":42,"response_format":"wav"}' \
  --output speech.wav
```

### POST /v1/audio/clone

| 字段 | 类型 | 默认值 | 状态 | 说明 |
|---|---|---|---|---|
| `audio` | file | — | required | WAV/MP3/FLAC/OGG/Opus/M4A/AAC/WebM，由 ffmpeg 解码 |
| `input` | string | — | required | 非空白待合成文本 |
| `prompt_text` | string | — | required | 必须传字段；内容忽略，允许显式空字符串 |
| `response_format` | string | `mp3`（服务配置） | supported | 六种格式均支持 |
| `model` | string | 未提供 | ignored | OpenAI 兼容 |
| `speed` | number | 1.0 | ignored | 接受 0.25–4.0 |
| `instructions` | string | 未提供 | ignored | 不做自由文本风格映射 |
| `language` | string | `ZONOS3_LANGUAGE` | extension | 原生语言代码 |
| `seed` | integer | 随机 | extension | 0–2147483647 |
| `temperature` | number | 0.75 | extension | 0–5 |
| `top_k` | integer | 80 | extension | 1–4096 |
| `top_p` | number | 0.69 | extension | 大于 0 且不超过 1 |
| `max_tokens` | integer | `ZONOS3_MAX_TOKENS` | extension | 1–8192 个音频行，受上下文限制 |

```bash
curl http://localhost:8000/v1/audio/clone \
  -F 'audio=@reference.wav' -F 'prompt_text=参考音频转录。' \
  -F 'input=你好，这是克隆语音。' -F 'language=cmn' -F 'response_format=wav' \
  --output cloned.wav
```

上传只存临时文件，不加入音色目录。前缀克隆要求参考音频至少 0.5 秒，
上游编码器按检查点的参考时长上限截取。建议使用简短、干净的单说话人录音。
两种克隆路径均不使用转录文本；适配层不维护 prompt 缓存。

## 音色目录

```text
voices/
  alice.wav
  alice.txt
  alice.yml       # 可选 YAML 元数据对象
```

仅扫描顶层。WAV 与 UTF-8 TXT 必须同时存在且非空，虽然本模型忽略转录文本，
仍保留规范约定。YAML 使用安全解析，损坏的元数据仅警告并忽略。
列表使用 `file://alice`，试听参数使用 `id=alice`。每次扫描可反映文件及元数据更新；
目录外路径和逃逸符号链接不可选。本适配不自带音色或模型权重。

## 开发

`engine` 为未修改的官方 Git submodule，固定到
`96d9e0ec1e39083ed336ac78f24e3dbc93721c0f`。
依据上游要求使用 Python 3.12+、PyTorch/torchaudio 2.9.1、transformers 4.56–4.57.3。
Docker 使用 CUDA 12.8、Ubuntu 24.04（提供系统 Python 3.12），分离 builder/runtime。
仅安装 `engine/model` 和固定版本 FuseAlign 包，不安装根 uv workspace 中的其他后端。
FuseAlign 是上游模型包声明的依赖；本适配不加载对齐模型或 ASR 模型，也不修改上游源码。

```bash
git clone --recurse-submodules <你的适配仓库地址>
cd zonos3-mini-open-tts
docker build -f docker/Dockerfile -t zonos3-mini-open-tts:local .
```

已有检出可用 `git submodule update --init --recursive` 补齐源码子模块。
GitHub Actions 在 main push、`v*` tag 或手动触发时构建单一 linux/amd64 镜像，
发布 latest、短 SHA 和版本标签；构建不下载模型。
此次只完成源码与静态检查，未构建镜像、运行服务或推理、下载模型、安装依赖；
Docker、CI 和实际音频效果仍需部署环境验证。
