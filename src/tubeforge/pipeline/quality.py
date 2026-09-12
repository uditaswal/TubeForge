"""Local, deterministic publication quality gate for promoted video artifacts."""
from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from tubeforge.core.errors import ProviderValidationError


class QualityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: str = Field(pattern=r"^(error|warning)$")
    message: str


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    passed: bool
    findings: tuple[QualityFinding, ...]
    media: dict[str, object]


def validate_final_artifact(*, path: Path, expected_duration: float, renderer, captions_path: Path | None, captions_required: bool, minimum_width: int = 160, minimum_height: int = 90) -> QualityReport:
    """Re-probe final media and return durable hard/soft findings.

    Renderer validation already verifies duration, dimensions, codecs and usable
    audio streams. Repeating it here makes the final gate independently
    checkpointable and catches files modified after their render checkpoint.
    """
    findings: list[QualityFinding] = []
    if not path.is_file() or path.stat().st_size == 0:
        findings.append(QualityFinding(code="final_missing", severity="error", message="final video artifact is missing or empty"))
        return QualityReport(passed=False, findings=tuple(findings), media={})
    try:
        media = renderer.validate(path, expected_duration)
    except ProviderValidationError as error:
        findings.append(QualityFinding(code="media_probe_failed", severity="error", message=str(error)))
        return QualityReport(passed=False, findings=tuple(findings), media={})
    width, height = int(media.get("width", 0)), int(media.get("height", 0))
    if width < minimum_width or height < minimum_height:
        findings.append(QualityFinding(code="resolution_too_small", severity="error", message=f"final resolution {width}x{height} is below minimum {minimum_width}x{minimum_height}"))
    if captions_required and (captions_path is None or not captions_path.is_file() or captions_path.stat().st_size == 0):
        findings.append(QualityFinding(code="captions_missing", severity="error", message="captions were requested but no usable caption artifact exists"))
    if path.stat().st_size < 1_024:
        findings.append(QualityFinding(code="small_file", severity="warning", message="final media is unusually small; inspect it before publishing"))
    findings.append(QualityFinding(code="black_frame_detection_unavailable", severity="warning", message="black-frame analysis is not enabled in this local gate"))
    return QualityReport(passed=not any(item.severity == "error" for item in findings), findings=tuple(findings), media=media)
