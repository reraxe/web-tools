from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


PIPELINE_VERSION = "vision-intake-poc-v0.3.0-core-recognition-handoff"
CLASSICAL_ENGINE_VERSION = "classical-geometry-v0.2.0-geometry-repair"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class SourceProfile(str, Enum):
    FLATBED = "FLATBED"
    FEED_SCANNER = "FEED_SCANNER"
    OVERHEAD_CAMERA = "OVERHEAD_CAMERA"
    PHONE_PHOTO = "PHONE_PHOTO"
    LIVE_CAMERA = "LIVE_CAMERA"
    UNKNOWN = "UNKNOWN"


class QualityState(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    ABSTAIN = "ABSTAIN"


class CornerVisibility(str, Enum):
    VISIBLE = "VISIBLE"
    OCCLUDED = "OCCLUDED"
    OUT_OF_FRAME = "OUT_OF_FRAME"
    UNCERTAIN = "UNCERTAIN"


class GeometryProvider(str, Enum):
    CLASSICAL = "CLASSICAL"
    LEARNED = "LEARNED"
    MANUAL = "MANUAL"


class RoutingMode(str, Enum):
    CLASSICAL_FIRST = "CLASSICAL_FIRST"
    LEARNED_FIRST = "LEARNED_FIRST"
    PARALLEL = "PARALLEL"


class ArbitrationDecision(str, Enum):
    SELECT_CLASSICAL = "SELECT_CLASSICAL"
    SELECT_LEARNED = "SELECT_LEARNED"
    SELECT_MANUAL = "SELECT_MANUAL"
    AGREED_CLASSICAL = "AGREED_CLASSICAL"
    AGREED_LEARNED = "AGREED_LEARNED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def to_list(self) -> list[float]:
        return [float(self.x), float(self.y)]


@dataclass(frozen=True)
class Corner:
    point: Point
    visibility: CornerVisibility = CornerVisibility.VISIBLE
    uncertainty_px: float | None = None


@dataclass(frozen=True)
class GeometryEvidence:
    convex: bool
    ordered: bool
    aspect_ratio: float | None
    aspect_plausible: bool
    area_ratio: float
    edge_support: float
    completeness: float
    source_boundary_contact: float
    holder_ambiguity: float
    transform_condition: float | None = None
    analysis_profile: str | None = None
    raw_signals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeometryProposal:
    proposal_id: str
    provider: GeometryProvider
    corners: tuple[Corner, Corner, Corner, Corner]
    evidence: GeometryEvidence
    instance_probability: float | None = None
    model_version: str | None = None

    def points(self) -> list[list[float]]:
        return [corner.point.to_list() for corner in self.corners]


@dataclass(frozen=True)
class VisualQualityEvidence:
    width: int
    height: int
    blur_score: float | None
    motion_blur_score: float | None
    glare_ratio: float | None
    illumination_uniformity: float | None
    occlusion_ratio: float | None
    compression_score: float | None
    useful_region_quality: float | None
    sleeve_interference: float | None
    holder_interference: float | None
    raw_signals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityDecision:
    state: QualityState
    reason_codes: tuple[str, ...]
    geometry_reliability: str
    visual_utility: str


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    sha256: str
    original_path: str
    mime_type: str
    encoding: str | None
    byte_size: int
    pixel_width: int
    pixel_height: int
    source_profile: SourceProfile
    exif_orientation: int | None
    exif_orientation_interpretation: str
    processing_timestamp: str
    processing_request_id: str


@dataclass(frozen=True)
class ArbitrationRecord:
    decision: ArbitrationDecision
    selected_proposal_id: str | None
    reason_codes: tuple[str, ...]
    mean_corner_distance_px: float | None
    normalized_corner_disagreement: float | None


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    source_id: str
    processing_request_id: str
    created_at: str
    pipeline_version: str
    classical_engine_version: str | None
    learned_model_version: str | None
    routing_mode: RoutingMode
    proposals: tuple[GeometryProposal, ...]
    arbitration: ArbitrationRecord
    geometry_metrics: dict[str, Any]
    visual_quality: VisualQualityEvidence | None
    quality: QualityDecision
    latency_ms: dict[str, float]
    hardware_provider: str
    shadow_proposals: tuple[GeometryProposal, ...] = ()


@dataclass(frozen=True)
class DerivativeRecord:
    derivative_id: str
    source_id: str
    attempt_id: str
    created_at: str
    sha256: str
    path: str
    normalized_width: int
    normalized_height: int
    transform_matrix: tuple[tuple[float, float, float], ...]
    crop_polygon: tuple[Point, Point, Point, Point]
    orientation_degrees: int
    correction_mode: str
    supersedes_derivative_id: str | None = None


@dataclass(frozen=True)
class SamHandoff:
    contract_version: str
    source_id: str
    original_reference: str
    preferred_derivative_reference: str | None
    alternate_orientation_references: tuple[str, ...]
    quality_state: QualityState
    quality_reason_codes: tuple[str, ...]
    attempt_id: str
    derivative_id: str | None
    geometry_metadata: dict[str, Any]
    pipeline_provenance: dict[str, Any]
    printing_artifact_preservation: dict[str, Any] = field(default_factory=dict)
    identity_authority: bool = False
    exact_printing_authority: bool = False
    review_derivative_reference: str | None = None
    recognition_input_policy: str = "RAW_PRIMARY"

    def __post_init__(self) -> None:
        if self.identity_authority:
            raise ValueError("Vision Intake may not grant identity authority")
        if self.exact_printing_authority:
            raise ValueError("Vision Intake may not grant exact-printing authority")
        if self.recognition_input_policy not in {
            "DERIVATIVE_PRIMARY",
            "RAW_PRIMARY_DERIVATIVE_REVIEW",
            "RAW_PRIMARY",
        }:
            raise ValueError("Unknown recognition input policy")
        if (
            self.recognition_input_policy == "DERIVATIVE_PRIMARY"
            and not self.preferred_derivative_reference
        ):
            raise ValueError("Derivative-primary handoff requires a preferred derivative")
        if (
            self.recognition_input_policy == "RAW_PRIMARY_DERIVATIVE_REVIEW"
            and not self.review_derivative_reference
        ):
            raise ValueError("Dual review handoff requires a review derivative")


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    return value


def points_to_corners(
    points: Iterable[Iterable[float]],
    visibility: CornerVisibility = CornerVisibility.VISIBLE,
) -> tuple[Corner, Corner, Corner, Corner]:
    converted = tuple(
        Corner(Point(float(pair[0]), float(pair[1])), visibility)
        for pair in points
    )
    if len(converted) != 4:
        raise ValueError("Exactly four ordered corners are required")
    return converted  # type: ignore[return-value]
