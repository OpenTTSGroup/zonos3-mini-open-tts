# zonos3-mini-open-tts

**English** · [中文](./README.zh.md)

[Open TTS](https://github.com/OpenTTSGroup/open-tts-spec) adapter for
[Zyphra/ZONOS3-Mini](https://github.com/Zyphra/ZONOS3-Mini), using the upstream
**plain PyTorch reference implementation** (`zonos3.reference`). No WebGPU,
GGUF, ggml or MLX backend is used. This is not the optimized Mini-SGLang server;
its latency and memory requirements differ. No real-time performance is promised.

## Features

- OpenAI-compatible speech, directory voices and multipart voice cloning.
- CUDA raw-reference-prefix cloning; CUDA/CPU speaker-embedding cloning.
- Native language codes from the upstream registry, including `cmn`, `en_us`, `ja`.
- MP3, Opus, AAC, FLAC, WAV and signed little-endian PCM16 output. Mono 44,100 Hz,
  except Opus which is encoded at 48,000 Hz as required by its codec.
- Background initialization with `/healthz` reporting `loading`; bounded optional
  queue, configurable CORS and temporary upload cleanup.
- No built-in voice IDs, streaming endpoint or natural-language voice-design endpoint.
  `speed`, `instructions`, `model` and reference transcripts are accepted but ignored.

## Quick Start (Docker)

The following commands are deployment instructions; they were not executed during
adapter development. The image name assumes publication under OpenTTSGroup; replace
the owner with your own if publishing elsewhere. An image has not been published by
this change.

```bash
docker pull ghcr.io/openttsgroup/zonos3-mini-open-tts:latest
docker run --rm --gpus all -p 8000:8000 \
  -v "$PWD/voices:/voices:ro" -v "$PWD/cache:/root/.cache" \
  -e ZONOS3_LANGUAGE=cmn \
  ghcr.io/openttsgroup/zonos3-mini-open-tts:latest
```

For CPU, omit `--gpus all` and add `-e ZONOS3_DEVICE=cpu`. Automatic speaker mode
then selects embedding cloning and FP32. Raw-reference-prefix encoding requires
CUDA; explicitly requesting that mode on CPU fails at startup. The upstream raw
encoder uses BF16 internally, independently of the LM dtype. Use suitable CUDA
hardware; this adapter has not been benchmarked or hardware-qualified.

Weights are fetched **only at service startup** through the upstream Hugging Face
SDK helpers into `/root/.cache/huggingface`: LM, extra text rows, decoder and the
selected reference/speaker encoder. Mount `/root/.cache` persistently. No weights
are placed in the Docker image. `HF_HUB_OFFLINE=1` uses an already complete cache;
missing files or loading failures terminate the process. A local LM directory alone
does not contain all codec/speaker assets referenced by the upstream registries.

Compose example: `docker compose -f docker/docker-compose.example.yml up`.
For CPU remove its GPU `deploy` section and set `ZONOS3_DEVICE=cpu`.

## Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `ZONOS3_MODEL` | `Zyphra/ZONOS3-Mini` | HF repo ID expands to `hf://<repo>/lm/zonos3_mini`; also accepts an explicit `hf://` LM folder or local folder containing `params.json` and `model.pth` |
| `ZONOS3_DEVICE` | `auto` | `auto`, `cuda`, `cpu` |
| `ZONOS3_CUDA_INDEX` | `0` | Visible GPU index |
| `ZONOS3_DTYPE` | `auto` | `auto`, `bfloat16`, `float32`; auto uses BF16 on supported CUDA devices, otherwise FP32; CPU always FP32; applies to LM only |
| `ZONOS3_SPEAKER_MODE` | `auto` | `reference` on CUDA, `embedding` on CPU; can explicitly select either mode subject to hardware support |
| `ZONOS3_LANGUAGE` | `en_us` | Default native language code; see `/v1/audio/languages` |
| `ZONOS3_MAX_TOKENS` | `2000` | Audio-row budget, 1–8192, further limited by model context; not a character count |
| `ZONOS3_TEXT_ROWS` | unset | Release extra phoneme/start/pause rows for the default LM; explicit file/`hf://` URI for other LMs; empty disables |
| `VOICES_DIR` | `/voices` | Read-only voice catalog |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | HTTP binding |
| `LOG_LEVEL` | `info` | Log verbosity |
| `MAX_INPUT_CHARS` | `8000` | Text limit; oversized requests return 413 |
| `MAX_AUDIO_BYTES` | `52428800` | Reference-file size limit |
| `DEFAULT_RESPONSE_FORMAT` | `mp3` | Format when omitted or JSON null |
| `MAX_CONCURRENCY` | `1` | Must be 1: shared reference-model state is not reentrant |
| `MAX_QUEUE_SIZE` | `0` | Maximum waiting requests; 0 means unlimited |
| `QUEUE_TIMEOUT` | `0` | Waiting timeout in seconds; 0 means unlimited |
| `CORS_ENABLED` | `false` | Enable unrestricted origins/methods/headers when true |
| `HF_HOME` | `/root/.cache/huggingface` | SDK cache in Docker |
| `HF_HUB_OFFLINE` | unset | Set to 1 for cached, offline operation |

Use **one Uvicorn worker**. The entrypoint honors host/port/log settings when run
without arguments; supplied command arguments are executed verbatim. Queue full or
timeout returns 503. Blocking inference runs in a worker thread; cancellation waits
for that thread before releasing the gate or deleting its reference file.

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/healthz` | Loading/ready status, capabilities, device, LM dtype, queue counters |
| GET | `/v1/audio/voices` | `{ "voices": [...] }`, file IDs include `file://` |
| GET | `/v1/audio/voices/preview?id=alice` | Reference WAV; plain ID, no URI prefix |
| GET | `/v1/audio/languages` | `{ "languages": [{ "key", "name" }] }` from pinned upstream registry |
| POST | `/v1/audio/speech` | JSON request, complete encoded audio |
| POST | `/v1/audio/clone` | Multipart upload, complete encoded audio |

`/v1/audio/design` and `/v1/audio/realtime` are not registered (404).
`/healthz.capabilities` declares clone/languages true and streaming/design/builtin_voices false.
Unknown JSON fields are ignored. Unsupported formats/languages return 422; missing
file voices return 404; bare voice IDs return 422; unsupported remote voice URIs
return 501. Invalid audio is rejected by upstream decoding, without exposing a
local path as a selectable voice. `/docs` exposes generated OpenAPI documentation.

### POST /v1/audio/speech

| Field | Type | Default | Status | Meaning |
|---|---|---|---|---|
| `input` | string | — | required | Nonblank text |
| `voice` | string | — | required | `file://alice` from the catalog |
| `response_format` | string/null | `mp3` (service setting) | supported | `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm` |
| `model` | string/null | null | ignored | OpenAI compatibility; never switches weights |
| `speed` | number | 1.0 | ignored | Accepted range 0.25–4.0; no time stretching |
| `instructions` | string/null | null | ignored | No free-text style mapping |
| `language` | string/null | `ZONOS3_LANGUAGE` | extension | Native upstream language code |
| `seed` | integer/null | random | extension | 0–2147483647 |
| `temperature` | number/null | 0.75 | extension | 0–5 |
| `top_k` | integer/null | 80 | extension | 1–4096; mapped to upstream `topk` |
| `top_p` | number/null | 0.69 | extension | Greater than 0, at most 1 |
| `max_tokens` | integer/null | `ZONOS3_MAX_TOKENS` | extension | 1–8192 audio rows; upstream also caps against remaining context |

```bash
curl http://localhost:8000/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"你好，这是语音合成示例。","voice":"file://alice","language":"cmn","seed":42,"response_format":"wav"}' \
  --output speech.wav
```

### POST /v1/audio/clone

| Field | Type | Default | Status | Meaning |
|---|---|---|---|---|
| `audio` | file | — | required | WAV/MP3/FLAC/OGG/Opus/M4A/AAC/WebM; decoded by ffmpeg |
| `input` | string | — | required | Nonblank text |
| `prompt_text` | string | — | required | Contract requires field; content ignored, empty string is accepted |
| `response_format` | string | `mp3` (service setting) | supported | All six formats |
| `model` | string | absent | ignored | OpenAI compatibility |
| `speed` | number | 1.0 | ignored | 0.25–4.0 |
| `instructions` | string | absent | ignored | No free-text style mapping |
| `language` | string | `ZONOS3_LANGUAGE` | extension | Native upstream language code |
| `seed` | integer | random | extension | 0–2147483647 |
| `temperature` | number | 0.75 | extension | 0–5 |
| `top_k` | integer | 80 | extension | 1–4096 |
| `top_p` | number | 0.69 | extension | Greater than 0, at most 1 |
| `max_tokens` | integer | `ZONOS3_MAX_TOKENS` | extension | 1–8192 audio rows, context-limited |

```bash
curl http://localhost:8000/v1/audio/clone \
  -F 'audio=@reference.wav' -F 'prompt_text=Reference transcript.' \
  -F 'input=Hello from ZONOS3.' -F 'language=en_us' -F 'response_format=wav' \
  --output cloned.wav
```

Uploads are temporary and never added to the voice catalog. Reference mode requires
at least 0.5 seconds of audio; the upstream encoder trims to the checkpoint's
reference-duration limit. Prefer a short, clean recording of a single speaker.
Neither clone path consumes a transcript. No prompt cache is maintained by the adapter.

## Voice Directory

```text
voices/
  alice.wav
  alice.txt
  alice.yml       # optional metadata mapping
```

The top-level WAV and UTF-8 TXT must both be nonempty, even though this model ignores
the transcript. YAML is parsed safely, invalid metadata is ignored with a warning.
The list uses `file://alice`; preview uses `id=alice`. Files are rescanned for updates,
including metadata modification times. Paths outside the catalog and escaping
symlinks are not selectable. No voices or checkpoints are bundled in this adapter.

## Development

Upstream is an unmodified `engine` Git submodule pinned to
`96d9e0ec1e39083ed336ac78f24e3dbc93721c0f`. Python 3.12+, PyTorch/torchaudio 2.9.1 and
transformers 4.56–4.57.3 follow the upstream model package. The Dockerfile uses CUDA
12.8 and Ubuntu 24.04 for its system Python 3.12, with separate builder/runtime stages.
Only `engine/model` and the pinned FuseAlign package are installed, not the root uv
workspace. FuseAlign is a declared model-package dependency; no alignment or ASR
model is loaded by this adapter. No upstream files are patched.

```bash
git clone --recurse-submodules <your-adapter-repository>
cd zonos3-mini-open-tts
docker build -f docker/Dockerfile -t zonos3-mini-open-tts:local .
```

For an existing checkout, `git submodule update --init --recursive` populates source
submodules. GitHub Actions builds one linux/amd64 image on main pushes, `v*` tags or
manual dispatch; tags are latest, short SHA and version. It does not download model
weights. Docker and CI files are provided but have not been built or run; no dependency
installation, model download, service launch or inference validation was performed.
