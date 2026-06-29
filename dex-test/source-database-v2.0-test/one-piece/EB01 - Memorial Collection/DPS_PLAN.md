# DPS Plan: Dex Pre-Grading System

Last updated: 2026-06-23

## Purpose

DPS, or **Dex Pre-Grading System**, is Dex's evidence-first condition screening tool for higher-value cards.

DPS is not an official PSA, Beckett, TAG, CGC, or third-party grading result. It is an internal pre-screen that helps decide:

- whether a card is worth grading
- what condition concerns exist
- what evidence supports the condition estimate
- whether the card should be sold raw, held, or submitted

## Core Principle

DPS should be measurement-first, not hype-first.

It should show evidence, measurements, and uncertainty rather than pretending it can magically guarantee a third-party grade.

## Capture Tools

Current available scanner:

- Canon PIXMA G6020 flatbed
- good for high-resolution straight-on scans
- avoids roller damage for higher-value cards

Recommended capture modes:

- 600 dpi flatbed scan for normal DPS review
- 1200 dpi flatbed scan for high-value cards
- PNG or TIFF preferred
- scanner auto-enhance disabled
- clean glass before each session

Optional future captures:

- angled/raking-light phone photos
- cross-light photos
- front/back closeups
- foil/surface texture photos

## What DPS Should Measure

### Capture Quality

- resolution
- focus/sharpness
- glare
- clipping/cut-off card edges
- skew/rotation
- visible full card boundary
- file format/compression quality

If capture quality is poor, DPS should refuse to force a score.

### Centering

- front left/right ratio
- front top/bottom ratio
- back left/right ratio
- back top/bottom ratio
- card border geometry

### Corners

- rounding consistency
- whitening
- dents
- bends
- missing material
- corner shape asymmetry

### Edges

- edge whitening
- chipping
- nicks
- rough cuts
- border wear

### Surface

- visible scratches
- print lines
- dents
- impressions
- stains
- roller marks
- gloss or foil anomalies

Flatbed scans can catch some surface issues, but not all. Surface review should improve with optional angled-light images.

### Print Quality

- print dots/noise
- misalignment
- ink issues
- obvious print defects
- color/contrast anomalies

## DPS Output

Each DPS report should include:

- card SKU
- card identity
- scan date
- scanner/capture settings
- capture quality status
- centering measurements
- corner observations
- edge observations
- surface observations
- print-quality observations
- evidence map or marked image areas
- sub-scores
- overall DPS condition range
- confidence level
- notes/recommendation

Example recommendation:

```text
Raw Sale Recommended
Reason: Centering is strong, but surface evidence is incomplete without angled-light capture.
```

## Differentiators

DPS should set itself apart by being transparent:

- exact centering ratios
- marked evidence regions
- defect coordinates
- severity labels
- capture-quality gate
- confidence score
- versioned scoring model
- repeatable report tied to physical SKU
- history of future scans against the same card

## Validation Plan

Start with small controlled tests:

- 10 known near-mint pack-fresh cards
- 10 cards with obvious edge/corner/surface issues
- 10 higher-value cards scanned carefully on flatbed
- 5 repeat scans of the same card to test consistency

Better validation later:

- 50-100 mixed-condition cards
- blind manual review before DPS result
- compare DPS findings to returned third-party grades
- track difference between DPS estimate and actual outcome

## Version Path

### v3.0-test: DPS Capture And Measurements

- Add DPS page.
- Upload/select front/back high-res scans.
- Validate capture quality.
- Measure card bounds and centering.
- Store DPS report tied to SKU.

### v3.1-test: Corners And Edges

- Add edge/corner evidence maps.
- Add manual correction tools.
- Add sub-scores.

### v3.2-test: Surface Evidence

- Add optional angled-light uploads.
- Add surface anomaly marking.
- Add surface confidence warnings.

### v3.3-test: Submission Support

- Add grading-cost math.
- Add expected value ranges.
- Add submit/sell raw/hold recommendations.
- Connect to Janna and Goose market signals.

## Safety Rules

- Never call DPS an official grade.
- Never promise near-100% grading accuracy.
- Never overwrite inventory condition without review.
- Always keep the original scans.
- Always store the DPS scoring version used for the report.
- Always show uncertainty when evidence is incomplete.

## Reality Boundary

Straight-on flatbed scans are strong for centering, corners, edges, and obvious print/surface defects. They cannot catch every scratch, dent, indentation, foil line, gloss issue, or texture problem. Some defects require angled light, magnification, depth, tactile inspection, or third-party human judgment.
