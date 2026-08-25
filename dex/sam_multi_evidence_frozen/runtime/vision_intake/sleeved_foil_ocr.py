"""Shadow-only One Piece footer OCR for penny-sleeved foil captures.

The challenger produces non-authoritative card-number evidence for a frozen SAM
benchmark.  It never writes inventory facts and never applies identity.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


CHALLENGER_VERSION = "sleeved-foil-ocr-intake-shadow-v1"
OCR_MIN_CONFIDENCE = 0.67
OCR_TIMEOUT_SECONDS = 8.0
CARD_NUMBER_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?P<family>(?:[O0]P|EB|ST|PRB))\s*"
    r"(?P<set>[0-9OIL](?:\s?[0-9OIL]){0,2})\s*[-_]\s*"
    r"(?P<number>[0-9OIL](?:\s?[0-9OIL]){2})(?![A-Z0-9])",
    re.IGNORECASE,
)
PROMO_PATTERN = re.compile(
    r"(?<![A-Z0-9])P\s*[-_]\s*(?P<number>[0-9OIL](?:\s?[0-9OIL]){2})(?![A-Z0-9])",
    re.IGNORECASE,
)
COMPACT_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?P<family>(?:[O0]P|EB|ST|PRB))"
    r"(?P<digits>[0-9OIL]{4,6})(?![A-Z0-9])",
    re.IGNORECASE,
)
NUMERIC_TRANSLATION = str.maketrans({"O": "0", "I": "1", "L": "1"})


@dataclass(frozen=True)
class NormalizedToken:
    card_number: str
    corrections: tuple[str, ...]
    source_span: str


@dataclass(frozen=True)
class OcrAttempt:
    sequence: int
    branch: str
    region_name: str
    region_pixels: tuple[int, int, int, int]
    preprocessing: str
    selected_channel: str
    page_segmentation_mode: int
    raw_text: str
    normalized: str
    normalization_corrections: tuple[str, ...]
    engine_word_confidence: float
    preprocessing_ms: float
    execution_ms: float
    error_code: str


@dataclass(frozen=True)
class SleevedFoilOcrResult:
    challenger_version: str
    mode: str
    source_sha256: str
    normalized: str
    candidate_normalized: str
    confidence: float
    candidate_confidence: float
    source: str
    trustworthy: bool
    consensus_support_branches: int
    valid_candidate_branches: int
    conflicting_consensus: bool
    incorrect_authority_possible: bool
    attempts_run: int
    attempts_available: int
    early_exit_reason: str
    preprocessing_ms: float
    execution_ms: float
    wall_ms: float
    peak_python_memory_bytes: int | None
    runtime: dict[str, Any]
    debug_attempts: tuple[OcrAttempt, ...]

    def as_evidence(self) -> dict[str, Any]:
        """Return the frozen Challenger-compatible, non-authoritative evidence."""

        return {
            "raw": next(
                (item.raw_text for item in self.debug_attempts if item.normalized == self.candidate_normalized),
                "",
            ),
            "normalized": self.normalized,
            "candidate_normalized": self.candidate_normalized,
            "confidence": self.confidence,
            "candidate_confidence": self.candidate_confidence,
            "source": self.source,
            "method_version": self.challenger_version,
            "preprocessing_ms": self.preprocessing_ms,
            "execution_ms": self.execution_ms,
            "consensus_support": self.consensus_support_branches,
            "valid_candidate_attempts": self.valid_candidate_branches,
            "runtime": self.runtime,
            "shadow_only": True,
            "identity_authority": False,
            "debug_attempts": [asdict(item) for item in self.debug_attempts],
        }


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_tesseract() -> str:
    configured = os.environ.get("DEX_TESSERACT_CMD", "").strip()
    candidates = [configured, shutil.which("tesseract") or ""]
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
        )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return ""


def normalize_footer_tokens(value: object) -> NormalizedToken | None:
    """Normalize only contiguous One Piece identifier-shaped footer evidence.

    Whitespace may split a prefix/set/hyphen/number sequence (for example
    ``OP16 -080``), but unrelated words may not be skipped or joined.
    """

    text = str(value or "").upper()[:1000].translate(
        str.maketrans({"–": "-", "—": "-", "−": "-"})
    )
    match = CARD_NUMBER_PATTERN.search(text)
    if match:
        family = "OP" if match.group("family") == "0P" else match.group("family")
        set_raw = re.sub(r"\s", "", match.group("set"))
        number_raw = re.sub(r"\s", "", match.group("number"))
        set_part = set_raw.translate(NUMERIC_TRANSLATION)
        number_part = number_raw.translate(NUMERIC_TRANSLATION)
        corrections: list[str] = []
        if match.group("family") == "0P":
            corrections.append("0_TO_O_IN_OP_PREFIX")
        if set_part != set_raw or number_part != number_raw:
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        if re.search(r"\s", match.group(0)):
            corrections.append("ADJACENT_TOKEN_JOIN_WITHIN_IDENTIFIER")
        return NormalizedToken(
            f"{family}{set_part}-{number_part}", tuple(sorted(set(corrections))), match.group(0)
        )
    promo = PROMO_PATTERN.search(text)
    if promo:
        number_raw = re.sub(r"\s", "", promo.group("number"))
        number = number_raw.translate(NUMERIC_TRANSLATION)
        corrections = []
        if number != number_raw:
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        if re.search(r"\s", promo.group(0)):
            corrections.append("ADJACENT_TOKEN_JOIN_WITHIN_IDENTIFIER")
        return NormalizedToken(f"P-{number}", tuple(sorted(set(corrections))), promo.group(0))
    compact = COMPACT_PATTERN.search(text)
    if compact:
        family = "OP" if compact.group("family") == "0P" else compact.group("family")
        digits_raw = compact.group("digits")
        digits = digits_raw.translate(NUMERIC_TRANSLATION)
        set_part, number_part = digits[:-3], digits[-3:]
        if not set_part or not (set_part.isdigit() and number_part.isdigit()):
            return None
        corrections = ["MISSING_OR_NONSTANDARD_HYPHEN"]
        if compact.group("family") == "0P":
            corrections.append("0_TO_O_IN_OP_PREFIX")
        if digits != digits_raw:
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        return NormalizedToken(
            f"{family}{set_part}-{number_part}", tuple(sorted(set(corrections))), compact.group(0)
        )
    return None


def consensus_from_attempts(attempts: list[OcrAttempt]) -> tuple[str, float, int, int, bool]:
    """Require agreement from at least two independent preprocessing branches."""

    branch_votes: dict[str, set[str]] = defaultdict(set)
    for attempt in attempts:
        if attempt.normalized:
            branch_votes[attempt.normalized].add(attempt.branch)
    ranked = sorted(branch_votes.items(), key=lambda item: (-len(item[1]), item[0]))
    if not ranked:
        return "", 0.0, 0, 0, False
    winner, branches = ranked[0]
    runner_up_support = len(ranked[1][1]) if len(ranked) > 1 else 0
    distinct_valid_branches = len({branch for values in branch_votes.values() for branch in values})
    confidence = len(branches) / max(1, distinct_valid_branches)
    conflicting_consensus = runner_up_support >= 2
    trustworthy = (
        len(branches) >= 2
        and len(branches) > runner_up_support
        and confidence >= OCR_MIN_CONFIDENCE
        and not conflicting_consensus
    )
    return winner if trustworthy else "", confidence if trustworthy else 0.0, len(branches), distinct_valid_branches, conflicting_consensus


def _channel_quality(channel: np.ndarray) -> float:
    p10, p90 = np.percentile(channel, [10, 90])
    local_contrast = float(p90 - p10) / 255.0
    edges = cv2.Canny(channel, 80, 180)
    edge_density = float(np.count_nonzero(edges)) / max(1, edges.size)
    # Text needs contrast, while dense foil/halftone edges are a penalty.
    return local_contrast - max(0.0, edge_density - 0.18) * 0.9


def _best_channel(crop: np.ndarray) -> tuple[str, np.ndarray]:
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    channels = {
        "GRAY": cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY),
        "LAB_L": lab[:, :, 0],
        "BLUE": crop[:, :, 0],
        "GREEN": crop[:, :, 1],
        "RED": crop[:, :, 2],
    }
    name = max(channels, key=lambda key: (_channel_quality(channels[key]), key))
    return name, channels[name]


def _prepare(crop: np.ndarray, method: str) -> tuple[str, np.ndarray]:
    if method.startswith("LOCAL_CHANNEL"):
        channel_name, channel = _best_channel(crop)
    else:
        channel_name = "GRAY"
        channel = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if "DESCREEN" in method:
        target_width = min(channel.shape[1], 760)
        ratio = target_width / max(1, channel.shape[1])
        reduced = cv2.resize(channel, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
        channel = cv2.bilateralFilter(reduced, 5, 24, 24)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 4))
    enhanced = clahe.apply(channel)
    scale = max(2.0, min(4.0, 1250.0 / max(1, enhanced.shape[1])))
    enhanced = cv2.resize(enhanced, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if method.endswith("OTSU"):
        _threshold, enhanced = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method.endswith("ADAPTIVE"):
        enhanced = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )
    enhanced = cv2.copyMakeBorder(enhanced, 18, 18, 18, 18, cv2.BORDER_CONSTANT, value=255)
    return channel_name, enhanced


def _tesseract_tsv(command: str, image_path: Path, psm: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                command,
                str(image_path),
                "stdout",
                "-l",
                "eng",
                "--oem",
                "1",
                "--psm",
                str(psm),
                "-c",
                "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
                "-c",
                "load_system_dawg=0",
                "-c",
                "load_freq_dawg=0",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "raw": "",
            "confidence": 0.0,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": type(error).__name__.upper(),
        }
    words: list[str] = []
    confidences: list[float] = []
    if completed.returncode == 0:
        for line in completed.stdout.splitlines()[1:]:
            fields = line.split("\t", 11)
            if len(fields) != 12 or not fields[11].strip():
                continue
            words.append(fields[11].strip())
            try:
                confidence = float(fields[10])
            except ValueError:
                confidence = -1.0
            if confidence >= 0:
                confidences.append(confidence)
    return {
        "raw": " ".join(words)[:1000],
        "confidence": round((sum(confidences) / len(confidences)) / 100.0, 4) if confidences else 0.0,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "error": "" if completed.returncode == 0 else f"TESSERACT_EXIT_{completed.returncode}",
    }


class SleevedFoilOcrChallenger:
    """Layout-aware, shadow-only card-number OCR challenger."""

    REGIONS = {
        "FOOTER_NUMBER": (0.62, 0.895, 0.995, 0.995),
        "FOOTER_NUMBER_TIGHT": (0.70, 0.915, 0.995, 0.992),
        "LOWER_METADATA_BAND": (0.48, 0.845, 0.995, 0.998),
    }
    PLAN = (
        ("LOCAL_GRAY", "FOOTER_NUMBER", "LOCAL_GRAY_CLAHE", 11),
        ("LOCAL_CHANNEL", "FOOTER_NUMBER", "LOCAL_CHANNEL_CLAHE", 11),
        ("LOCAL_GRAY", "FOOTER_NUMBER_TIGHT", "LOCAL_GRAY_CLAHE_OTSU", 7),
        ("LOCAL_CHANNEL", "FOOTER_NUMBER_TIGHT", "LOCAL_CHANNEL_CLAHE_OTSU", 7),
        ("DESCREEN_GRAY", "FOOTER_NUMBER", "LOCAL_GRAY_DESCREEN_CLAHE", 11),
        ("DESCREEN_CHANNEL", "FOOTER_NUMBER", "LOCAL_CHANNEL_DESCREEN_CLAHE", 11),
        ("WIDE_GRAY", "LOWER_METADATA_BAND", "LOCAL_GRAY_DESCREEN_CLAHE", 11),
        ("WIDE_CHANNEL", "LOWER_METADATA_BAND", "LOCAL_CHANNEL_DESCREEN_CLAHE_ADAPTIVE", 11),
    )

    def __init__(self, tesseract_command: str | None = None):
        self.command = tesseract_command or find_tesseract()
        if not self.command:
            raise RuntimeError("Tesseract OCR runtime is unavailable")
        version = subprocess.run(
            [self.command, "--version"], capture_output=True, text=True, timeout=5, check=False
        )
        self.version = ((version.stdout or version.stderr).splitlines() or ["Unknown"])[0].strip()

    def analyze(self, source_path: Path) -> SleevedFoilOcrResult:
        import tracemalloc

        source = source_path.resolve()
        started = time.perf_counter()
        tracemalloc.start()
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            tracemalloc.stop()
            raise ValueError("Image cannot be decoded")
        if image.shape[1] > image.shape[0]:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        height, width = image.shape[:2]
        attempts: list[OcrAttempt] = []
        total_preprocess = 0.0
        total_execution = 0.0
        early_exit = ""
        with tempfile.TemporaryDirectory(prefix="dex-sleeved-foil-ocr-") as temporary:
            root = Path(temporary)
            for sequence, (branch, region_name, preprocessing, psm) in enumerate(self.PLAN, start=1):
                bounds = self.REGIONS[region_name]
                pixels = (
                    int(width * bounds[0]),
                    int(height * bounds[1]),
                    int(width * bounds[2]),
                    int(height * bounds[3]),
                )
                crop = image[pixels[1] : pixels[3], pixels[0] : pixels[2]]
                prep_started = time.perf_counter()
                channel_name, prepared = _prepare(crop, preprocessing)
                preprocessing_ms = round((time.perf_counter() - prep_started) * 1000, 2)
                total_preprocess += preprocessing_ms
                prepared_path = root / f"attempt-{sequence:02d}.png"
                cv2.imwrite(str(prepared_path), prepared)
                output = _tesseract_tsv(self.command, prepared_path, psm)
                total_execution += float(output["duration_ms"])
                token = normalize_footer_tokens(output["raw"])
                attempts.append(
                    OcrAttempt(
                        sequence=sequence,
                        branch=branch,
                        region_name=region_name,
                        region_pixels=pixels,
                        preprocessing=preprocessing,
                        selected_channel=channel_name,
                        page_segmentation_mode=psm,
                        raw_text=output["raw"],
                        normalized=token.card_number if token else "",
                        normalization_corrections=token.corrections if token else (),
                        engine_word_confidence=float(output["confidence"]),
                        preprocessing_ms=preprocessing_ms,
                        execution_ms=float(output["duration_ms"]),
                        error_code=output["error"],
                    )
                )
                trusted, _confidence, support, valid, conflict = consensus_from_attempts(attempts)
                if sequence >= 2 and trusted and support >= 2 and valid == 2 and not conflict:
                    early_exit = "TWO_AGREEING_INDEPENDENT_PREPROCESSING_BRANCHES"
                    break
        trusted, confidence, support, valid, conflict = consensus_from_attempts(attempts)
        candidates: dict[str, set[str]] = defaultdict(set)
        for attempt in attempts:
            if attempt.normalized:
                candidates[attempt.normalized].add(attempt.branch)
        ranked = sorted(candidates.items(), key=lambda item: (-len(item[1]), item[0]))
        candidate = ranked[0][0] if ranked else ""
        candidate_confidence = len(ranked[0][1]) / max(1, valid) if ranked else 0.0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return SleevedFoilOcrResult(
            challenger_version=CHALLENGER_VERSION,
            mode="SHADOW_ONLY",
            source_sha256=_sha256(source),
            normalized=trusted,
            candidate_normalized=candidate,
            confidence=round(confidence, 4),
            candidate_confidence=round(candidate_confidence, 4),
            source="LOCAL_TESSERACT_OCR" if trusted else "OCR_NO_TRUSTED_CONSENSUS",
            trustworthy=bool(trusted),
            consensus_support_branches=support,
            valid_candidate_branches=valid,
            conflicting_consensus=conflict,
            incorrect_authority_possible=False,
            attempts_run=len(attempts),
            attempts_available=len(self.PLAN),
            early_exit_reason=early_exit,
            preprocessing_ms=round(total_preprocess, 2),
            execution_ms=round(total_execution, 2),
            wall_ms=round((time.perf_counter() - started) * 1000, 2),
            peak_python_memory_bytes=peak,
            runtime={"engine": self.version, "available": True},
            debug_attempts=tuple(attempts),
        )

