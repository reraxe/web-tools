"""Private, local-only image OCR for DEX receipt intelligence.

Original source artifacts are never modified.  Derived images live only in a
temporary directory and are removed before this module returns.  Raw OCR text
is returned to the in-process parser but is not persisted or logged.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


OCR_VERSION = "receipt-image-tesseract-v1"
OCR_TIMEOUT_SECONDS = 30


class ReceiptOcrUnavailable(ValueError):
    code = "LOCAL_OCR_UNAVAILABLE"


class ReceiptOcrFailed(ValueError):
    code = "LOCAL_OCR_FAILED"


def find_tesseract_command() -> str:
    if str(os.environ.get("DEX_RECEIPT_OCR_ENABLED", "1")).strip().lower() in (
        "0", "false", "no", "off",
    ):
        return ""
    configured = str(os.environ.get("DEX_TESSERACT_CMD", "")).strip()
    candidates = [configured, shutil.which("tesseract") or ""]
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
        )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).is_file():
            return str(Path(resolved).resolve())
    return ""


def tesseract_version(command: str) -> str:
    if not command:
        return "Unavailable"
    try:
        result = subprocess.run(
            [command, "--version"], capture_output=True, text=True,
            timeout=5, check=False,
        )
        return ((result.stdout or result.stderr).splitlines() or ["Unknown"])[0][:120]
    except (OSError, subprocess.SubprocessError):
        return "Unknown"


def provider_health() -> dict:
    command = find_tesseract_command()
    return {
        "provider": "LOCAL_TESSERACT_RECEIPT",
        "version": OCR_VERSION,
        "configured": bool(command),
        "available": bool(command),
        "private_local_processing": True,
        "external_transmission": False,
        "operational_formats": ["image/jpeg", "image/png"] if command else [],
        "tesseract_version": tesseract_version(command),
        "originals_modified": False,
        "derived_working_images_persisted": False,
    }


def _text_score(text: str) -> float:
    """Rank OCR attempts without interpreting receipt identity or economics."""

    compact = " ".join(text.split())
    if not compact:
        return 0.0
    words = re.findall(r"[A-Za-z]{2,}", compact)
    amounts = re.findall(r"(?:\$\s*)?\d+[.,]\d{2}\b", compact)
    receipt_terms = re.findall(
        r"\b(?:subtotal|total|tax|discount|fee|qty|quantity|receipt|date)\b",
        compact,
        re.I,
    )
    return len(words) + 4 * len(amounts) + 3 * len(receipt_terms)


def _prepare(image: Image.Image, angle: float = 0.0) -> Image.Image:
    prepared = ImageOps.exif_transpose(image).convert("L")
    if max(prepared.size) > 2600:
        ratio = 2600 / max(prepared.size)
        prepared = prepared.resize(
            (max(1, round(prepared.width * ratio)), max(1, round(prepared.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    if angle:
        prepared = prepared.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    prepared = ImageOps.autocontrast(prepared, cutoff=1)
    prepared = ImageEnhance.Contrast(prepared).enhance(1.3)
    prepared = prepared.filter(ImageFilter.SHARPEN)
    if prepared.width < 1200:
        ratio = 1200 / max(1, prepared.width)
        prepared = prepared.resize(
            (1200, max(1, round(prepared.height * ratio))), Image.Resampling.LANCZOS
        )
    return prepared


def _run_tesseract(command: str, path: Path, psm: int = 6) -> tuple[str, float]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [
                command, str(path), "stdout", "-l", "eng", "--oem", "1",
                "--psm", str(psm), "-c", "preserve_interword_spaces=1",
            ],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptOcrFailed("Private local receipt OCR failed") from exc
    elapsed = (time.perf_counter() - started) * 1000
    if result.returncode != 0:
        raise ReceiptOcrFailed("Private local receipt OCR failed")
    return result.stdout or "", elapsed


def extract_image_text(data: bytes) -> dict:
    command = find_tesseract_command()
    if not command:
        raise ReceiptOcrUnavailable(
            "Private local image OCR is unavailable; continue with HF2 manual purchase facts"
        )
    preprocess_started = time.perf_counter()
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            source = opened.copy()
    except Exception as exc:
        raise ReceiptOcrFailed("Receipt image could not be decoded locally") from exc

    attempts: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="dex-receipt-ocr-") as temporary:
        root = Path(temporary)

        def attempt(angle: float, psm: int = 6) -> None:
            prepared = _prepare(source, angle)
            path = root / f"receipt-{len(attempts)}.png"
            prepared.save(path, format="PNG", optimize=False)
            text, duration = _run_tesseract(command, path, psm)
            attempts.append(
                {
                    "angle": angle, "psm": psm, "text": text,
                    "score": _text_score(text), "ocr_ms": duration,
                }
            )

        attempt(0.0, 6)
        # Tesseract usually handles upright receipts.  Extra local attempts are
        # bounded and occur only when the first pass lacks receipt-like evidence.
        if attempts[0]["score"] < 24:
            for angle in (-3.0, 3.0, 90.0, 180.0, 270.0):
                attempt(angle, 6)
        best = max(attempts, key=lambda item: (item["score"], -abs(item["angle"])))

    preprocess_ms = (time.perf_counter() - preprocess_started) * 1000 - sum(
        float(item["ocr_ms"]) for item in attempts
    )
    if not best["text"].strip():
        raise ReceiptOcrFailed("Local OCR could not read purchase facts from this image")
    return {
        "pages": [(1, best["text"])],
        "metrics": {
            "preprocessing_ms": round(max(0.0, preprocess_ms), 2),
            "ocr_ms": round(sum(float(item["ocr_ms"]) for item in attempts), 2),
            "ocr_attempt_count": len(attempts),
            "selected_rotation_degrees": best["angle"],
            "selected_psm": best["psm"],
        },
        "provider": "LOCAL_TESSERACT_RECEIPT",
        "provider_version": OCR_VERSION,
    }
