"""Offline, non-authoritative catalog interpretation for frozen SAM OCR evidence.

The module never changes an OCR observation, never grants OCR trust, and never
applies identity.  It can only nominate at most eight local card families for a
shadow candidate-generation experiment.
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


INTERPRETER_VERSION = "catalog-constrained-ocr-shadow-v1"
MAX_INJECTED_CANDIDATES = 8
CANDIDATE_STATES = {
    "EXACT_OBSERVED_MATCH",
    "CATALOG_CONSTRAINED_CANDIDATE",
    "AMBIGUOUS",
    "NO_MATCH",
}
_DASH_TRANSLATION = str.maketrans({"–": "-", "—": "-", "−": "-", "_": "-"})
_DIGIT_TRANSLATION = str.maketrans({"O": "0", "I": "1", "L": "1"})
_STRICT_IDENTIFIER = re.compile(
    r"(?<![A-Z0-9])(?:(?:OP|EB|ST|PRB)\d{1,3}-\d{3}[A-Z]?|P-\d{3}[A-Z]?)(?![A-Z0-9])"
)
_SET_ONLY = re.compile(r"(?<![A-Z0-9])(?:OP|0P|EB|ST|PRB)[0-9OIL]{1,3}(?![A-Z0-9])")
_SUFFIX_ONLY = re.compile(r"(?<![A-Z0-9])[0-9OIL]{3}[A-Z]?(?![A-Z0-9])")


@dataclass(frozen=True)
class CatalogFamily:
    card_number: str
    set_code: str
    canonical_name: str | None = None


@dataclass(frozen=True)
class OcrObservation:
    attempt_id: str
    raw_text: str
    confidence: float
    bounding_box: tuple[int, int, int, int] | None
    source_region: str | None
    region_pixels: tuple[int, int, int, int] | None
    image_source: str
    preprocessing_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "source_region": self.source_region,
            "region_pixels": list(self.region_pixels) if self.region_pixels else None,
            "image_source": self.image_source,
            "preprocessing_version": self.preprocessing_version,
        }


class LocalFamilyCatalog:
    def __init__(self, families: Iterable[CatalogFamily], *, version: str, sha256: str = "") -> None:
        self.version = version
        self.sha256 = sha256
        self.families = {family.card_number.upper(): family for family in families}
        self.by_set: dict[str, set[str]] = defaultdict(set)
        self.by_suffix: dict[str, set[str]] = defaultdict(set)
        self.by_name: dict[str, set[str]] = defaultdict(set)
        for number, family in self.families.items():
            self.by_set[family.set_code.upper()].add(number)
            suffix = number.split("-", 1)[1] if "-" in number else ""
            self.by_suffix[suffix].add(number)
            if family.canonical_name:
                self.by_name[_name_key(family.canonical_name)].add(number)

    @classmethod
    def from_snapshot(cls, path: Path) -> "LocalFamilyCatalog":
        import hashlib

        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("recognition_authority") is not False:
            raise ValueError("Local catalog snapshot must be non-authoritative")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        families = [
            CatalogFamily(
                card_number=str(row["card_number"]).upper(),
                set_code=str(row.get("set_code") or "").upper(),
                canonical_name=row.get("canonical_name"),
            )
            for row in payload.get("families") or []
        ]
        if len(families) != int(payload.get("family_count") or -1):
            raise ValueError("Catalog family count does not reconcile")
        return cls(families, version=str(payload.get("snapshot_version") or ""), sha256=digest)


def _name_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def observations_from_evidence(evidence: dict[str, Any]) -> list[OcrObservation]:
    """Convert frozen SAM evidence without discarding or rewriting raw observations."""

    method = str(evidence.get("method_version") or "UNKNOWN_OCR_METHOD")
    output: list[OcrObservation] = []
    attempts = list(evidence.get("debug_attempts") or [])
    for offset, attempt in enumerate(attempts, start=1):
        sequence = int(attempt.get("sequence") or offset)
        region = attempt.get("region")
        region_pixels = tuple(int(value) for value in region) if isinstance(region, list) and len(region) == 4 else None
        output.append(OcrObservation(
            attempt_id=f"{method}:ATTEMPT-{sequence:02d}",
            raw_text=str(attempt.get("raw") or ""),
            confidence=float(attempt.get("confidence") or 0.0),
            bounding_box=None,  # Frozen OCR did not persist word-level TSV coordinates.
            source_region=str(attempt.get("region_name") or "") or None,
            region_pixels=region_pixels,
            image_source="IMMUTABLE_RAW_SCAN",
            preprocessing_version=(
                f"{method}:{attempt.get('preprocessing') or 'UNKNOWN'}:PSM-{attempt.get('psm')}"
            ),
        ))
    if not output and evidence.get("raw"):
        region = evidence.get("region")
        region_pixels = tuple(int(value) for value in region) if isinstance(region, list) and len(region) == 4 else None
        output.append(OcrObservation(
            attempt_id=f"{method}:SELECTED-EVIDENCE",
            raw_text=str(evidence.get("raw") or ""),
            confidence=float(evidence.get("engine_word_confidence") or evidence.get("confidence") or 0.0),
            bounding_box=None,
            source_region=str(evidence.get("region_name") or "") or None,
            region_pixels=region_pixels,
            image_source="IMMUTABLE_RAW_SCAN",
            preprocessing_version=f"{method}:{evidence.get('preprocessing') or 'UNKNOWN'}:PSM-{evidence.get('psm')}",
        ))
    return output


def _normalize_surface(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.upper().translate(_DASH_TRANSLATION)).strip()


def _parse_compact_identifier(compact: str) -> tuple[str, list[str]] | None:
    original = compact.upper()
    compact = re.sub(r"[^A-Z0-9]", "", original)
    prefix = ""
    prefix_length = 0
    for candidate in ("PRB", "OP", "0P", "EB", "ST", "P"):
        if compact.startswith(candidate):
            prefix, prefix_length = candidate, len(candidate)
            break
    if not prefix:
        return None
    corrections: list[str] = []
    if prefix == "0P":
        prefix = "OP"
        corrections.append("0_TO_O_IN_OP_PREFIX")
    body = compact[prefix_length:]
    suffix_letter = body[-1] if body and body[-1].isalpha() and body[-1] not in "OIL" else ""
    digits = body[:-1] if suffix_letter else body
    if prefix == "P":
        if len(digits) != 3:
            return None
        translated = digits.translate(_DIGIT_TRANSLATION)
        if not translated.isdigit():
            return None
        if translated != digits:
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        return f"P-{translated}{suffix_letter}", corrections
    if not 4 <= len(digits) <= 6:
        return None
    set_part, number_part = digits[:-3], digits[-3:]
    translated_set = set_part.translate(_DIGIT_TRANSLATION)
    translated_number = number_part.translate(_DIGIT_TRANSLATION)
    if not (1 <= len(translated_set) <= 3 and translated_set.isdigit() and translated_number.isdigit()):
        return None
    if translated_set != set_part or translated_number != number_part:
        corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
    return f"{prefix}{translated_set}-{translated_number}{suffix_letter}", corrections


def _candidate_windows(surface: str) -> list[tuple[str, list[str]]]:
    tokens = re.findall(r"[A-Z0-9]+", surface)
    windows: list[tuple[str, list[str]]] = []
    for width in range(1, min(3, len(tokens)) + 1):
        for index in range(0, len(tokens) - width + 1):
            selected = tokens[index:index + width]
            windows.append(("".join(selected), selected))
    return windows


def _add_path(
    paths: dict[str, list[dict[str, Any]]],
    card_number: str,
    observation: OcrObservation,
    rule: str,
    transformations: list[str],
) -> None:
    paths[card_number].append({
        "attempt_id": observation.attempt_id,
        "observed_text": observation.raw_text,
        "observed_confidence": observation.confidence,
        "rule": rule,
        "transformations": transformations,
    })


def interpret_catalog_candidates(
    evidence: dict[str, Any],
    catalog: LocalFamilyCatalog,
    *,
    max_candidates: int = MAX_INJECTED_CANDIDATES,
) -> dict[str, Any]:
    started = time.perf_counter()
    observations = observations_from_evidence(evidence)
    paths: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exact_support: dict[str, set[str]] = defaultdict(set)
    query_started = time.perf_counter()

    for observation in observations:
        surface = _normalize_surface(observation.raw_text)
        full_identifier_found = False
        for exact in _STRICT_IDENTIFIER.findall(surface):
            exact = exact.upper()
            if exact in catalog.families:
                full_identifier_found = True
                exact_support[exact].add(observation.attempt_id)
                _add_path(paths, exact, observation, "STRICT_PRINTED_IDENTIFIER", ["UPPERCASE", "UNICODE_DASH_NORMALIZATION"])

        for compact, token_parts in _candidate_windows(surface):
            parsed = _parse_compact_identifier(compact)
            if not parsed:
                continue
            card_number, corrections = parsed
            if card_number not in catalog.families:
                continue
            full_identifier_found = True
            transformations = ["UPPERCASE", "UNICODE_DASH_NORMALIZATION"]
            if len(token_parts) > 1:
                transformations.append("SPATIALLY_ORDERED_TOKEN_ASSEMBLY")
            if "-" not in observation.raw_text:
                transformations.append("OPTIONAL_HYPHEN_RECONSTRUCTION")
            transformations.extend(corrections)
            _add_path(paths, card_number, observation, "ONE_PIECE_IDENTIFIER_GRAMMAR", sorted(set(transformations)))

        for set_token in ([] if full_identifier_found else _SET_ONLY.findall(surface)):
            normalized_set = set_token.upper()
            if normalized_set.startswith("0P"):
                normalized_set = "OP" + normalized_set[2:]
            prefix = re.match(r"(?:OP|EB|ST|PRB)", normalized_set)
            if not prefix:
                continue
            digits = normalized_set[len(prefix.group(0)):].translate(_DIGIT_TRANSLATION)
            if not digits.isdigit():
                continue
            set_code = f"{prefix.group(0)}{digits}"
            for card_number in catalog.by_set.get(set_code, set()):
                _add_path(paths, card_number, observation, "PARTIAL_SET_PREFIX", ["UPPERCASE", "SET_PREFIX_ONLY"])

        for suffix_token in ([] if full_identifier_found else _SUFFIX_ONLY.findall(surface)):
            suffix = suffix_token.upper().translate(_DIGIT_TRANSLATION)
            for card_number in catalog.by_suffix.get(suffix, set()):
                _add_path(paths, card_number, observation, "PARTIAL_NUMERIC_SUFFIX", ["NUMERIC_SUFFIX_ONLY"])

        if catalog.by_name:
            compact_name = _name_key(surface)
            for name_key, family_numbers in catalog.by_name.items():
                if len(name_key) >= 5 and name_key in compact_name:
                    for card_number in family_numbers:
                        _add_path(paths, card_number, observation, "CANONICAL_NAME_FRAGMENT", ["UPPERCASE", "NAME_PUNCTUATION_REMOVAL"])

    query_ms = round((time.perf_counter() - query_started) * 1000, 4)
    candidates = sorted(paths)
    independently_exact = sorted(number for number, attempts in exact_support.items() if len(attempts) >= 2)
    if len(independently_exact) == 1:
        state = "EXACT_OBSERVED_MATCH"
        injected = independently_exact
    elif len(independently_exact) > 1 or len(candidates) > max_candidates:
        state = "AMBIGUOUS"
        injected = []
    elif candidates:
        state = "CATALOG_CONSTRAINED_CANDIDATE"
        injected = candidates
    else:
        state = "NO_MATCH"
        injected = []
    if state not in CANDIDATE_STATES:
        raise AssertionError("Unexpected candidate state")
    total_ms = round((time.perf_counter() - started) * 1000, 4)
    return {
        "interpreter_version": INTERPRETER_VERSION,
        "state": state,
        "observed": [item.as_dict() for item in observations],
        "interpreted": [
            {
                "card_number": number,
                "transformation_paths": paths[number],
                "independent_exact_observation_count": len(exact_support.get(number, set())),
            }
            for number in candidates
        ],
        "trusted": {
            "changed_by_interpreter": False,
            "existing_trusted_card_number": evidence.get("normalized") if evidence.get("source") == "LOCAL_TESSERACT_OCR" else None,
        },
        "candidate_count": len(candidates),
        "candidate_cap": max_candidates,
        "injected_candidates": injected,
        "injection_performed": bool(injected),
        "catalog": {
            "version": catalog.version,
            "sha256": catalog.sha256,
            "family_count": len(catalog.families),
            "offline": True,
        },
        "latency_ms": {"catalog_query": query_ms, "complete_interpretation": total_ms},
        "authority": {
            "ocr_trust_granted": False,
            "identity_authority_granted": False,
            "printing_authority_granted": False,
        },
    }


def recognize_catalog_constrained_shadow(
    scan_path: Path,
    references: list[dict[str, Any]],
    *,
    core: Any,
    frozen_challenger: Any,
    catalog: LocalFamilyCatalog,
    ocr_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run frozen ranking/authority with an additive, non-trusted candidate union."""

    evidence = ocr_evidence if ocr_evidence is not None else core.read_card_number_evidence(scan_path, None)
    interpretation = interpret_catalog_candidates(evidence, catalog)
    injected = set(interpretation["injected_candidates"])
    original_union = frozen_challenger._candidate_union

    def augmented_union(reference_rows, scan_features, trusted_ocr_family, frozen_core):
        rows, visual_scores, sources, neighbors = original_union(
            reference_rows, scan_features, trusted_ocr_family, frozen_core
        )
        family_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        family_best: dict[str, float] = {}
        for reference in reference_rows:
            family = reference["family"]
            family_rows[family].append(reference)
            score = visual_scores[reference["asset_id"]]
            family_best[family] = max(score, family_best.get(family, 0.0))
        already_selected = {row["asset_id"] for row in rows}
        for family in sorted(injected):
            if family not in family_rows:
                continue
            sources.setdefault(family, set()).add("CATALOG_CONSTRAINED_OCR_CANDIDATE")
            rows.extend(row for row in family_rows[family] if row["asset_id"] not in already_selected)
        neighbor_by_family = {row["card_number"]: row for row in neighbors}
        for family in sorted(sources):
            neighbor_by_family[family] = {
                "card_number": family,
                "visual_score": round(family_best.get(family, 0.0), 4),
                "sources": sorted(sources[family]),
                "reference_count": len(family_rows.get(family, [])),
            }
        ordered_neighbors = sorted(
            neighbor_by_family.values(), key=lambda row: (-row["visual_score"], row["card_number"])
        )
        return rows, visual_scores, sources, ordered_neighbors

    frozen_challenger._candidate_union = augmented_union
    try:
        result = frozen_challenger.recognize_shadow(
            scan_path, references, core=core, ocr_evidence=evidence
        )
    finally:
        frozen_challenger._candidate_union = original_union
    visual_top = (result.get("evidence") or {}).get("visual_top_family")
    interpretation["ocr_visual_conflict"] = bool(
        injected and visual_top and visual_top not in injected
    )
    result["catalog_constrained_ocr"] = interpretation
    result["candidate_generation"]["strategy"] = (
        "FROZEN_GLOBAL_VISUAL_AND_TRUSTED_OCR_UNION_PLUS_NONTRUSTED_LOCAL_CATALOG_OCR"
    )
    result["candidate_generation"]["catalog_candidates_are_trusted_ocr"] = False
    result["policy_guards"].update({
        "catalog_runtime_api": False,
        "catalog_candidate_cap": MAX_INJECTED_CANDIDATES,
        "sam_authority_changed": False,
        "exact_printing_authority_changed": False,
    })
    return result
