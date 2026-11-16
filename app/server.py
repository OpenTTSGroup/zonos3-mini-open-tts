from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import anyio
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, Response

from .audio import encode
from .concurrency import ConcurrencyLimiter
from .config import get_settings
from .engine import TTSEngine, list_languages, normalize_language
from .schemas import (Capabilities, CloneRequest, GenerationOptions, HealthResponse,
                      Language, LanguagesResponse, SpeechRequest, VoiceInfo, VoiceListResponse)
from .voices import FILE_VOICE_PREFIX, Voice, VoiceCatalog

log = logging.getLogger(__name__)
CAPABILITIES = Capabilities(clone=True, streaming=False, design=False, languages=True, builtin_voices=False)
CLONE_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    app.state.settings = settings
    app.state.catalog = VoiceCatalog(settings.voices_path)
    app.state.limiter = ConcurrencyLimiter(settings.max_concurrency, settings.max_queue_size, settings.queue_timeout)
    app.state.engine = None

    async def initialize() -> None:
        try:
            app.state.engine = await anyio.to_thread.run_sync(TTSEngine, settings)
        except Exception:
            log.exception("ZONOS3 model loading failed; exiting")
            logging.shutdown()
            os._exit(1)

    task = asyncio.create_task(initialize())
    try:
        yield
    finally:
        # Model initialization cannot safely be interrupted halfway through a CUDA call.
        await task


app = FastAPI(title="zonos3-mini-open-tts", version="1.0.0", lifespan=lifespan)
if get_settings().cors_enabled:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _engine(request: Request) -> TTSEngine:
    if request.app.state.engine is None:
        raise HTTPException(503, "engine loading")
    return request.app.state.engine


def _validate_text(text: str, limit: int) -> None:
    if not text.strip():
        raise HTTPException(422, "input must not be empty")
    if len(text) > limit:
        raise HTTPException(413, f"input exceeds {limit} chars")


def _options(req: GenerationOptions, request: Request) -> dict:
    options = req.model_dump(include=set(GenerationOptions.model_fields), exclude_none=True)
    try:
        options["language"] = normalize_language(options.get("language", request.app.state.settings.zonos3_language))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return options


def _voice(name: str, request: Request) -> Voice:
    if not name.startswith(FILE_VOICE_PREFIX):
        if "://" in name:
            raise HTTPException(501, "remote voice URIs not supported")
        raise HTTPException(422, "voice must use 'file://' prefix for clone-only engines")
    voice = request.app.state.catalog.get(name)
    if voice is None:
        raise HTTPException(404, "voice not found")
    if voice.wav_path.stat().st_size > request.app.state.settings.max_audio_bytes:
        raise HTTPException(413, "reference audio exceeds MAX_AUDIO_BYTES")
    return voice


async def _render(job: Awaitable[np.ndarray], rate: int, fmt: str) -> Response:
    try:
        samples = await job
    except ValueError as exc:
        log.exception("reference or generation parameters rejected")
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("inference failed")
        raise HTTPException(500, "inference failed") from exc
    try:
        body, mime = await anyio.to_thread.run_sync(encode, samples, rate, fmt)
    except Exception as exc:
        log.exception("audio encoding failed")
        raise HTTPException(500, "audio encoding failed") from exc
    return Response(body, media_type=mime)


@app.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    engine = request.app.state.engine
    return HealthResponse(status="ok" if engine else "loading", model=request.app.state.settings.zonos3_model,
                          sample_rate=engine.sample_rate if engine else 0, capabilities=CAPABILITIES,
                          device=engine.device if engine else None, dtype=engine.dtype_str if engine else None,
                          concurrency=request.app.state.limiter.snapshot())


@app.get("/v1/audio/voices", response_model=VoiceListResponse)
async def voices(request: Request) -> VoiceListResponse:
    files = await anyio.to_thread.run_sync(request.app.state.catalog.list)
    return VoiceListResponse(voices=[VoiceInfo(id=v.uri,
        preview_url=f"/v1/audio/voices/preview?id={quote(v.id, safe='')}",
        prompt_text=v.prompt_text, metadata=v.metadata) for v in files])


@app.get("/v1/audio/voices/preview")
async def preview(id: str, request: Request) -> FileResponse:
    if id.startswith(FILE_VOICE_PREFIX):
        raise HTTPException(404, "preview id must be a plain voice name")
    voice = await anyio.to_thread.run_sync(request.app.state.catalog.get, id)
    if voice is None:
        raise HTTPException(404, "voice not found")
    return FileResponse(voice.wav_path, media_type="audio/wav", filename=f"{voice.id}.wav")


@app.get("/v1/audio/languages", response_model=LanguagesResponse)
async def languages() -> LanguagesResponse:
    return LanguagesResponse(languages=[Language(key=key, name=name) for key, name in list_languages()])


@app.post("/v1/audio/speech")
async def speech(req: SpeechRequest, request: Request) -> Response:
    settings = request.app.state.settings
    _validate_text(req.input, settings.max_input_chars)
    options = _options(req, request)
    voice = await anyio.to_thread.run_sync(_voice, req.voice, request)
    engine = _engine(request)
    async with request.app.state.limiter.acquire():
        return await _render(engine.synthesize_clone(req.input, ref_audio=str(voice.wav_path),
            ref_text=voice.prompt_text, ref_mtime=voice.mtime, speed=req.speed,
            instructions=req.instructions, **options), engine.sample_rate,
            req.response_format or settings.default_response_format)


@app.post("/v1/audio/clone")
async def clone(request: Request, req: CloneRequest = Depends()) -> Response:
    settings = request.app.state.settings
    tmp: Path | None = None
    try:
        if "prompt_text" not in await request.form():
            raise HTTPException(422, "prompt_text field is required (an empty string is allowed)")
        _validate_text(req.input, settings.max_input_chars)
        options = _options(req.options, request)
        suffix = Path(req.audio.filename or "reference.wav").suffix.lower()
        if suffix not in CLONE_AUDIO_EXTS:
            raise HTTPException(415, "unsupported reference audio format")
        engine = _engine(request)
        with tempfile.NamedTemporaryFile(prefix="zonos3-ref-", suffix=suffix, delete=False) as dest:
            tmp = Path(dest.name)
            size = 0
            while chunk := await req.audio.read(1 << 20):
                size += len(chunk)
                if size > settings.max_audio_bytes:
                    raise HTTPException(413, "reference audio exceeds MAX_AUDIO_BYTES")
                await anyio.to_thread.run_sync(dest.write, chunk)
        if size == 0:
            raise HTTPException(400, "audio file is empty")
        async with request.app.state.limiter.acquire():
            return await _render(engine.synthesize_clone(req.input, ref_audio=str(tmp), ref_text=req.prompt_text,
                speed=req.speed, instructions=req.instructions, **options), engine.sample_rate,
                req.response_format or settings.default_response_format)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        with anyio.CancelScope(shield=True):
            await req.audio.close()


def _openapi() -> dict:
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        body = schema["paths"]["/v1/audio/clone"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
        if "$ref" in body:
            body = schema["components"]["schemas"][body["$ref"].rsplit("/", 1)[-1]]
        required = body.setdefault("required", [])
        if "prompt_text" not in required:
            required.append("prompt_text")
        app.openapi_schema = schema
    return app.openapi_schema


# Match the handler's presence check while allowing an explicitly empty form value.
app.openapi = _openapi
