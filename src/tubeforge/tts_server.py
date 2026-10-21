"""Private local Piper synthesis API for trusted local application processes."""

from __future__ import annotations

import hashlib
import io
import threading
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from tubeforge.core.config import PiperProviderConfig, REPOSITORY_ROOT, load_settings


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=12_000)
    speaker_id: int | None = Field(default=None, ge=0, le=10_000)


def _path(value: Path | str | None) -> Path:
    assert value is not None
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def create_tts_app(
    settings: PiperProviderConfig | None = None,
    *,
    voice_loader: Any | None = None,
) -> FastAPI:
    """Create a tiny non-download-capable API; tests can inject a local voice."""
    selected = settings or load_settings().pipeline.piper
    gate = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        model_path = _path(selected.model_path)
        if not model_path.is_file():
            raise RuntimeError("configured Piper model file is unavailable")
        config_path = _path(selected.config_path) if selected.config_path else None
        if config_path is not None and not config_path.is_file():
            raise RuntimeError("configured Piper model sidecar is unavailable")
        if voice_loader is None:
            from piper import PiperVoice
            loaded = PiperVoice.load(model_path, config_path=config_path)
        else:
            loaded = voice_loader(model_path, config_path)
        app.state.voice = loaded
        app.state.voice_id = selected.voice_id
        app.state.model_sha256 = _sha256(model_path)
        app.state.max_output_bytes = selected.max_output_bytes
        app.state.speaker = selected.speaker
        app.state.gate = gate
        yield

    app = FastAPI(title="TubeForge local Piper", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/healthz")
    def health(request: Request) -> dict[str, object]:
        if not hasattr(request.app.state, "voice"):
            raise HTTPException(status_code=503, detail="Piper model is not ready")
        return {"status": "ok", "voice_id": request.app.state.voice_id, "model_sha256": request.app.state.model_sha256}

    @app.post("/synthesize", response_class=Response)
    def synthesize(body: SynthesisRequest, request: Request) -> Response:
        text = " ".join(body.text.split())
        if not text:
            raise HTTPException(status_code=422, detail="text is empty")
        speaker_id = body.speaker_id if body.speaker_id is not None else request.app.state.speaker
        voice = request.app.state.voice
        try:
            from piper.config import SynthesisConfig
            syn_config = SynthesisConfig(speaker_id=speaker_id)
            with request.app.state.gate:
                output = io.BytesIO()
                with wave.open(output, "wb") as wav:
                    params_set = False
                    for chunk in voice.synthesize(text, syn_config=syn_config):
                        if not params_set:
                            wav.setframerate(chunk.sample_rate)
                            wav.setsampwidth(chunk.sample_width)
                            wav.setnchannels(chunk.sample_channels)
                            params_set = True
                        wav.writeframes(chunk.audio_int16_bytes)
                        if output.tell() > request.app.state.max_output_bytes:
                            raise HTTPException(status_code=413, detail="audio result exceeds configured size limit")
                audio = output.getvalue()
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=503, detail="local Piper synthesis failed") from error
        return Response(audio, media_type="audio/wav", headers={"X-Piper-Voice": request.app.state.voice_id, "X-Piper-Model-SHA256": request.app.state.model_sha256})

    return app


def main() -> None:
    import uvicorn
    settings = load_settings()
    app = create_tts_app(settings.pipeline.piper)
    uvicorn.run(
        app,
        host=settings.pipeline.piper.listen_host,
        port=settings.pipeline.piper.listen_port,
        access_log=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
