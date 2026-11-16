from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    zonos3_model: str = Field(default="Zyphra/ZONOS3-Mini", description="HF repository, hf:// LM folder, or local LM directory.")
    zonos3_device: Literal["auto", "cuda", "cpu"] = Field(default="auto", description="Inference device.")
    zonos3_cuda_index: int = Field(default=0, ge=0, le=255, description="CUDA device index.")
    zonos3_dtype: Literal["auto", "bfloat16", "float32"] = Field(default="auto", description="LM dtype; auto uses BF16 on supported CUDA devices, FP32 otherwise.")
    zonos3_speaker_mode: Literal["auto", "reference", "embedding"] = Field(default="auto", description="Auto uses reference on CUDA and embedding on CPU.")
    zonos3_language: str = Field(default="en_us", description="Default native language code.")
    zonos3_pinyin_enabled: bool = Field(default=False, description="Convert bracketed pinyin only when the effective language is cmn.")
    zonos3_ipa_enabled: bool = Field(default=False, description="Convert {{IPA}} groups in all languages, preserving phonemes and tones.")
    zonos3_max_tokens: int = Field(default=2000, ge=1, le=8192, description="Maximum generated audio rows.")
    zonos3_text_rows: str | None = Field(default=None, description="Extra text rows path/URI; null selects release default, empty disables.")
    voices_dir: str = Field(default="/voices", description="Reference voice directory.")
    host: str = Field(default="0.0.0.0", description="Bind address.")
    port: int = Field(default=8000, ge=1, le=65535, description="HTTP port.")
    log_level: str = Field(default="info", description="Logging level.")
    max_input_chars: int = Field(default=8000, ge=1, le=1000000, description="Input text limit.")
    max_audio_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=1073741824, description="Reference upload limit.")
    default_response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = Field(default="mp3", description="Default audio format.")
    max_concurrency: int = Field(default=1, ge=1, le=1, description="Reference runtime shares mutable model state; one inference at a time.")
    max_queue_size: int = Field(default=0, ge=0, le=100000, description="Waiting requests; zero means unlimited.")
    queue_timeout: float = Field(default=0, ge=0, le=86400, description="Queue timeout seconds; zero means unlimited.")
    cors_enabled: bool = Field(default=False, description="Allow cross-origin requests.")

    @property
    def voices_path(self) -> Path:
        return Path(self.voices_dir)

    @property
    def resolved_device(self) -> str:
        import torch
        if self.zonos3_device == "cpu":
            return "cpu"
        if self.zonos3_device == "auto" and not torch.cuda.is_available():
            return "cpu"
        return f"cuda:{self.zonos3_cuda_index}"

    @property
    def model_location(self) -> str:
        value = self.zonos3_model
        if value.startswith("hf://") or Path(value).exists() or value.startswith(("/", ".", "~")) or ":" in value:
            return value
        if value.count("/") == 1:
            return f"hf://{value}/lm/zonos3_mini"
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
