"""Shared Phase 1 foundations for Dex operational economics.

This module intentionally contains no database or UI behavior. Money is represented
as integer cents, and remainder cents are assigned by immutable stable identifier so
allocation does not depend on input order or presentation sorting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeAlias


CALCULATION_VERSION = "acquisition-rip-v3"

ACQUISITION_MODES = (
    "SEALED_RIP",
    "SINGLES_KNOWN_COST",
    "SINGLES_LUMP_SUM",
)
ORDER_TYPES = ("CARD", "SEALED")
RECYCLE_REASON_CODES = (
    "DUPLICATE_ENTRY_ERROR",
    "CORRECTION_HOLD",
    "DAMAGED",
    "MISSING_LOST",
    "OTHER",
)

StableIdentifier: TypeAlias = int | str


@dataclass(frozen=True)
class CentAllocation:
    stable_id: StableIdentifier
    cents: int


def _stable_sort_key(value: StableIdentifier) -> tuple[int, int | str]:
    if isinstance(value, bool):
        raise TypeError("Boolean values are not valid stable identifiers")
    if isinstance(value, int):
        return (0, value)
    if isinstance(value, str) and value:
        return (1, value)
    raise TypeError("Stable identifiers must be non-empty strings or integers")


def allocate_cents(
    total_cents: int,
    stable_ids: Iterable[StableIdentifier],
) -> tuple[CentAllocation, ...]:
    """Allocate a non-negative cent total in deterministic stable-ID order.

    Each recipient receives the equal base amount. Remainder cents go one at a time
    to the lowest immutable identifiers. Thus 1000 cents across IDs 1, 2, and 3 is
    always 334, 333, and 333 cents regardless of input or UI order.
    """

    if isinstance(total_cents, bool) or not isinstance(total_cents, int):
        raise TypeError("The allocation total must be an integer number of cents")
    if total_cents < 0:
        raise ValueError("The allocation total cannot be negative")

    recipients = list(stable_ids)
    ordered = sorted(recipients, key=_stable_sort_key)
    if len(set(ordered)) != len(ordered):
        raise ValueError("Stable identifiers must be unique")
    if not ordered:
        if total_cents == 0:
            return ()
        raise ValueError("A non-zero total requires at least one recipient")

    base, remainder = divmod(total_cents, len(ordered))
    allocations = tuple(
        CentAllocation(stable_id=stable_id, cents=base + (1 if index < remainder else 0))
        for index, stable_id in enumerate(ordered)
    )
    if sum(item.cents for item in allocations) != total_cents:
        raise AssertionError("Cent allocation failed to reconcile")
    return allocations


def allocate_weighted_cents(
    total_cents: int,
    weighted_stable_ids: Iterable[tuple[StableIdentifier, int]],
) -> tuple[CentAllocation, ...]:
    """Allocate a signed total by non-negative integer weights, exactly and stably.

    Fractional remainder cents go to the largest fractional remainders, with the
    immutable stable identifier as the tie-breaker. Zero total weight falls back to
    equal allocation. This is used to attribute historical order totals once across
    their existing sale items.
    """

    if isinstance(total_cents, bool) or not isinstance(total_cents, int):
        raise TypeError("The allocation total must be an integer number of cents")
    recipients = list(weighted_stable_ids)
    ordered = sorted(recipients, key=lambda item: _stable_sort_key(item[0]))
    ids = [item[0] for item in ordered]
    if len(set(ids)) != len(ids):
        raise ValueError("Stable identifiers must be unique")
    for stable_id, weight in ordered:
        _stable_sort_key(stable_id)
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise TypeError("Allocation weights must be integer values")
        if weight < 0:
            raise ValueError("Allocation weights cannot be negative")
    if not ordered:
        if total_cents == 0:
            return ()
        raise ValueError("A non-zero total requires at least one recipient")

    sign = -1 if total_cents < 0 else 1
    absolute_total = abs(total_cents)
    weight_total = sum(item[1] for item in ordered)
    if weight_total == 0:
        base, remainder = divmod(absolute_total, len(ordered))
        cents = [base + (1 if index < remainder else 0) for index in range(len(ordered))]
    else:
        numerators = [absolute_total * item[1] for item in ordered]
        cents = [numerator // weight_total for numerator in numerators]
        remainder = absolute_total - sum(cents)
        remainder_order = sorted(
            range(len(ordered)),
            key=lambda index: (
                -(numerators[index] % weight_total),
                _stable_sort_key(ordered[index][0]),
            ),
        )
        for index in remainder_order[:remainder]:
            cents[index] += 1

    allocations = tuple(
        CentAllocation(stable_id=ordered[index][0], cents=sign * cents[index])
        for index in range(len(ordered))
    )
    if sum(item.cents for item in allocations) != total_cents:
        raise AssertionError("Weighted cent allocation failed to reconcile")
    return allocations
