"""SAM family/printing identity and append-only evidence services.

Catalog and reference metadata are descriptive.  Only the established family
authority path or an explicit operator printing decision may update inventory
truth.  A family decision never implies a commercial-printing decision.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Mapping, Sequence


CERTAINTIES = (
    "AUTHORITATIVE",
    "OPERATOR_CONFIRMED",
    "HIGH_CONFIDENCE_SUGGESTION",
    "UNRESOLVED",
    "CONFLICTING",
    "LEGACY_RECORDED",
)
MARKER_STATES = ("PRESENT", "ABSENT_CONFIDENT", "UNRESOLVED")
PRINTING_EVIDENCE_VERSION = "sam-printing-evidence-v2"
ARTWORK_PRESENT_MINIMUM = 0.86
ARTWORK_ABSENT_MAXIMUM = 0.30


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: object, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(value: object, fallback: object) -> object:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _value(row: Mapping | sqlite3.Row, key: str, default: object = "") -> object:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def normalize_name(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", clean(value, 240).upper()).strip()


def family_key(game: object, set_code: object, card_number: object, name: object) -> str:
    normalized_game = normalize_name(game) or "UNKNOWN GAME"
    normalized_number = clean(card_number, 80).upper()
    normalized_set = clean(set_code, 80).upper()
    normalized_name = normalize_name(name)
    identity = normalized_number or f"{normalized_set}|{normalized_name}"
    return hashlib.sha256(f"{normalized_game}|{identity}".encode()).hexdigest()


def ensure_family(
    db: sqlite3.Connection,
    *,
    game: object,
    set_code: object,
    card_number: object,
    name: object,
    external_descriptors: Mapping | None = None,
) -> dict | None:
    game_text = clean(game, 80) or "Unknown"
    set_text = clean(set_code, 80).upper()
    number_text = clean(card_number, 80).upper()
    name_text = clean(name, 240)
    if not number_text and not name_text:
        return None
    key = family_key(game_text, set_text, number_text, name_text)
    now = utcnow()
    db.execute(
        """INSERT INTO sam_card_families
             (family_uuid,game,family_key,normalized_set_code,card_number,canonical_name,
              normalized_name,external_descriptors,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(game,family_key) DO UPDATE SET
             normalized_set_code=CASE WHEN sam_card_families.normalized_set_code=''
                                      THEN excluded.normalized_set_code ELSE sam_card_families.normalized_set_code END,
             card_number=CASE WHEN sam_card_families.card_number=''
                              THEN excluded.card_number ELSE sam_card_families.card_number END,
             canonical_name=CASE WHEN sam_card_families.canonical_name=''
                                 THEN excluded.canonical_name ELSE sam_card_families.canonical_name END,
             normalized_name=CASE WHEN sam_card_families.normalized_name=''
                                  THEN excluded.normalized_name ELSE sam_card_families.normalized_name END,
             updated_at=excluded.updated_at""",
        (
            f"SAM-FAMILY-{uuid.uuid4()}", game_text, key, set_text, number_text,
            name_text, normalize_name(name_text), _json(dict(external_descriptors or {})), now, now,
        ),
    )
    return dict(db.execute(
        "SELECT * FROM sam_card_families WHERE game=? AND family_key=?", (game_text, key)
    ).fetchone())


def _printing_descriptors(reference: Mapping | sqlite3.Row) -> dict:
    variant = clean(_value(reference, "variant"), 120)
    printing = clean(_value(reference, "printing"), 120)
    rarity = clean(_value(reference, "rarity"), 80)
    language = clean(_value(reference, "language"), 60) or "Unknown"
    combined = " ".join((variant, printing, rarity)).upper()
    distinctive = not (
        variant.upper() in ("", "UNKNOWN", "STANDARD", "BASE")
        and printing.upper() in ("", "UNKNOWN", "ORIGINAL", "STANDARD", "BASE")
    )
    requirements: list[str] = []
    if any(token in combined for token in ("ALT", "ALTERNATE", "PARALLEL", "MANGA")):
        requirements.append("ARTWORK_MATCH")
    if re.search(r"\bSP\b|SPECIAL RARE", combined):
        requirements.append("SP_MARKER")
    if re.search(r"(?:^|\s)(?:R|SR|SEC)\*", combined):
        requirements.append("STARRED_RARITY_MARKER")
    if any(token in combined for token in ("FOIL", "HOLO", "TEXTURED")):
        requirements.append("FINISH_PATTERN")
    for label, marker in (
        ("WINNER", "WINNER_MARKER"), ("JUDGE", "JUDGE_MARKER"),
        ("REGIONAL", "REGIONAL_MARKER"), ("STAMP", "PROMO_STAMP"),
    ):
        if label in combined:
            requirements.append(marker)
    return {
        "variant_label": variant,
        "printing_label": printing,
        "rarity_treatment": rarity,
        "language": language,
        "distinctive": distinctive,
        "required_markers": sorted(set(requirements)),
    }


def ensure_reference_identity(
    db: sqlite3.Connection, reference: Mapping | sqlite3.Row
) -> dict | None:
    family = ensure_family(
        db,
        game=_value(reference, "game", "One Piece"),
        set_code=_value(reference, "set_code"),
        card_number=_value(reference, "card_number"),
        name=_value(reference, "card_name"),
        external_descriptors={
            "metadata_provider": clean(_value(reference, "metadata_provider"), 80),
            "metadata_source_key": clean(_value(reference, "metadata_source_key"), 120),
            "authority": False,
        },
    )
    if not family:
        return None
    descriptors = _printing_descriptors(reference)
    printing = None
    if descriptors["distinctive"]:
        printing_key_source = "|".join((
            descriptors["variant_label"].upper(), descriptors["printing_label"].upper(),
            descriptors["rarity_treatment"].upper(), descriptors["language"].upper(),
        ))
        key = hashlib.sha256(printing_key_source.encode()).hexdigest()
        now = utcnow()
        db.execute(
            """INSERT INTO sam_commercial_printings
                 (printing_uuid,family_id,printing_key,artwork_identity,variant_label,
                  rarity_treatment,language,special_designation,catalog_source,
                  evidence_requirements,authority_state,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,'DESCRIPTIVE',?,?)
               ON CONFLICT(family_id,printing_key) DO UPDATE SET updated_at=excluded.updated_at""",
            (
                f"SAM-PRINTING-{uuid.uuid4()}", family["id"], key,
                descriptors["printing_label"], descriptors["variant_label"],
                descriptors["rarity_treatment"], descriptors["language"],
                descriptors["printing_label"], clean(_value(reference, "metadata_provider"), 80),
                _json({"required_markers": descriptors["required_markers"],
                       "source": "REFERENCE_DESCRIPTION", "authority": False}), now, now,
            ),
        )
        printing = dict(db.execute(
            "SELECT * FROM sam_commercial_printings WHERE family_id=? AND printing_key=?",
            (family["id"], key),
        ).fetchone())
    reference_id = int(_value(reference, "id"))
    db.execute(
        """INSERT INTO sam_reference_asset_links
             (reference_id,family_id,printing_id,asset_scope,certainty,provenance,evidence,linked_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(reference_id) DO UPDATE SET
             family_id=excluded.family_id,printing_id=excluded.printing_id,
             asset_scope=excluded.asset_scope,certainty=excluded.certainty,
             provenance=excluded.provenance,evidence=excluded.evidence,linked_at=excluded.linked_at""",
        (
            reference_id, family["id"], printing["id"] if printing else None,
            "PRINTING" if printing else "FAMILY", "HIGH_CONFIDENCE_SUGGESTION",
            "LOCAL_REFERENCE_DESCRIPTION",
            _json({"reference_sha256": clean(_value(reference, "sha256"), 80),
                   "descriptors": descriptors, "authority": False}), utcnow(),
        ),
    )
    return {"family": family, "printing": printing, "descriptors": descriptors}


def reference_identity(db: sqlite3.Connection, reference_id: int) -> dict | None:
    row = db.execute(
        """SELECT l.asset_scope,l.certainty,l.provenance,l.evidence,
                  f.id AS family_id,f.family_uuid,f.family_key,f.card_number AS family_card_number,
                  f.canonical_name AS family_name,f.normalized_set_code AS family_set_code,
                  p.id AS commercial_printing_id,p.printing_uuid,p.variant_label,p.artwork_identity,
                  p.rarity_treatment,p.finish,p.language AS printing_language,p.special_designation,
                  p.stamp_marking,p.promo_release,p.evidence_requirements,p.authority_state
             FROM sam_reference_asset_links l
             JOIN sam_card_families f ON f.id=l.family_id
             LEFT JOIN sam_commercial_printings p ON p.id=l.printing_id
            WHERE l.reference_id=?""",
        (reference_id,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["evidence"] = _loads(result.get("evidence"), {})
    result["evidence_requirements"] = _loads(result.get("evidence_requirements"), {})
    return result


def family_printing_candidates(
    db: sqlite3.Connection,
    family_id: int | None,
    recognition_candidates: Sequence[Mapping],
    scan_quality: Mapping | None = None,
) -> list[dict]:
    """Gather every documented same-family printing and explain visual evidence.

    The family matcher supplies visual scores for references it actually
    compared.  Missing scores and obstructed scans remain unresolved; they are
    never converted into confident negative evidence.
    """
    if not family_id:
        return []
    by_reference = {int(item.get("id") or 0): item for item in recognition_candidates}
    warnings = set((scan_quality or {}).get("warnings") or [])
    inconclusive_scan = bool(warnings & {
        "INSUFFICIENT_CARD_AREA", "SCAN_IMAGE_UNREADABLE", "NO_FRONT_SCAN",
    })
    rows = db.execute(
        """SELECT p.*,l.reference_id,r.width,r.height,r.file_size,
                  r.duplicate_of_reference_id,l.provenance,l.evidence AS link_evidence
             FROM sam_commercial_printings p
             LEFT JOIN sam_reference_asset_links l ON l.printing_id=p.id
             LEFT JOIN sam_reference_records r ON r.id=l.reference_id
            WHERE p.family_id=? AND p.active=1
            ORDER BY p.id,l.reference_id""",
        (family_id,),
    ).fetchall()
    grouped: dict[int, dict] = {}
    for row in rows:
        printing_id = int(row["id"])
        item = grouped.setdefault(printing_id, {
            "family_id": int(family_id), "commercial_printing_id": printing_id,
            "printing_id": printing_id, "printing_uuid": row["printing_uuid"],
            "variant_label": row["variant_label"], "artwork_identity": row["artwork_identity"],
            "rarity_treatment": row["rarity_treatment"], "finish": row["finish"],
            "language": row["language"], "special_designation": row["special_designation"],
            "stamp_marking": row["stamp_marking"], "promo_release": row["promo_release"],
            "evidence_requirements": _loads(row["evidence_requirements"], {}),
            "reference_ids": [], "visual_score": 0.0, "reference_quality_score": 1.0,
            "quality_warnings": [], "evidence_observations": [],
            "reference_evidence": [],
        })
        reference_id = int(row["reference_id"] or 0)
        if not reference_id:
            continue
        item["reference_ids"].append(reference_id)
        candidate = by_reference.get(reference_id)
        visual_score = float(candidate.get("visual_score") or 0) if candidate else 0.0
        if candidate:
            item["visual_score"] = max(item["visual_score"], visual_score)
        asset_warnings = []
        if row["duplicate_of_reference_id"]:
            asset_warnings.append("REFERENCE_ASSET_TWIN")
        if not row["width"] or not row["height"] or min(int(row["width"] or 0), int(row["height"] or 0)) < 250:
            asset_warnings.append("LOW_RESOLUTION_REFERENCE")
        if int(row["file_size"] or 0) < 10_000:
            asset_warnings.append("SMALL_REFERENCE_ASSET")
        item["quality_warnings"].extend(code for code in asset_warnings if code not in item["quality_warnings"])
        if asset_warnings:
            item["reference_quality_score"] = min(item["reference_quality_score"], 0.85)
        item["reference_evidence"].append({
            "reference_id": reference_id, "visual_score": visual_score,
            "quality_warnings": asset_warnings,
        })
    for item in grouped.values():
        reference_evidence = item.pop("reference_evidence")
        if not reference_evidence:
            reference_evidence = [{"reference_id": None, "visual_score": 0.0, "quality_warnings": []}]
        for asset in reference_evidence:
            visual = float(asset["visual_score"] or 0)
            poor_asset = bool(asset["quality_warnings"])
            if inconclusive_scan or visual == 0:
                artwork_state = "UNRESOLVED"
                explanation = "Artwork evidence is unavailable or the relevant scan/reference is inconclusive."
            elif poor_asset and visual < ARTWORK_PRESENT_MINIMUM:
                artwork_state = "UNRESOLVED"
                explanation = "This reference asset disagrees visually but is too weak to support confident negative evidence."
            elif visual >= ARTWORK_PRESENT_MINIMUM:
                artwork_state = "PRESENT"
                explanation = "Whole-card visual similarity meets the existing visual-evidence minimum."
            elif visual <= ARTWORK_ABSENT_MAXIMUM:
                artwork_state = "ABSENT_CONFIDENT"
                explanation = "A readable scan strongly disagrees with this printing's linked artwork."
            else:
                artwork_state = "UNRESOLVED"
                explanation = "Artwork similarity is not decisive enough to include or eliminate this printing."
            item["evidence_observations"].append({
                "evidence_type": "ARTWORK_MATCH", "state": artwork_state,
                "confidence": visual if visual else None, "source_kind": "SYSTEM_VISUAL",
                "reference_id": asset["reference_id"], "explanation": explanation,
            })
        for marker in (item["evidence_requirements"] or {}).get("required_markers", []):
            if marker == "ARTWORK_MATCH":
                continue
            item["evidence_observations"].append({
                "evidence_type": marker, "state": "UNRESOLVED", "confidence": None,
                "source_kind": "REFERENCE_METADATA", "reference_id": None,
                "explanation": "The printing requires this marker, but the current local evidence path cannot verify it.",
            })
        if item["quality_warnings"]:
            item["evidence_observations"].append({
                "evidence_type": "REFERENCE_ASSET_QUALITY", "state": "UNRESOLVED",
                "confidence": item["reference_quality_score"], "source_kind": "REFERENCE_METADATA",
                "reference_id": item["reference_ids"][0] if item["reference_ids"] else None,
                "explanation": ", ".join(item["quality_warnings"]),
            })
    return list(grouped.values())


def record_printing_evidence_observations(
    db: sqlite3.Connection, *, job_id: int, family_id: int | None,
    candidates: Sequence[Mapping],
) -> int:
    if not family_id:
        return 0
    count = 0
    now = utcnow()
    for candidate in candidates:
        printing_id = int(candidate.get("printing_id") or candidate.get("commercial_printing_id") or 0) or None
        for observation in candidate.get("evidence_observations") or []:
            state = clean(observation.get("state"), 40).upper()
            if state not in MARKER_STATES:
                raise ValueError("Printing marker state is not supported")
            source_kind = clean(observation.get("source_kind"), 40).upper() or "REFERENCE_METADATA"
            confidence = observation.get("confidence")
            reference_id = int(observation.get("reference_id") or 0) or None
            # Some pre-Phase-1 fixtures deliberately contain descriptive link
            # IDs without the referenced asset row.  Preserve the observation
            # without inventing a foreign reference relationship.
            if reference_id and not db.execute(
                "SELECT 1 FROM sam_reference_records WHERE id=?", (reference_id,)
            ).fetchone():
                reference_id = None
            db.execute(
                """INSERT INTO sam_printing_evidence_observations
                     (observation_uuid,job_id,family_id,printing_id,reference_id,evidence_type,
                      observed_state,numeric_confidence,source_kind,explanation,evidence,observed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"SAM-PRINT-EVID-{uuid.uuid4()}", job_id, family_id, printing_id,
                    reference_id, clean(observation.get("evidence_type"), 100),
                    state, confidence, source_kind, clean(observation.get("explanation"), 1000),
                    _json({"authority_granted": False,
                           "evidence_version": PRINTING_EVIDENCE_VERSION}), now,
                ),
            )
            count += 1
    return count


def printing_evidence_observations(db: sqlite3.Connection, job_id: int) -> list[dict]:
    rows = []
    for row in db.execute(
        "SELECT * FROM sam_printing_evidence_observations WHERE job_id=? ORDER BY printing_id,id",
        (job_id,),
    ).fetchall():
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), {})
        rows.append(item)
    return rows


