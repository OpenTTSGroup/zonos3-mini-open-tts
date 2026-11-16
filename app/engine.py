from __future__ import annotations

import base64
import logging
from functools import partial
from pathlib import Path

import anyio
import numpy as np

from .config import Settings
from .ipa import convert_ipa
from .pinyin import convert_pinyin

log = logging.getLogger(__name__)


def list_languages() -> list[tuple[str, str]]:
    from zonos3.languages import SERVER
    return [(lang.code, lang.label) for lang in SERVER]


def normalize_language(value: str) -> str:
    from zonos3.languages import normalize
    return normalize(value)


class TTSEngine:
    def prepare_text(self, text: str, *, language: str) -> str:
        spec = self.model.config.text_tokenizer_spec or {}
        symbols = (spec.get("phonemes") or {}).get("symbols")
        # Convert explicit IPA first; the pinyin pass skips Unicode IPA groups.
        text = convert_ipa(text, enabled=self.settings.zonos3_ipa_enabled, symbols=symbols)
        return convert_pinyin(text, enabled=self.settings.zonos3_pinyin_enabled,
                              language=language, symbols=symbols)

    def __init__(self, settings: Settings) -> None:
        import torch
        from zonos3.generation import SAMPLE_RATE
        from zonos3.models.text_extra import TextExtraRows
        from zonos3.reference.lm import Zonos3LM
        from zonos3.reference.synth import ReferenceAssets
        from zonos3.utils import release

        self.settings = settings
        self.device = settings.resolved_device
        device = torch.device(self.device)
        if device.type == "cuda":
            torch.cuda.set_device(device)
        self.dtype_str = settings.zonos3_dtype
        if self.dtype_str == "auto":
            self.dtype_str = "bfloat16" if device.type == "cuda" and torch.cuda.is_bf16_supported() else "float32"
        if device.type == "cpu":
            self.dtype_str = "float32"
        self.dtype = getattr(torch, self.dtype_str)
        self.speaker_mode = settings.zonos3_speaker_mode
        if self.speaker_mode == "auto":
            self.speaker_mode = "reference" if device.type == "cuda" else "embedding"
        if self.speaker_mode == "reference" and device.type != "cuda":
            raise ValueError("ZONOS3_SPEAKER_MODE=reference requires CUDA; use embedding on CPU")
        normalize_language(settings.zonos3_language)
        self.sample_rate = SAMPLE_RATE
        self.model = Zonos3LM.load(settings.model_location, device=device, dtype=self.dtype).eval()
        self.assets = ReferenceAssets.load()
        self.assets.grow(self.model)
        rows = settings.zonos3_text_rows
        if rows is None and settings.model_location == release.RELEASE_LM:
            rows = release.RELEASE_TEXT_ROWS
        if rows:
            self.model.append_text_rows(TextExtraRows.load(rows))
        config = self.model.config
        if self.speaker_mode == "reference" and not config.speaker_reference_prefix_enabled:
            raise ValueError("checkpoint does not support reference-prefix cloning")
        # Eagerly load companions so healthz does not report ready before downloads finish.
        self.assets.decoder(config.audio_codec, device)
        self.assets.normalizer()
        if self.speaker_mode == "reference":
            from zonos3.tokenizer.dual_reference import get_encoder
            get_encoder(self.device)
        else:
            self.assets.speaker_encoder(config.speaker_embedding_codec, config.speaker_embedding_dim, device)
        log.info("ZONOS3 reference ready: device=%s dtype=%s speaker_mode=%s", self.device, self.dtype_str, self.speaker_mode)

    def _synthesize(self, text: str, ref_audio: str, options: dict) -> np.ndarray:
        import torch
        from zonos3.reference.synth import synthesize

        request = {key: value for key, value in options.items() if value is not None}
        if "top_k" in request:
            request["topk"] = request.pop("top_k")
        request.setdefault("language", self.settings.zonos3_language)
        request.setdefault("max_tokens", self.settings.zonos3_max_tokens)
        request.update(text=text, stream=False, stream_decode="whole", speaker_mode=self.speaker_mode,
                       speaker_audio_base64=base64.b64encode(Path(ref_audio).read_bytes()).decode("ascii"),
                       speaker_audio_name=Path(ref_audio).name)
        # CUDA's current device and inference_mode are thread-local.
        if self.device.startswith("cuda"):
            torch.cuda.set_device(torch.device(self.device))
        with torch.inference_mode():
            result = synthesize(self.model, request, assets=self.assets,
                                device=self.device, dtype=self.dtype)
        pcm = np.asarray(result.pcm, dtype=np.float32).reshape(-1)
        if not pcm.size or not np.isfinite(pcm).all():
            raise RuntimeError("model returned empty or non-finite audio")
        return np.clip(pcm, -1, 1)

    async def synthesize_clone(
        self, text: str, *, ref_audio: str, ref_text: str, ref_mtime: float | None = None,
        instructions: str | None = None, speed: float = 1.0, **engine_specific,
    ) -> np.ndarray:
        # Do not abandon the worker on disconnect: the gate and reference file must
        # stay alive until the shared model finishes using them.
        return await anyio.to_thread.run_sync(partial(self._synthesize, text, ref_audio, engine_specific),
                                             abandon_on_cancel=False)
