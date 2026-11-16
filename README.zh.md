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
| `ZONOS3_PINYIN_ENABLED` | `false` | 仅在最终语言为 `cmn` 时，将方括号拼音转换为 IPA |
| `ZONOS3_IPA_ENABLED` | `false` | 所有语言均可将 `{{IPA}}` 转换为模型音素边界 |
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

### 可选方括号拼音输入

设置 `ZONOS3_PINYIN_ENABLED=true` 后，speech 和 clone 接口支持
`[nǐ][hǎo]`、`[nǐ hǎo]`。优先使用请求的 `language`；省略或为 null 时使用
`ZONOS3_LANGUAGE`。只有最终语言为 `cmn` 才转换，关闭功能或其他语言均原样传入。

每对方括号是独立的变调范围：`[nǐ][hǎo]` 保留两个三声；`[nǐ hǎo]` 将前一个
三声转成二声。连续三个或更多三声采用“除最后一个外均转二声”的确定性规则，
不跨括号，也不结合括号外汉字变调。这不是基于语法的韵律分析；暂不自动处理
“一/不”变调或半三声。需要指定其他实际读音时，可在独立括号里显式标调。

支持紧贴音节的儿化后缀 `r`：`[huār]`、`[hua1r]` 均转换为一个儿化音节；
数字声调写在 `r` **之前**。`[huā ér]` 和 `[huā][ér]` 均保留两个独立音节，
单独的 `ér`/`er2` 不会被误识别为后缀。
转换先处理韵母，再附加该音节唯一的调值：包括前元音韵尾/鼻尾 n 的脱落、
ng 脱落后保留鼻化，以及卷舌元音或滑音形式。使用模型支持的 `ɚ` / `ɚ̯`，
不简单追加 ASCII `r` 或独立带调的“儿”。这是普通话宽式转换，不覆盖各地方口音；
不支持的韵母（包括在 `er` 上重复儿化）返回 422。
规则类别参考[语音研究表 2](https://www.atlantis-press.com/article/125988795.pdf)。

同组音节用空白分隔。支持声调符号或末尾数字（如 `ni3`，1–4 为四声，0/5 为轻声），
不标调视为轻声；支持 `ü`、`v`、`u:`。使用 `pinyin-to-ipa==1.0.1` 的第一种音值候选，
在音节末附加上标调值，并用当前模型的音素表校验。已有 IPA 边界组和括号外文本原样保留。
启用且语言为中文时，方括号专用于拼音：空组、嵌套、不配对、非法音节或不支持的音素
在进入推理队列前返回 422。模型必须加载音素文本行，不能用 `ZONOS3_TEXT_ROWS` 将其禁用。

```json
{"input":"[nǐ hǎo]，欢迎使用。", "voice":"file://alice", "language":"cmn"}
```

变调只控制应用层生成的 IPA，模型发音仍可能受上下文影响；尚未实测音频。
已提供 `tests/test_pinyin.py` 单元测试源码，本次未执行。

### 可选易输入 IPA 边界

设置 `ZONOS3_IPA_ENABLED=true` 后，speech 和 clone 的输入均可使用 `{{kuɔ³⁵}}`。
该开关独立于拼音开关，默认关闭，适用于所有受支持的语言。应用层将双花括号
替换为 U+E000/U+E001，内部 IPA 原样传入，不做拼音转换、变调、去空白或 Unicode 归一化。

```json
{"input":"读音示例：{{kuɔ³⁵}}。", "voice":"file://alice", "language":"cmn"}
```

两个开关同时启用时，可输入 `[nǐ hǎo]，{{kuɔ³⁵}}`。先转换显式 IPA 边界，
再转换中文拼音；拼音处理会跳过 IPA 组。已有 Unicode 音素组和普通文本原样保留，
两种语法不能互相嵌套。空组、嵌套、不配对或含不支持音素的 IPA 组在推理前返回 422；
组内不支持空格、斜杠分隔符、汉字或普通数字声调，模型必须已加载音素文本行。
单个普通花括号不是分隔符；开关关闭时，转换器不赋予 `{{…}}` 特殊含义。
已提供 `tests/test_ipa.py` 测试源码，本次未执行。

### 目录文件

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
