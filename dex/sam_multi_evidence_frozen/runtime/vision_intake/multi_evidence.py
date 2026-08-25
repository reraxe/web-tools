"""Transparent, non-authoritative family-evidence fusion for SAM shadow research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from rapidfuzz import fuzz, process

from .dual_ocr import DualOcrResult, OcrObservation


FUSION_VERSION = "sam-multi-evidence-family-shadow-v1"
MAX_NAME_CANDIDATES = 8
MAX_TOTAL_CANDIDATES = 80
NAME_STRONG_THRESHOLD = 93.0
NAME_SUPPORT_THRESHOLD = 84.0
EVIDENCE_STATES = {"STRONG_SUPPORT", "SUPPORT", "NEUTRAL", "CONFLICT", "UNRESOLVED"}


def recognize_dual_ocr_shadow(
    scan_path: Path,
    references: list[dict[str, Any]],
    *,
    core: Any,
    frozen_challenger: Any,
    dual: DualOcrResult,
) -> dict[str, Any]:
    """Add bounded non-trusted dual-OCR families to unchanged frozen ranking."""

    injected = set(dual.candidates)
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
            family_best[family] = max(
                float(visual_scores[reference["asset_id"]]), family_best.get(family, 0.0)
            )
        selected_ids = {row["asset_id"] for row in rows}
        for family in sorted(injected):
            if family not in family_rows:
                continue
            sources.setdefault(family, set()).add("DUAL_OCR_NONTRUSTED_CANDIDATE")
            rows.extend(row for row in family_rows[family] if row["asset_id"] not in selected_ids)
        neighbor_by_family = {row["card_number"]: row for row in neighbors}
        for family in sorted(sources):
            neighbor_by_family[family] = {
                "card_number": family,
                "visual_score": round(family_best.get(family, 0.0), 4),
                "sources": sorted(sources[family]),
                "reference_count": len(family_rows.get(family, [])),
            }
        ordered = sorted(neighbor_by_family.values(), key=lambda row: (-row["visual_score"], row["card_number"]))
        return rows, visual_scores, sources, ordered

    frozen_challenger._candidate_union = augmented_union
    try:
        result = frozen_challenger.recognize_shadow(
            scan_path, references, core=core, ocr_evidence=dual.as_frozen_sam_evidence()
        )
    finally:
        frozen_challenger._candidate_union = original_union
    result["dual_ocr"] = dual.as_dict()
    result["candidate_generation"]["strategy"] = (
        "FROZEN_GLOBAL_VISUAL_AND_TRUSTED_OCR_UNION_PLUS_NONTRUSTED_DUAL_LOCALIZED_OCR"
    )
    result["candidate_generation"]["dual_ocr_candidates_are_trusted_ocr"] = False
    result["policy_guards"].update({
        "dual_ocr_candidate_cap": 8,
        "sam_authority_changed": False,
        "exact_printing_authority_changed": False,
    })
    return result


def _name_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@dataclass(frozen=True)
class EvidenceFamily:
    card_number: str
    set_code: str
    canonical_name: str | None
    alternative_names: tuple[str, ...]
    rarity_labels: tuple[str, ...]


class MultiEvidenceCatalog:
    def __init__(self, families: Iterable[EvidenceFamily], *, version: str, sha256: str) -> None:
        self.version = version
        self.sha256 = sha256
        self.families = {family.card_number: family for family in families}
        self.name_choices: dict[str, str] = {}
        for family in self.families.values():
            for name in (family.canonical_name, *family.alternative_names):
                if name and len(_name_key(name)) >= 4:
                    self.name_choices[f"{family.card_number}|{name}"] = _name_key(name)

    @classmethod
    def from_snapshot(cls, path: Path) -> "MultiEvidenceCatalog":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("recognition_authority") is not False:
            raise ValueError("Multi-evidence catalog must be descriptive and non-authoritative")
        families = [EvidenceFamily(
            card_number=str(row["card_number"]).upper(),
            set_code=str(row.get("set_code") or "").upper(),
            canonical_name=row.get("canonical_name"),
            alternative_names=tuple(row.get("alternative_names") or ()),
            rarity_labels=tuple(row.get("rarity_labels") or ()),
        ) for row in payload.get("families") or []]
        if len(families) != int(payload.get("family_count") or -1):
            raise ValueError("Multi-evidence catalog family count does not reconcile")
        return cls(
            families,
            version=str(payload.get("snapshot_version") or ""),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )


@dataclass(frozen=True)
class EvidenceAssertion:
    field: str
    source: str
    state: str
    observed_value: str | None
    candidate_value: str | None
    confidence: float | None
    reason: str
    provenance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise ValueError(f"Invalid evidence state: {self.state}")


@dataclass(frozen=True)
class CandidateAssessment:
    card_number: str
    canonical_name: str | None
    assertions: tuple[EvidenceAssertion, ...]
    visual_score: float
    visual_rank: int | None

    @property
    def strong_count(self) -> int:
        return sum(item.state == "STRONG_SUPPORT" for item in self.assertions)

    @property
    def support_count(self) -> int:
        return sum(item.state == "SUPPORT" for item in self.assertions)

    @property
    def conflict_count(self) -> int:
        return sum(item.state == "CONFLICT" for item in self.assertions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "card_number": self.card_number,
            "canonical_name": self.canonical_name,
            "assertions": [asdict(item) for item in self.assertions],
            "strong_support_count": self.strong_count,
            "support_count": self.support_count,
            "conflict_count": self.conflict_count,
            "visual_score": self.visual_score,
            "visual_rank": self.visual_rank,
        }


def _observation_text(observation: OcrObservation) -> str:
    return " ".join(token.text for token in observation.tokens) or observation.raw_text


def name_candidates(
    observations: Sequence[OcrObservation], catalog: MultiEvidenceCatalog,
    *, max_candidates: int = MAX_NAME_CANDIDATES,
) -> list[dict[str, Any]]:
    """Return bounded fuzzy-name observations; no match is ever authority."""

    best: dict[str, dict[str, Any]] = {}
    for observation in observations:
        observed_text = _name_key(_observation_text(observation))
        if len(observed_text) < 4:
            continue
        matches = process.extract(
            observed_text,
            catalog.name_choices,
            scorer=fuzz.WRatio,
            score_cutoff=NAME_SUPPORT_THRESHOLD,
            limit=max_candidates,
        )
        for _choice_value, score, choice_key in matches:
            card_number, source_name = choice_key.split("|", 1)
            item = {
                "card_number": card_number,
                "observed_text": observation.raw_text,
                "catalog_name": source_name,
                "confidence": round(float(score) / 100.0, 6),
                "attempt_id": observation.attempt_id,
                "engine": observation.engine,
            }
            if card_number not in best or item["confidence"] > best[card_number]["confidence"]:
                best[card_number] = item
    return sorted(best.values(), key=lambda row: (-row["confidence"], row["card_number"]))[:max_candidates]


def _visual_neighbors(challenger_result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list((challenger_result.get("candidate_generation") or {}).get("family_neighbors") or [])
    return sorted(rows, key=lambda row: (-float(row.get("visual_score") or 0.0), str(row.get("card_number") or "")))


def _card_number_assertions(card_number: str, dual: DualOcrResult) -> list[EvidenceAssertion]:
    if dual.engine_conflict:
        observed = sorted({path.card_number for path in dual.candidate_paths})
        return [EvidenceAssertion(
            field="CARD_NUMBER",
            source="DUAL_LOCALIZED_OCR",
            state="CONFLICT",
            observed_value=" | ".join(observed),
            candidate_value=card_number,
            confidence=None,
            reason="Independent OCR engines produced incompatible catalog-valid identifiers.",
            provenance_ids=tuple(path.attempt_id for path in dual.candidate_paths),
        )]
    matching = [path for path in dual.candidate_paths if path.card_number == card_number]
    engines = {path.engine for path in matching}
    if len(engines) >= 2:
        return [EvidenceAssertion(
            field="CARD_NUMBER",
            source="DUAL_LOCALIZED_OCR",
            state="STRONG_SUPPORT",
            observed_value=card_number,
            candidate_value=card_number,
            confidence=min(path.confidence for path in matching),
            reason="Two independent OCR engines observed the same catalog-valid printed identifier.",
            provenance_ids=tuple(path.attempt_id for path in matching),
        )]
    if matching:
        return [EvidenceAssertion(
            field="CARD_NUMBER",
            source=matching[0].engine,
            state="SUPPORT",
            observed_value=card_number,
            candidate_value=card_number,
            confidence=max(path.confidence for path in matching),
            reason="One OCR engine observed a catalog-valid identifier; corroboration is absent.",
            provenance_ids=tuple(path.attempt_id for path in matching),
        )]
    observed = sorted({path.card_number for path in dual.candidate_paths})
    if observed:
        return [EvidenceAssertion(
            field="CARD_NUMBER",
            source="DUAL_LOCALIZED_OCR",
            state="CONFLICT",
            observed_value=" | ".join(observed),
            candidate_value=card_number,
            confidence=None,
            reason="Observed catalog-valid card-number evidence supports a different family.",
            provenance_ids=tuple(path.attempt_id for path in dual.candidate_paths),
        )]
    return [EvidenceAssertion(
        field="CARD_NUMBER",
        source="DUAL_LOCALIZED_OCR",
        state="UNRESOLVED",
        observed_value=None,
        candidate_value=card_number,
        confidence=None,
        reason="No catalog-valid printed card number was reconstructed safely.",
    )]


def _name_assertions(card_number: str, names: Sequence[dict[str, Any]]) -> list[EvidenceAssertion]:
    matching = next((row for row in names if row["card_number"] == card_number), None)
    if matching:
        score = float(matching["confidence"])
        return [EvidenceAssertion(
            field="CARD_NAME",
            source=str(matching["engine"]),
            state="STRONG_SUPPORT" if score >= NAME_STRONG_THRESHOLD / 100.0 else "SUPPORT",
            observed_value=str(matching["observed_text"]),
            candidate_value=str(matching["catalog_name"]),
            confidence=score,
            reason="Localized printed-name evidence is compatible with this catalog family.",
            provenance_ids=(str(matching["attempt_id"]),),
        )]
    if names and float(names[0]["confidence"]) >= NAME_STRONG_THRESHOLD / 100.0:
        return [EvidenceAssertion(
            field="CARD_NAME",
            source=str(names[0]["engine"]),
            state="CONFLICT",
            observed_value=str(names[0]["observed_text"]),
            candidate_value=None,
            confidence=float(names[0]["confidence"]),
            reason="High-quality name evidence supports a different catalog family.",
            provenance_ids=(str(names[0]["attempt_id"]),),
        )]
    return [EvidenceAssertion(
        field="CARD_NAME",
        source="LOCALIZED_NAME_OCR",
        state="UNRESOLVED",
        observed_value=None,
        candidate_value=None,
        confidence=None,
        reason="Printed-name evidence was absent or insufficiently distinctive.",
    )]


def evaluate_multi_evidence(
    dual: DualOcrResult,
    name_observations: Sequence[OcrObservation],
    challenger_result: dict[str, Any],
    catalog: MultiEvidenceCatalog,
) -> dict[str, Any]:
    """Rank a bounded union using categorical evidence; never apply identity."""

    names = name_candidates(name_observations, catalog)
    visual = _visual_neighbors(challenger_result)
    visual_by_family = {str(row["card_number"]): row for row in visual}
    family_numbers = set(visual_by_family)
    family_numbers.update(dual.candidates)
    family_numbers.update(row["card_number"] for row in names)
    family_numbers.intersection_update(catalog.families)
    if len(family_numbers) > MAX_TOTAL_CANDIDATES:
        visual_keep = [str(row["card_number"]) for row in visual[:MAX_TOTAL_CANDIDATES]]
        required = set(dual.candidates) | {row["card_number"] for row in names}
        family_numbers = required | set(visual_keep[: max(0, MAX_TOTAL_CANDIDATES - len(required))])

    assessments: list[CandidateAssessment] = []
    visual_rank = {str(row["card_number"]): index for index, row in enumerate(visual, start=1)}
    for card_number in sorted(family_numbers):
        family = catalog.families[card_number]
        assertions = _card_number_assertions(card_number, dual) + _name_assertions(card_number, names)
        visual_row = visual_by_family.get(card_number)
        if visual_row:
            assertions.append(EvidenceAssertion(
                field="VISUAL_FAMILY",
                source="UNCHANGED_SAM_VISUAL_RANKING",
                state="SUPPORT",
                observed_value=card_number,
                candidate_value=card_number,
                confidence=float(visual_row.get("visual_score") or 0.0),
                reason=f"Unchanged SAM visual retrieval included this family at rank {visual_rank[card_number]}.",
            ))
        else:
            assertions.append(EvidenceAssertion(
                field="VISUAL_FAMILY",
                source="UNCHANGED_SAM_VISUAL_RANKING",
                state="UNRESOLVED",
                observed_value=None,
                candidate_value=card_number,
                confidence=None,
                reason="The family entered through non-visual evidence and lacks a visual-neighbor score.",
            ))
        assessments.append(CandidateAssessment(
            card_number=card_number,
            canonical_name=family.canonical_name,
            assertions=tuple(assertions),
            visual_score=float((visual_row or {}).get("visual_score") or 0.0),
            visual_rank=visual_rank.get(card_number),
        ))

    assessments.sort(key=lambda item: (
        item.conflict_count,
        -item.strong_count,
        -item.support_count,
        -item.visual_score,
        item.visual_rank if item.visual_rank is not None else 999999,
        item.card_number,
    ))
    top = assessments[0] if assessments else None
    if dual.engine_conflict:
        state = "CONFLICT"
    elif top is None:
        state = "UNRESOLVED"
    elif top.conflict_count:
        state = "CONFLICT"
    elif top.strong_count:
        state = "STRONG_SUPPORT"
    elif top.support_count >= 2:
        state = "SUPPORT"
    else:
        state = "UNRESOLVED"

    runner_up = assessments[1] if len(assessments) > 1 else None
    explanation: list[str] = []
    if top:
        explanation.append(
            f"Top family {top.card_number} has {top.strong_count} strong, "
            f"{top.support_count} supporting, and {top.conflict_count} conflicting evidence item(s)."
        )
        explanation.extend(item.reason for item in top.assertions if item.state in {"STRONG_SUPPORT", "SUPPORT", "CONFLICT"})
    if runner_up:
        explanation.append(
            f"Runner-up {runner_up.card_number} has {runner_up.strong_count} strong, "
            f"{runner_up.support_count} supporting, and {runner_up.conflict_count} conflicting evidence item(s)."
        )
    return {
        "fusion_version": FUSION_VERSION,
        "state": state,
        "top_family": top.card_number if top else None,
        "top_family_name": top.canonical_name if top else None,
        "candidate_count": len(assessments),
        "candidate_cap": MAX_TOTAL_CANDIDATES,
        "candidates": [item.as_dict() for item in assessments],
        "name_observations": [item.as_dict() for item in name_observations],
        "name_candidates": names,
        "human_explanation": explanation,
        "conflict_state": "CONFLICT" if state == "CONFLICT" else "NONE",
        "catalog": {
            "version": catalog.version,
            "sha256": catalog.sha256,
            "family_count": len(catalog.families),
            "recognition_authority": False,
        },
        "authority": {
            "identity_applied": False,
            "family_authority_granted": False,
            "printing_authority_granted": False,
            "sam_authority_rules_changed": False,
        },
        "deferred": {
            "dense_retrieval": True,
            "geometry_integration": True,
            "exact_printing": True,
        },
    }
