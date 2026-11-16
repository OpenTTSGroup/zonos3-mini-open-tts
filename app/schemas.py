from __future__ import annotations

from typing import Annotated, Literal

from fastapi import File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field

ResponseFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]


class Capabilities(BaseModel):
    clone: bool = Field(description="Reference voice cloning.")
    streaming: bool = Field(description="Incremental audio endpoint.")
    design: bool = Field(description="Natural-language voice design.")
    languages: bool = Field(description="Language discovery.")
    builtin_voices: bool = Field(description="Built-in voice identifiers.")


class ConcurrencySnapshot(BaseModel):
    max: int = Field(ge=1, description="Maximum active requests.")
    active: int = Field(ge=0, description="Active requests.")
    queued: int = Field(ge=0, description="Waiting requests.")


class HealthResponse(BaseModel):
    status: Literal["loading", "ok"] = Field(description="Model loading status.")
    model: str = Field(description="Configured model.")
    sample_rate: int = Field(ge=0, description="Output sample rate; zero while loading.")
    capabilities: Capabilities = Field(description="Adapter capabilities.")
    device: str | None = Field(default=None, description="Actual device.")
    dtype: str | None = Field(default=None, description="LM dtype.")
    concurrency: ConcurrencySnapshot = Field(description="Concurrency counters.")


class VoiceInfo(BaseModel):
    id: str = Field(description="file:// voice identifier.")
    preview_url: str | None = Field(default=None, description="WAV preview URL.")
    prompt_text: str | None = Field(default=None, description="Reference transcript.")
    metadata: dict | None = Field(default=None, description="Optional YAML metadata.")


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfo] = Field(description="Available voices.")


class Language(BaseModel):
    key: str = Field(description="Native language code.")
    name: str = Field(description="Language display name.")


class LanguagesResponse(BaseModel):
    languages: list[Language] = Field(description="Supported languages.")


class GenerationOptions(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    language: str | None = Field(default=None, description="Native code; defaults to ZONOS3_LANGUAGE.")
    seed: int | None = Field(default=None, ge=0, le=2147483647, description="Sampling seed; null chooses randomly.")
    temperature: float | None = Field(default=None, ge=0, le=5, description="Sampling temperature; upstream default 0.75.")
    top_k: int | None = Field(default=None, ge=1, le=4096, description="Top-k sampling; upstream default 80.")
    top_p: float | None = Field(default=None, gt=0, le=1, description="Nucleus probability; upstream default 0.69.")
    max_tokens: int | None = Field(default=None, ge=1, le=8192, description="Audio-row budget, further bounded by model context.")


class SpeechRequest(GenerationOptions):
    model: str | None = Field(default=None, description="Accepted for OpenAI compatibility; ignored.")
    input: str = Field(description="Text to synthesize.")
    voice: str = Field(description="Reference voice: file://name.")
    response_format: ResponseFormat | None = Field(default=None, description="Audio format; service default mp3.")
    speed: float = Field(default=1.0, ge=0.25, le=4, description="Accepted but ignored.")
    instructions: str | None = Field(default=None, description="Accepted but ignored.")


class CloneRequest:
    def __init__(
        self,
        audio: Annotated[UploadFile, File(description="Reference audio.")],
        input: Annotated[str, Form(description="Text to synthesize.")],
        # FastAPI treats empty form strings as missing. Presence is checked in
        # the handler so an explicitly supplied empty transcript remains valid.
        prompt_text: Annotated[str, Form(description="Required transcript field; empty accepted, content ignored.")] = "",
        model: Annotated[str | None, Form(description="Accepted for OpenAI compatibility; ignored.")] = None,
        response_format: Annotated[ResponseFormat | None, Form(description="Output format; default mp3.")] = None,
        speed: Annotated[float, Form(ge=0.25, le=4, allow_inf_nan=False, description="Accepted but ignored.")] = 1.0,
        instructions: Annotated[str | None, Form(description="Accepted but ignored.")] = None,
        language: Annotated[str | None, Form(description="Native language code.")] = None,
        seed: Annotated[int | None, Form(ge=0, le=2147483647, description="Sampling seed.")] = None,
        temperature: Annotated[float | None, Form(ge=0, le=5, allow_inf_nan=False, description="Sampling temperature.")] = None,
        top_k: Annotated[int | None, Form(ge=1, le=4096, description="Top-k sampling.")] = None,
        top_p: Annotated[float | None, Form(gt=0, le=1, allow_inf_nan=False, description="Nucleus probability.")] = None,
        max_tokens: Annotated[int | None, Form(ge=1, le=8192, description="Audio-row budget.")] = None,
    ) -> None:
        self.audio, self.input, self.prompt_text = audio, input, prompt_text
        self.response_format, self.speed, self.instructions = response_format, speed, instructions
        self.options = GenerationOptions(language=language, seed=seed, temperature=temperature,
                                         top_k=top_k, top_p=top_p, max_tokens=max_tokens)
