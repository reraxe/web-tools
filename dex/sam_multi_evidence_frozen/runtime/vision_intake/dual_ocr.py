"""Independent, localized OCR observations for shadow-only SAM research.

This module deliberately separates observation from interpretation.  Tesseract
and PaddleOCR each preserve their own raw text, word boxes, confidence, runtime
identity, and latency.  Agreement can nominate a catalog family, but it never
creates identity authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Iterable, Sequence
import uuid

import cv2
import numpy as np

from .catalog_constrained_ocr import LocalFamilyCatalog
from .sleeved_foil_ocr import normalize_footer_tokens


PIPELINE_VERSION = "sam-dual-localized-ocr-shadow-v1"
TESSERACT_PREPROCESSING_VERSION = "localized-gray-bicubic-border-v1"
RAPIDOCR_PREPROCESSING_VERSION = "localized-bgr-original-v1"
MAX_CARD_NUMBER_CANDIDATES = 8
MAX_RECONSTRUCTION_TOKENS = 3
MIN_TOKEN_CONFIDENCE = 0.35
MAX_GAP_HEIGHT_RATIO = 1.60
MIN_VERTICAL_OVERLAP = 0.35


@dataclass(frozen=True)
class TokenBox:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    source_polygon: tuple[tuple[float, float], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(float(self.confidence), 6),
            "polygon": [list(point) for point in self.polygon],
            "source_polygon": [list(point) for point in self.source_polygon],
        }


@dataclass(frozen=True)
class OcrObservation:
    attempt_id: str
    engine: str
    engine_version: str
    model_version: str
    source_path: str
    source_sha256: str
    region_name: str
    region_pixels: tuple[int, int, int, int]
    preprocessing_version: str
    raw_text: str
    tokens: tuple[TokenBox, ...]
    confidence: float
    observed_at: str
    latency_ms: float
    runtime_provider: str
    error_code: str = ""

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tokens"] = [token.as_dict() for token in self.tokens]
        value["region_pixels"] = list(self.region_pixels)
        return value


@dataclass(frozen=True)
class CandidatePath:
    card_number: str
    engine: str
    attempt_id: str
    token_indexes: tuple[int, ...]
    observed_text: str
    confidence: float
    reconstruction: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["token_indexes"] = list(self.token_indexes)
        return value


@dataclass(frozen=True)
class DualOcrResult:
    pipeline_version: str
    source_sha256: str
    observations: tuple[OcrObservation, ...]
    candidate_paths: tuple[CandidatePath, ...]
    candidates: tuple[str, ...]
    exact_engine_agreement: str
    engine_conflict: bool
    state: str
    early_exit_reason: str
    latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "source_sha256": self.source_sha256,
            "observations": [item.as_dict() for item in self.observations],
            "candidate_paths": [item.as_dict() for item in self.candidate_paths],
            "candidates": list(self.candidates),
            "exact_engine_agreement": self.exact_engine_agreement or None,
            "engine_conflict": self.engine_conflict,
            "state": self.state,
            "early_exit_reason": self.early_exit_reason or None,
            "latency_ms": round(self.latency_ms, 4),
            "authority": {
                "trusted_ocr_granted": False,
                "identity_authority_granted": False,
                "printing_authority_granted": False,
            },
        }

    def as_frozen_sam_evidence(self) -> dict[str, Any]:
        """Expose observations in the legacy debug-attempt shape, never as trust."""

        attempts = []
        for sequence, observation in enumerate(self.observations, start=1):
            attempts.append({
                "sequence": sequence,
                "raw": observation.raw_text,
                "confidence": observation.confidence,
                "region_name": observation.region_name,
                "region": list(observation.region_pixels),
                "preprocessing": observation.preprocessing_version,
                "psm": None,
                "engine": observation.engine,
                "engine_version": observation.engine_version,
                "model_version": observation.model_version,
                "attempt_id": observation.attempt_id,
                "token_boxes": [token.as_dict() for token in observation.tokens],
            })
        return {
            "raw": "",
            "normalized": "",
            "candidate_normalized": self.exact_engine_agreement,
            "confidence": 0.0,
            "source": "OCR_NO_TRUSTED_CONSENSUS",
            "method_version": self.pipeline_version,
            "shadow_only": True,
            "identity_authority": False,
            "debug_attempts": attempts,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_tesseract() -> str:
    configured = os.environ.get("DEX_TESSERACT_CMD", "").strip()
    candidates = [configured, shutil.which("tesseract") or ""]
    if os.name == "nt":
        candidates.extend([
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return ""


def _ordered_portrait(image: np.ndarray) -> tuple[np.ndarray, str]:
    if image.shape[1] <= image.shape[0]:
        return image, "SOURCE_PORTRAIT"
    return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), "ROTATE_90_CLOCKWISE"


def _region_pixels(image: np.ndarray, fractions: Sequence[float]) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = fractions
    return (int(width * x1), int(height * y1), int(width * x2), int(height * y2))


def _crop(image: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = region
    return image[y1:y2, x1:x2]


def _rect_polygon(left: float, top: float, width: float, height: float) -> tuple[tuple[float, float], ...]:
    return ((left, top), (left + width, top), (left + width, top + height), (left, top + height))


def _to_source_polygon(
    polygon: Sequence[Sequence[float]], region: tuple[int, int, int, int], *, scale: float = 1.0,
    border: float = 0.0,
) -> tuple[tuple[float, float], ...]:
    x1, y1, _x2, _y2 = region
    return tuple(
        (round(x1 + (float(point[0]) - border) / scale, 3), round(y1 + (float(point[1]) - border) / scale, 3))
        for point in polygon
    )


def _tesseract_observation(
    command: str,
    image: np.ndarray,
    source: Path,
    source_hash: str,
    region_name: str,
    region: tuple[int, int, int, int],
    *,
    psm: int,
    whitelist: str | None,
    sequence: int,
) -> OcrObservation:
    started = time.perf_counter()
    crop = _crop(image, region)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scale = max(2.0, min(3.5, 1050.0 / max(1, gray.shape[1])))
    prepared = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    border = 14
    prepared = cv2.copyMakeBorder(prepared, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
    args = [command, "", "stdout", "-l", "eng", "--oem", "1", "--psm", str(psm)]
    if whitelist:
        args.extend(["-c", f"tessedit_char_whitelist={whitelist}", "-c", "load_system_dawg=0", "-c", "load_freq_dawg=0"])
    args.append("tsv")
    error_code = ""
    raw_text = ""
    tokens: list[TokenBox] = []
    with tempfile.TemporaryDirectory(prefix="dex-dual-ocr-") as temp_dir:
        prepared_path = Path(temp_dir) / "region.png"
        if not cv2.imwrite(str(prepared_path), prepared):
            error_code = "PREPARED_IMAGE_WRITE_FAILED"
            completed = None
        else:
            args[1] = str(prepared_path)
            try:
                completed = subprocess.run(
                    args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=10, check=False,
                )
            except (OSError, subprocess.SubprocessError) as error:
                completed = None
                error_code = f"TESSERACT_{type(error).__name__.upper()}"
        if completed is not None:
            if completed.returncode != 0:
                error_code = f"TESSERACT_EXIT_{completed.returncode}"
            else:
                words: list[str] = []
                for line in completed.stdout.splitlines()[1:]:
                    fields = line.split("\t", 11)
                    if len(fields) != 12 or not fields[11].strip():
                        continue
                    text = fields[11].strip()
                    try:
                        confidence = max(0.0, float(fields[10]) / 100.0)
                        left, top, width, height = (float(fields[index]) for index in (6, 7, 8, 9))
                    except ValueError:
                        continue
                    polygon = _rect_polygon(left, top, width, height)
                    tokens.append(TokenBox(
                        text=text,
                        confidence=confidence,
                        polygon=polygon,
                        source_polygon=_to_source_polygon(polygon, region, scale=scale, border=border),
                    ))
                    words.append(text)
                raw_text = " ".join(words)[:1000]
    confidence = sum(token.confidence for token in tokens) / len(tokens) if tokens else 0.0
    return OcrObservation(
        attempt_id=f"TESSERACT-{sequence:02d}-{uuid.uuid4().hex[:10].upper()}",
        engine="TESSERACT",
        engine_version=subprocess.run([command, "--version"], capture_output=True, text=True, check=False).stdout.splitlines()[0],
        model_version="eng-traineddata-local",
        source_path=str(source),
        source_sha256=source_hash,
        region_name=region_name,
        region_pixels=region,
        preprocessing_version=f"{TESSERACT_PREPROCESSING_VERSION}:PSM-{psm}",
        raw_text=raw_text,
        tokens=tuple(tokens),
        confidence=confidence,
        observed_at=datetime.now(timezone.utc).isoformat(),
        latency_ms=(time.perf_counter() - started) * 1000,
        runtime_provider="LOCAL_CPU_SUBPROCESS",
        error_code=error_code,
    )


def _rapidocr_observation(
    engine: Any,
    image: np.ndarray,
    source: Path,
    source_hash: str,
    region_name: str,
    region: tuple[int, int, int, int],
    *,
    sequence: int,
    model_version: str,
) -> OcrObservation:
    import importlib.metadata

    started = time.perf_counter()
    crop = _crop(image, region)
    error_code = ""
    tokens: list[TokenBox] = []
    try:
        output = engine(crop)
    except Exception as error:  # The observation persists a safe code; source text is never exposed.
        output = None
        error_code = f"RAPIDOCR_{type(error).__name__.upper()}"
    boxes_raw = getattr(output, "boxes", None)
    texts_raw = getattr(output, "txts", None)
    scores_raw = getattr(output, "scores", None)
    boxes = list(boxes_raw) if boxes_raw is not None else []
    texts = list(texts_raw) if texts_raw is not None else []
    scores = list(scores_raw) if scores_raw is not None else []
    for polygon_raw, text_raw, score_raw in zip(boxes, texts, scores):
        try:
            polygon = tuple((float(point[0]), float(point[1])) for point in polygon_raw)
            text = str(text_raw).strip()
            confidence = float(score_raw)
        except (TypeError, ValueError, IndexError):
            continue
        if text:
            tokens.append(TokenBox(
                text=text,
                confidence=confidence,
                polygon=polygon,
                source_polygon=_to_source_polygon(polygon, region),
            ))
    tokens.sort(key=lambda token: (min(point[1] for point in token.polygon), min(point[0] for point in token.polygon)))
    raw_text = " ".join(token.text for token in tokens)[:1000]
    confidence = sum(token.confidence for token in tokens) / len(tokens) if tokens else 0.0
    return OcrObservation(
        attempt_id=f"RAPIDOCR-{sequence:02d}-{uuid.uuid4().hex[:10].upper()}",
        engine="RAPIDOCR_ONNX",
        engine_version=f"rapidocr-{importlib.metadata.version('rapidocr')}",
        model_version=model_version,
        source_path=str(source),
        source_sha256=source_hash,
        region_name=region_name,
        region_pixels=region,
        preprocessing_version=RAPIDOCR_PREPROCESSING_VERSION,
        raw_text=raw_text,
        tokens=tuple(tokens),
        confidence=confidence,
        observed_at=datetime.now(timezone.utc).isoformat(),
        latency_ms=(time.perf_counter() - started) * 1000,
        runtime_provider="ONNXRUNTIME_CPU_EXECUTION_PROVIDER",
        error_code=error_code,
    )


def _bounds(token: TokenBox) -> tuple[float, float, float, float]:
    xs = [point[0] for point in token.source_polygon]
    ys = [point[1] for point in token.source_polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _spatially_compatible(left: TokenBox, right: TokenBox) -> bool:
    lx1, ly1, lx2, ly2 = _bounds(left)
    rx1, ry1, rx2, ry2 = _bounds(right)
    left_height = max(1.0, ly2 - ly1)
    right_height = max(1.0, ry2 - ry1)
    vertical_overlap = max(0.0, min(ly2, ry2) - max(ly1, ry1)) / min(left_height, right_height)
    gap = rx1 - lx2
    median_height = (left_height + right_height) / 2.0
    return rx1 >= lx1 and gap <= MAX_GAP_HEIGHT_RATIO * median_height and gap >= -0.45 * median_height and vertical_overlap >= MIN_VERTICAL_OVERLAP


def candidate_paths(observation: OcrObservation, catalog: LocalFamilyCatalog) -> list[CandidatePath]:
    """Interpret only catalog-valid identifiers assembled from adjacent boxes."""

    output: dict[tuple[str, tuple[int, ...]], CandidatePath] = {}
    tokens = list(observation.tokens)
    for start in range(len(tokens)):
        for width in range(1, min(MAX_RECONSTRUCTION_TOKENS, len(tokens) - start) + 1):
            selected = tokens[start:start + width]
            if any(token.confidence < MIN_TOKEN_CONFIDENCE for token in selected):
                continue
            if any(not _spatially_compatible(selected[index], selected[index + 1]) for index in range(len(selected) - 1)):
                continue
            variants = [" ".join(token.text for token in selected), "".join(token.text for token in selected)]
            for value in variants:
                normalized = normalize_footer_tokens(value)
                if normalized is None or normalized.card_number not in catalog.families:
                    continue
                indexes = tuple(range(start, start + width))
                confidence = min(token.confidence for token in selected)
                path = CandidatePath(
                    card_number=normalized.card_number,
                    engine=observation.engine,
                    attempt_id=observation.attempt_id,
                    token_indexes=indexes,
                    observed_text=value,
                    confidence=confidence,
                    reconstruction="SINGLE_BOX" if width == 1 else "ADJACENT_SPATIAL_BOXES",
                )
                output[(path.card_number, indexes)] = path
    return sorted(output.values(), key=lambda item: (-item.confidence, item.card_number, item.token_indexes))


class DualLocalizedOcr:
    """Local two-engine OCR with staged footer-first execution."""

    REGIONS = {
        "FOOTER_NUMBER_TIGHT": (0.66, 0.895, 0.998, 0.998),
        "FOOTER_SEARCH": (0.50, 0.835, 0.998, 0.998),
        "CARD_NAME": (0.08, 0.72, 0.94, 0.94),
    }

    def __init__(
        self,
        catalog: LocalFamilyCatalog,
        *,
        tesseract_command: str | None = None,
        rapidocr_engine: Any | None = None,
    ) -> None:
        self.catalog = catalog
        self.tesseract_command = tesseract_command or _find_tesseract()
        if not self.tesseract_command:
            raise RuntimeError("Tesseract OCR runtime is unavailable")
        self._rapidocr_engine = rapidocr_engine
        self.rapidocr_model_version = "PP-OCRv6_det_small+PP-OCRv6_rec_small"

    @property
    def rapidocr_model_root(self) -> Path:
        import rapidocr

        return Path(rapidocr.__file__).resolve().parent / "models"

    def _get_rapidocr_engine(self) -> Any:
        if self._rapidocr_engine is None:
            from rapidocr import RapidOCR

            self._rapidocr_engine = RapidOCR()
            providers = self._rapidocr_engine.text_det.session.session.get_providers()
            if providers != ["CPUExecutionProvider"]:
                raise RuntimeError(f"Unexpected RapidOCR provider set: {providers}")
        return self._rapidocr_engine

    def analyze(self, source_path: Path) -> DualOcrResult:
        started = time.perf_counter()
        source = source_path.resolve()
        source_hash = _sha256(source)
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Image cannot be decoded")
        image, orientation = _ordered_portrait(image)
        tight = _region_pixels(image, self.REGIONS["FOOTER_NUMBER_TIGHT"])
        search = _region_pixels(image, self.REGIONS["FOOTER_SEARCH"])
        observations: list[OcrObservation] = []
        observations.append(_tesseract_observation(
            self.tesseract_command, image, source, source_hash,
            f"{orientation}:FOOTER_NUMBER_TIGHT", tight,
            psm=7, whitelist=None, sequence=1,
        ))
        if not candidate_paths(observations[-1], self.catalog):
            observations.append(_tesseract_observation(
                self.tesseract_command, image, source, source_hash,
                f"{orientation}:FOOTER_SEARCH", search,
                psm=11, whitelist=None, sequence=2,
            ))
        observations.append(_rapidocr_observation(
            self._get_rapidocr_engine(), image, source, source_hash,
            f"{orientation}:FOOTER_SEARCH", search,
            sequence=1, model_version=self.rapidocr_model_version,
        ))
        paths = [path for observation in observations for path in candidate_paths(observation, self.catalog)]
        by_engine: dict[str, set[str]] = {}
        for path in paths:
            by_engine.setdefault(path.engine, set()).add(path.card_number)
        agreement = sorted(set.intersection(*by_engine.values())) if len(by_engine) >= 2 else []
        engine_union = set().union(*by_engine.values()) if by_engine else set()
        engine_conflict = len(by_engine) >= 2 and not agreement and all(by_engine.values())
        if len(agreement) == 1:
            state = "CORROBORATED_CANDIDATE"
            candidates = agreement
            early_exit = "INDEPENDENT_ENGINES_AGREE_ON_EXACT_CATALOG_FAMILY"
        elif engine_conflict:
            state = "CONFLICT"
            candidates = []
            early_exit = ""
        elif 0 < len(engine_union) <= MAX_CARD_NUMBER_CANDIDATES:
            state = "CANDIDATE_ONLY"
            candidates = sorted(engine_union)
            early_exit = ""
        elif len(engine_union) > MAX_CARD_NUMBER_CANDIDATES:
            state = "AMBIGUOUS"
            candidates = []
            early_exit = ""
        else:
            state = "UNRESOLVED"
            candidates = []
            early_exit = ""
        return DualOcrResult(
            pipeline_version=PIPELINE_VERSION,
            source_sha256=source_hash,
            observations=tuple(observations),
            candidate_paths=tuple(paths),
            candidates=tuple(candidates),
            exact_engine_agreement=agreement[0] if len(agreement) == 1 else "",
            engine_conflict=engine_conflict,
            state=state,
            early_exit_reason=early_exit,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def analyze_names(self, source_path: Path) -> tuple[OcrObservation, ...]:
        """Run the later-stage name field only when footer evidence is insufficient."""

        source = source_path.resolve()
        source_hash = _sha256(source)
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Image cannot be decoded")
        image, orientation = _ordered_portrait(image)
        region = _region_pixels(image, self.REGIONS["CARD_NAME"])
        return (
            _tesseract_observation(
                self.tesseract_command, image, source, source_hash,
                f"{orientation}:CARD_NAME", region, psm=11, whitelist=None, sequence=10,
            ),
            _rapidocr_observation(
                self._get_rapidocr_engine(), image, source, source_hash,
                f"{orientation}:CARD_NAME", region, sequence=10, model_version=self.rapidocr_model_version,
            ),
        )


def engine_runtime_manifest(extractor: DualLocalizedOcr) -> dict[str, Any]:
    """Return executable/model identities without running recognition."""

    import importlib.metadata

    return {
        "pipeline_version": PIPELINE_VERSION,
        "tesseract": subprocess.run(
            [extractor.tesseract_command, "--version"], capture_output=True, text=True, check=False
        ).stdout.splitlines()[0],
        "rapidocr": importlib.metadata.version("rapidocr"),
        "onnxruntime": importlib.metadata.version("onnxruntime-gpu"),
        "rapidocr_provider": "CPUExecutionProvider",
        "rapidocr_model_version": extractor.rapidocr_model_version,
    }