def evaluate_printing_candidates(
    candidates: Sequence[Mapping],
    family_id: int | None,
    marker_states: Mapping[str, str] | None = None,
) -> dict:
    states = {clean(key, 80): clean(value, 40).upper() for key, value in (marker_states or {}).items()}
    invalid_states = sorted(value for value in states.values() if value not in MARKER_STATES)
    if invalid_states:
        raise ValueError("Printing marker state is not supported")
    printings: dict[int, dict] = {}
    for candidate in candidates:
        if int(candidate.get("family_id") or 0) != int(family_id or 0):
            continue
        printing_id = int(candidate.get("commercial_printing_id") or 0)
        if not printing_id:
            continue
        current = printings.setdefault(printing_id, {
            "printing_id": printing_id,
            "printing_uuid": candidate.get("printing_uuid"),
            "variant_label": candidate.get("variant_label") or candidate.get("variant") or "",
            "artwork_identity": candidate.get("artwork_identity") or candidate.get("printing") or "",
            "rarity_treatment": candidate.get("rarity_treatment") or candidate.get("rarity") or "",
            "confidence": 0.0,
            "required_markers": list((candidate.get("evidence_requirements") or {}).get("required_markers", [])),
            "incompatible_markers": list((candidate.get("evidence_requirements") or {}).get("incompatible_markers", [])),
            "reference_ids": [], "reference_quality_score": 1.0,
            "quality_warnings": [], "evidence_observations": [],
            "challenger_shadow": False,
        })
        current["confidence"] = max(current["confidence"], float(candidate.get("visual_score") or 0))
        current["reference_quality_score"] = min(
            current["reference_quality_score"], float(candidate.get("reference_quality_score") or 1)
        )
        current["quality_warnings"].extend(
            code for code in candidate.get("quality_warnings", []) if code not in current["quality_warnings"]
        )
        current["challenger_shadow"] = current["challenger_shadow"] or bool(candidate.get("challenger_shadow"))
        current["reference_ids"].extend(candidate.get("reference_ids") or [candidate.get("id")])
        current["evidence_observations"].extend(candidate.get("evidence_observations") or [])
    if not printings:
        return {
            "candidate": None, "confidence": 0.0, "certainty": "UNRESOLVED",
            "unresolved_reason": "NO_PROVEN_COMMERCIAL_PRINTING_CANDIDATE",
            "marker_evidence": [], "competing_printings": [], "authority_granted": False,
            "evidence_version": PRINTING_EVIDENCE_VERSION,
        }
    evaluated = []
    for printing in printings.values():
        evidence_by_type: dict[str, list[dict]] = {}
        for observation in printing["evidence_observations"]:
            evidence_type = clean(observation.get("evidence_type"), 100)
            state = clean(observation.get("state"), 40).upper()
            if state not in MARKER_STATES:
                raise ValueError("Printing marker state is not supported")
            evidence_by_type.setdefault(evidence_type, []).append({
                "marker": evidence_type, "state": state,
                "confidence": observation.get("confidence"),
                "source_kind": observation.get("source_kind") or "REFERENCE_METADATA",
                "reference_id": observation.get("reference_id"),
                "explanation": observation.get("explanation") or "",
            })
        for marker, state in states.items():
            evidence_by_type.setdefault(marker, []).append({
                "marker": marker, "state": state, "confidence": None,
                "source_kind": "OPERATOR", "reference_id": None,
                "explanation": "Explicit supplied evidence state.",
            })
        evidence = [item for values in evidence_by_type.values() for item in values]
        excluded = False
        conflicting = False
        all_present = bool(printing["required_markers"])
        for marker in printing["required_markers"]:
            observed = evidence_by_type.get(marker) or [{"state": "UNRESOLVED"}]
            marker_states_seen = {item["state"] for item in observed}
            if "PRESENT" in marker_states_seen and "ABSENT_CONFIDENT" in marker_states_seen:
                conflicting = True
            if "ABSENT_CONFIDENT" in marker_states_seen:
                excluded = True
            if marker_states_seen != {"PRESENT"}:
                all_present = False
        for marker in printing["incompatible_markers"]:
            observed = evidence_by_type.get(marker) or [{"state": "UNRESOLVED"}]
            marker_states_seen = {item["state"] for item in observed}
            if "PRESENT" in marker_states_seen and "ABSENT_CONFIDENT" in marker_states_seen:
                conflicting = True
            if "PRESENT" in marker_states_seen:
                excluded = True
        quality_adjusted = float(printing["confidence"]) * float(printing["reference_quality_score"])
        positive_count = sum(1 for item in evidence if item["state"] == "PRESENT")
        ranking_score = min(0.9999, quality_adjusted + min(0.05, positive_count * 0.015))
        evaluated.append({**printing, "confidence": round(quality_adjusted, 4),
                          "ranking_score": round(ranking_score, 4), "marker_evidence": evidence,
                          "excluded_by_negative_evidence": excluded,
                          "positive_evidence_complete": all_present,
                          "conflicting_evidence": conflicting,
                          "explanation": (
                              "Excluded because required positive evidence is confidently absent."
                              if excluded else "All required positive evidence is present."
                              if all_present else "Plausible, but required evidence remains unresolved."
                          )})
    evaluated.sort(key=lambda item: (-item["ranking_score"], item["printing_id"]))
    for rank, item in enumerate(evaluated, start=1):
        item["rank"] = rank
    viable = [item for item in evaluated if not item["excluded_by_negative_evidence"]]
    evidence_conflicts = [item for item in evaluated if item["conflicting_evidence"]]
    proven = [item for item in viable if item["positive_evidence_complete"]]
    if evidence_conflicts:
        return {
            "candidate": None, "confidence": 0.0, "certainty": "CONFLICTING",
            "unresolved_reason": "CONTRADICTORY_PRINTING_EVIDENCE",
            "marker_evidence": evidence_conflicts[0]["marker_evidence"],
            "competing_printings": evaluated, "authority_granted": False,
            "evidence_version": PRINTING_EVIDENCE_VERSION,
        }
    if len(proven) == 1:
        return {
            "candidate": proven[0], "confidence": proven[0]["confidence"],
            "certainty": "HIGH_CONFIDENCE_SUGGESTION", "unresolved_reason": "",
            "marker_evidence": proven[0]["marker_evidence"],
            "competing_printings": evaluated, "authority_granted": False,
            "evidence_version": PRINTING_EVIDENCE_VERSION,
        }
    reason = (
        "CONFLICTING_POSITIVE_PRINTING_EVIDENCE" if len(proven) > 1 else
        "REQUIRED_PRINTING_MARKER_ABSENT" if not viable else
        "SAME_FAMILY_PRINTING_COLLISION" if len(viable) > 1 else
        "POSITIVE_PRINTING_EVIDENCE_NOT_OBSERVED"
    )
    return {
        "candidate": viable[0] if len(viable) == 1 else None,
        "confidence": viable[0]["confidence"] if len(viable) == 1 else 0.0,
        "certainty": "CONFLICTING" if len(proven) > 1 else "UNRESOLVED",
        "unresolved_reason": reason, "marker_evidence": [],
        "competing_printings": evaluated, "authority_granted": False,
        "evidence_version": PRINTING_EVIDENCE_VERSION,
    }


def record_assertion(
    db: sqlite3.Connection, *, card_id: int, field_scope: str, certainty: str,
    actor: str, job_id: int | None = None, legacy_decision_id: int | None = None,
    family_id: int | None = None, printing_id: int | None = None,
    reference_id: int | None = None, proposed_value: str = "",
    confidence: float | None = None, authority_granted: bool = False,
    reason_code: str = "", notes: str = "", evidence: Mapping | None = None,
    supersedes_assertion_id: int | None = None,
) -> int:
    if certainty not in CERTAINTIES:
        raise ValueError("Identity certainty is not supported")
    if field_scope == "PRINTING" and authority_granted and (
        actor != "OPERATOR" or certainty != "OPERATOR_CONFIRMED"
    ):
        raise ValueError("Exact printing authority requires an explicit operator confirmation")
    if field_scope == "PRINTING" and printing_id:
        printing = db.execute(
            "SELECT family_id FROM sam_commercial_printings WHERE id=?", (printing_id,)
        ).fetchone()
        if not printing:
            raise ValueError("Printing assertion requires a valid commercial printing")
        if family_id is None or int(printing["family_id"]) != int(family_id):
            raise ValueError("Printing assertion must belong to the asserted card family")
    cursor = db.execute(
        """INSERT INTO sam_identity_assertions
             (assertion_uuid,card_id,job_id,legacy_decision_id,field_scope,family_id,
              printing_id,reference_id,proposed_value,certainty,numeric_confidence,
              authority_granted,actor,reason_code,notes,evidence,supersedes_assertion_id,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-ASSERT-{uuid.uuid4()}", card_id, job_id, legacy_decision_id,
            field_scope, family_id, printing_id, reference_id, clean(proposed_value, 500),
            certainty, confidence, 1 if authority_granted else 0, actor,
            clean(reason_code, 100), clean(notes, 1200), _json(dict(evidence or {})),
            supersedes_assertion_id, utcnow(),
        ),
    )
    return int(cursor.lastrowid)


def record_event(
    db: sqlite3.Connection, *, request_id: str, card_id: int, event_type: str,
    certainty: str, actor: str, job_id: int | None = None,
    family_id: int | None = None, printing_id: int | None = None,
    reference_id: int | None = None, prior_family_id: int | None = None,
    prior_printing_id: int | None = None, reason_code: str = "", notes: str = "",
    evidence: Mapping | None = None, effective_at: str = "",
) -> int:
    if certainty not in CERTAINTIES:
        raise ValueError("Identity certainty is not supported")
    if event_type in ("PRINTING_CONFIRMED", "PRINTING_CORRECTED") and (
        actor != "OPERATOR" or certainty != "OPERATOR_CONFIRMED"
    ):
        raise ValueError("Exact printing authority requires an explicit operator confirmation")
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO sam_identity_decision_events
             (event_uuid,request_id,job_id,card_id,event_type,family_id,printing_id,
              reference_id,prior_family_id,prior_printing_id,certainty,actor,effective_at,
              recorded_at,reason_code,notes,evidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-ID-EVENT-{uuid.uuid4()}", clean(request_id, 160), job_id, card_id,
            event_type, family_id, printing_id, reference_id, prior_family_id,
            prior_printing_id, certainty, actor, clean(effective_at, 40) or now, now,
            clean(reason_code, 100), clean(notes, 1200), _json(dict(evidence or {})),
        ),
    )
    return int(cursor.lastrowid)


def identity_history(db: sqlite3.Connection, card_id: int) -> dict:
    assertions = []
    for row in db.execute(
        "SELECT * FROM sam_identity_assertions WHERE card_id=? ORDER BY id", (card_id,)
    ).fetchall():
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), {})
        assertions.append(item)
    events = []
    for row in db.execute(
        "SELECT * FROM sam_identity_decision_events WHERE card_id=? ORDER BY id", (card_id,)
    ).fetchall():
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), {})
        events.append(item)
    return {"assertions": assertions, "events": events}


def identity_payload(db: sqlite3.Connection, job_id: int, candidates: Sequence[Mapping]) -> dict:
    job = dict(db.execute("SELECT * FROM sam_recognition_jobs WHERE id=?", (job_id,)).fetchone())
    card = dict(db.execute("SELECT * FROM cards WHERE id=?", (job["card_id"],)).fetchone())
    top = candidates[0] if candidates else {}
    card_family_authoritative = bool(card.get("sam_family_id")) and card.get("sam_family_certainty") in (
        "AUTHORITATIVE", "OPERATOR_CONFIRMED"
    )
    card_printing_authoritative = bool(card.get("sam_printing_id")) and card.get("sam_printing_certainty") == "OPERATOR_CONFIRMED"
    latest_operator_printing = db.execute(
        """SELECT certainty,reason_code,created_at FROM sam_identity_assertions
             WHERE card_id=? AND field_scope='PRINTING' AND actor='OPERATOR'
             ORDER BY id DESC LIMIT 1""",
        (job["card_id"],),
    ).fetchone()
    family_id = int(
        (card.get("sam_family_id") if card_family_authoritative else None)
        or job.get("family_id") or top.get("family_id") or 0
    ) or None
    family = db.execute("SELECT * FROM sam_card_families WHERE id=?", (family_id,)).fetchone() if family_id else None
    printing_id = int(
        (card.get("sam_printing_id") if card_printing_authoritative else None)
        or job.get("printing_id") or top.get("commercial_printing_id") or 0
    ) or None
    printing = db.execute("SELECT * FROM sam_commercial_printings WHERE id=?", (printing_id,)).fetchone() if printing_id else None
    printing_evaluation = _loads(job.get("printing_evidence"), {})
    effective_printing_certainty = (
        "OPERATOR_CONFIRMED" if card_printing_authoritative else
        latest_operator_printing["certainty"] if latest_operator_printing else
        job.get("printing_certainty", "UNRESOLVED")
    )
    effective_printing_reason = (
        "" if card_printing_authoritative else
        latest_operator_printing["reason_code"] if latest_operator_printing else
        job.get("printing_unresolved_reason", "PRINTING_NOT_EVALUATED")
    )
    # Phase 2 stores the complete same-family evaluation in the job.  Do not
    # reconstruct it from the five presentation candidates, which can omit
    # legitimate commercial printings and their negative/unresolved evidence.
    same_family = list(printing_evaluation.get("competing_printings") or [])
    legacy_conflicts = []
    if printing:
        comparisons = (
            ("variant", card.get("variant"), printing["variant_label"] or printing["artwork_identity"]),
            ("rarity", card.get("rarity"), printing["rarity_treatment"]),
        )
        for field, legacy_value, proposed_value in comparisons:
            legacy_text = str(legacy_value or "").strip()
            proposed_text = str(proposed_value or "").strip()
            if legacy_text and proposed_text and legacy_text.casefold() != proposed_text.casefold():
                legacy_conflicts.append({
                    "field": field,
                    "legacy_value": legacy_text,
                    "proposed_value": proposed_text,
                    "state": "CONFLICTING",
                    "reason": "LEGACY_VALUE_DISAGREES_WITH_PRINTING_SUGGESTION",
                })
    return {
        "family": {
            "family_id": family_id, "family_uuid": family["family_uuid"] if family else None,
            "card_number": family["card_number"] if family else top.get("card_number"),
            "canonical_name": family["canonical_name"] if family else top.get("card_name"),
            "set_code": family["normalized_set_code"] if family else top.get("set_code"),
            "confidence": float(job.get("family_confidence") or job.get("confidence") or 0),
            "certainty": card.get("sam_family_certainty") if card_family_authoritative else job.get("family_certainty", "UNRESOLVED"),
            "authoritative": card_family_authoritative,
        },
        "printing": {
            "printing_id": printing_id,
            "printing_uuid": printing["printing_uuid"] if printing else None,
            "variant_label": printing["variant_label"] if printing else None,
            "artwork_identity": printing["artwork_identity"] if printing else None,
            "confidence": float(job.get("printing_confidence") or 0),
            "certainty": effective_printing_certainty,
            "authoritative": card_printing_authoritative,
            "unresolved_reason": effective_printing_reason,
            "positive_evidence": printing_evaluation,
            "competing_same_family_printings": same_family,
            "legacy_conflicts": legacy_conflicts,
        },
        "reference_assets": [
            {
                "reference_id": candidate.get("id"), "image_url": candidate.get("image_url"),
                "asset_scope": candidate.get("asset_scope") or "FAMILY",
                "family_id": candidate.get("family_id"),
                "printing_id": candidate.get("commercial_printing_id"),
                "certainty": candidate.get("certainty") or "HIGH_CONFIDENCE_SUGGESTION",
                "provenance": candidate.get("provenance") or "LOCAL_REFERENCE_DESCRIPTION",
            }
            for candidate in candidates
        ],
        "language": {
            "value": printing["language"] if printing else top.get("language") or "Unknown",
            "certainty": card.get("sam_language_certainty", "LEGACY_RECORDED"),
            "authoritative": False,
            "authority_boundary": "DESCRIPTIVE_UNTIL_SEPARATELY_CONFIRMED",
        },
        "finish": {
            "value": printing["finish"] if printing else "",
            "certainty": card.get("sam_finish_certainty", "LEGACY_RECORDED"),
            "authoritative": False,
            "authority_boundary": "DESCRIPTIVE_UNTIL_SEPARATELY_CONFIRMED",
        },
        "condition": {
            "value": card.get("condition"),
            "certainty": "LEGACY_RECORDED",
            "authoritative": False,
            "authority_boundary": "OUTSIDE_SAM_PHASE1",
        },
        "inventory": {
            "family_id": card.get("sam_family_id"), "printing_id": card.get("sam_printing_id"),
            "legacy_variant": card.get("variant"),
            "legacy_rarity": card.get("rarity"),
            "legacy_variant_provenance": card.get("sam_legacy_identity_provenance", "LEGACY_RECORDED"),
            "legacy_conflicts": legacy_conflicts,
            "language_certainty": card.get("sam_language_certainty", "LEGACY_RECORDED"),
            "finish_certainty": card.get("sam_finish_certainty", "LEGACY_RECORDED"),
        },
        "history": identity_history(db, int(job["card_id"])),
        "authority_boundary": "FAMILY_AUTHORITY_NEVER_IMPLIES_PRINTING_AUTHORITY",
    }
