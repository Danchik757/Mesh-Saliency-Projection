"""
Shared processed-fixation and timing loader for all benchmark evaluators.

Processing flow
---------------
Two timing contracts are supported:

  cropped_reset (legacy, offset_2000 data):
    1. Skip crop_start_frames = round(1.8 * fps) from the start.
    2. Skip crop_end_frames   = round(0.2 * fps) from the end.
    3. Pair processed_gaze[k] -> placement[placement_start + k].
    4. Validates exact frame count and full-turn coverage.

  one_turn_from_start (new, offset_0 data):
    1. Compute turn_frames = round(abs(360 / rotation_speed) * fps).
    2. Apply optional delay: gaze_start = max(0, delay_frames),
       placement_start = max(0, -delay_frames).
    3. Pair processed_gaze[gaze_start + k] -> placement[placement_start + k]
       for k in range(turn_frames).
    4. Extra frames beyond one turn are truncated from the end (not an error).
    5. Validates that enough frames exist; does NOT enforce exact file length.

Select the contract via timing_contract= parameter or REPROJECT_TIMING_CONTRACT env var.

Processed fixation JSON format:
    fixations[frame_index][point_index] = [x_px, y_px]

Output coordinates:
    GazeBatch.x_norm, y_norm are in [0, 1] (x_px / width, y_px / height).

Known blockers (Decision 4):
    3DVA_jessi      -- empty file (0 frames) in new format; raises InvalidFixationError
    SAL3D_gorgoile  -- missing file; raises MissingFixationError
Neither case falls back to CSV automatically.
"""

from __future__ import annotations

import ast
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Approved timing constants (DECISIONS_REQUIRED.md, Decision 3).
CROP_START_SECONDS: float = 1.8
CROP_END_SECONDS: float = 0.2

# Timing contract identifiers.
TIMING_CONTRACT_CROPPED_RESET: str = "cropped_reset"
TIMING_CONTRACT_ONE_TURN: str = "one_turn_from_start"

# Rotation-speed tolerance: one frame at the declared fps (fractional seconds).
# The validator uses the same rule from validate_data_contract.py.
_ROTATION_SPEED_REL_TOL: float = 1e-5
_ROTATION_SPEED_ABS_TOL: float = 1e-5

# Full-turn tolerance: ±1 frame at declared fps.
_FULL_TURN_FRAME_TOLERANCE: int = 1


# ── exceptions ────────────────────────────────────────────────────────────────

class ParticipantLoaderError(RuntimeError):
    """Base class for all loader errors."""


class MissingFixationError(ParticipantLoaderError):
    """Fixation file is absent (e.g. SAL3D_gorgoile)."""

    def __init__(self, canonical_name: str, path: Path) -> None:
        self.canonical_name = canonical_name
        self.path = path
        super().__init__(
            f"Processed fixation file not found for '{canonical_name}': {path}\n"
            "This model is a known blocker. Do not fall back to CSV."
        )


class InvalidFixationError(ParticipantLoaderError):
    """Fixation file exists but fails structural validation (e.g. 3DVA_jessi)."""

    def __init__(self, canonical_name: str, reason: str) -> None:
        self.canonical_name = canonical_name
        self.reason = reason
        super().__init__(
            f"Invalid processed fixation for '{canonical_name}': {reason}\n"
            "This model is a known blocker. Do not fall back to CSV."
        )


class TimingValidationError(ParticipantLoaderError):
    """Placement JSON fails timing or full-turn validation."""


class ResumeContractMismatchError(ParticipantLoaderError):
    """Existing report was produced with a different timing contract or data source."""

    def __init__(self, report_path: Path, field: str, existing: Any, expected: Any) -> None:
        self.report_path = report_path
        self.field = field
        self.existing = existing
        self.expected = expected
        super().__init__(
            f"Resume guard: existing report {report_path} was produced with "
            f"{field}={existing!r} but the current run expects {expected!r}. "
            "Delete the report or use a different output directory."
        )


def resolve_processed_fixation_path(fixation_path: Path) -> Path:
    """Resolve fixations.json with a case-insensitive parent fallback.

    Release archives should use canonical directory names, but some historical
    model ids differ only by case, for example `3DVA_rockerarm` vs
    `3DVA_rockerArm`. This keeps the processed-fixation contract intact while
    avoiding a false missing-data error for case-only directory mismatches.
    """
    parent = fixation_path.parent
    root = parent.parent
    if root.is_dir():
        target = parent.name.lower()
        matches = [
            candidate / fixation_path.name
            for candidate in root.iterdir()
            if candidate.is_dir()
            and candidate.name.lower() == target
            and (candidate / fixation_path.name).is_file()
        ]
        exact_matches = [p for p in matches if p.parent.name == parent.name]
        if exact_matches:
            return exact_matches[0]
        if len(matches) == 1:
            return matches[0]

    if fixation_path.is_file():
        return fixation_path
    return fixation_path


# ── data types ────────────────────────────────────────────────────────────────

@dataclass
class GazeBatch:
    """Per-frame gaze points in normalized screen coordinates.

    Compatible with the FrameGazeBatch interface used by all evaluators.
    Field names match so evaluators can switch by importing this type.
    """
    x_norm: "np.ndarray"  # shape (n_points,), values in [0, 1]
    y_norm: "np.ndarray"  # shape (n_points,), values in [0, 1]


@dataclass
class LoadedTrack:
    """Result of loading one model's gaze data paired with its placement JSON.

    gaze_batches keys are absolute placement frame indices (0-based).
    Iterate as: for frame_idx, batch in track.gaze_batches.items(): ...
    """
    # Identity
    canonical_name: str        # e.g. "3DVA_A380"
    dataset: str               # e.g. "3DVA"
    model: str                 # e.g. "A380"

    # Source paths
    fixation_path: Path        # processed JSON or CSV
    placement_path: Path

    # Placement metadata (from placement JSON)
    video_info: dict[str, Any]
    animation: dict[str, Any]
    fps: float
    total_frames: int
    width: int
    height: int

    # Timing window (0-based placement frame indices)
    crop_start_frames: int          # round(1.8 * fps)
    crop_end_frames: int            # round(0.2 * fps)
    placement_start: int            # = crop_start_frames
    placement_end_exclusive: int    # = total_frames - crop_end_frames
    usable_count: int               # = placement_end_exclusive - placement_start

    # Paired gaze data.  Key = absolute placement frame index in
    # [placement_start, placement_end_exclusive).
    gaze_batches: dict[int, GazeBatch]

    # Input mode for provenance
    input_mode: str            # "processed_json" | "csv_compat"

    # Provenance dict — embed verbatim in every report.
    provenance: dict[str, Any]


# ── placement JSON helpers ─────────────────────────────────────────────────────

def _load_placement(placement_path: Path) -> dict[str, Any]:
    if not placement_path.is_file():
        raise FileNotFoundError(f"Placement JSON not found: {placement_path}")
    return json.loads(placement_path.read_text())


def _derive_timing(placement: dict[str, Any], path: Path) -> dict[str, Any]:
    """Validate placement JSON and return timing metadata."""
    try:
        vi = placement["video_info"]
        fps = float(vi["fps"])
        total_frames = int(vi["total_frames"])
        duration = float(vi["duration_seconds"])
        width = int(vi["resolution_width"])
        height = int(vi["resolution_height"])
        anim = placement["animation"]
        rotation_speed = float(anim["rotation_speed_deg_per_sec"])
        frames = placement["frames"]
    except (KeyError, TypeError, ValueError) as exc:
        raise TimingValidationError(f"Malformed placement JSON {path}: {exc}") from exc

    if len(frames) != total_frames:
        raise TimingValidationError(
            f"{path}: frames array length {len(frames)} != total_frames {total_frames}"
        )

    # Validate rotation speed using declared duration (not last timestamp).
    # See validate_data_contract.py and DATA_CONTRACT.md for the rationale.
    unwrapped = _unwrap_rotation_degrees(frames)
    if len(unwrapped) >= 2:
        observed_speed = (unwrapped[-1] - unwrapped[0]) / duration
        if not math.isclose(
            observed_speed, rotation_speed,
            rel_tol=_ROTATION_SPEED_REL_TOL,
            abs_tol=_ROTATION_SPEED_ABS_TOL,
        ):
            raise TimingValidationError(
                f"{path}: observed rotation speed {observed_speed:.6f} deg/s "
                f"!= declared {rotation_speed:.6f} deg/s"
            )

    crop_start_frames = round(CROP_START_SECONDS * fps)
    crop_end_frames = round(CROP_END_SECONDS * fps)
    placement_start = crop_start_frames
    placement_end_exclusive = total_frames - crop_end_frames
    usable_count = placement_end_exclusive - placement_start

    if usable_count <= 0:
        raise TimingValidationError(
            f"{path}: usable_count={usable_count} after crop; "
            f"total_frames={total_frames}, crop=[{crop_start_frames}, {crop_end_frames}]"
        )

    # Validate that the usable window is one full turn (±1 frame tolerance).
    full_turn_seconds = abs(360.0 / rotation_speed)
    usable_seconds = usable_count / fps
    tolerance_seconds = _FULL_TURN_FRAME_TOLERANCE / fps + 1e-9
    if not math.isclose(usable_seconds, full_turn_seconds, abs_tol=tolerance_seconds):
        raise TimingValidationError(
            f"{path}: usable window {usable_seconds:.4f} s is not one full turn "
            f"{full_turn_seconds:.4f} s (tolerance ±{tolerance_seconds:.4f} s). "
            "Check placement JSON duration/rotation_speed."
        )

    return {
        "fps": fps,
        "total_frames": total_frames,
        "duration": duration,
        "width": width,
        "height": height,
        "rotation_speed": rotation_speed,
        "full_turn_seconds": full_turn_seconds,
        "crop_start_frames": crop_start_frames,
        "crop_end_frames": crop_end_frames,
        "placement_start": placement_start,
        "placement_end_exclusive": placement_end_exclusive,
        "usable_count": usable_count,
    }


def _derive_timing_one_turn(
    placement: dict[str, Any],
    path: Path,
    delay_seconds: float,
) -> dict[str, Any]:
    """Validate placement JSON and return timing for one_turn_from_start contract.

    Takes exactly one full rotation from frame 0 — no crop_start/crop_end.
    Fixation files longer than one turn are accepted; extra trailing frames
    are truncated during pairing.
    """
    try:
        vi = placement["video_info"]
        fps = float(vi["fps"])
        total_frames = int(vi["total_frames"])
        duration = float(vi["duration_seconds"])
        width = int(vi["resolution_width"])
        height = int(vi["resolution_height"])
        anim = placement["animation"]
        rotation_speed = float(anim["rotation_speed_deg_per_sec"])
        frames = placement["frames"]
    except (KeyError, TypeError, ValueError) as exc:
        raise TimingValidationError(f"Malformed placement JSON {path}: {exc}") from exc

    if len(frames) != total_frames:
        raise TimingValidationError(
            f"{path}: frames array length {len(frames)} != total_frames {total_frames}"
        )

    unwrapped = _unwrap_rotation_degrees(frames)
    if len(unwrapped) >= 2:
        observed_speed = (unwrapped[-1] - unwrapped[0]) / duration
        if not math.isclose(
            observed_speed, rotation_speed,
            rel_tol=_ROTATION_SPEED_REL_TOL,
            abs_tol=_ROTATION_SPEED_ABS_TOL,
        ):
            raise TimingValidationError(
                f"{path}: observed rotation speed {observed_speed:.6f} deg/s "
                f"!= declared {rotation_speed:.6f} deg/s"
            )

    turn_frames = round(abs(360.0 / rotation_speed) * fps)
    delay_frames = round(delay_seconds * fps)

    gaze_start = max(0, delay_frames)
    placement_start = max(0, -delay_frames)
    placement_end_exclusive = placement_start + turn_frames

    if placement_end_exclusive > total_frames:
        raise TimingValidationError(
            f"{path}: with delay_seconds={delay_seconds:.3f}, "
            f"placement_end_exclusive={placement_end_exclusive} > total_frames={total_frames}. "
            "Delay magnitude is too large for the available placement data."
        )

    return {
        "fps": fps,
        "total_frames": total_frames,
        "duration": duration,
        "width": width,
        "height": height,
        "rotation_speed": rotation_speed,
        "full_turn_seconds": abs(360.0 / rotation_speed),
        "turn_frames": turn_frames,
        "delay_frames": delay_frames,
        "gaze_start": gaze_start,
        "crop_start_frames": 0,
        "crop_end_frames": 0,
        "placement_start": placement_start,
        "placement_end_exclusive": placement_end_exclusive,
        "usable_count": turn_frames,
    }


def _unwrap_rotation_degrees(frames: list[dict]) -> list[float]:
    values: list[float] = []
    for frame in frames:
        if "rotation_z_degrees" in frame:
            angle = float(frame["rotation_z_degrees"])
        else:
            angle = math.degrees(float(frame["rotation_z_radians"]))
        if values:
            while angle - values[-1] > 180.0:
                angle -= 360.0
            while angle - values[-1] < -180.0:
                angle += 360.0
        values.append(angle)
    return values


def _build_provenance(
    *,
    canonical_name: str,
    dataset: str,
    model: str,
    fixation_path: Path,
    placement_path: Path,
    timing: dict[str, Any],
    input_mode: str,
    timing_contract: str = TIMING_CONTRACT_CROPPED_RESET,
    delay_frames: int = 0,
    fixation_data_tag: str | None = None,
) -> dict[str, Any]:
    prov: dict[str, Any] = {
        "input_mode": input_mode,
        "canonical_name": canonical_name,
        "dataset": dataset,
        "model": model,
        "fixation_source": str(fixation_path),
        "placement_source": str(placement_path),
        "fps": timing["fps"],
        "total_frames": timing["total_frames"],
        "video_duration_seconds": timing["duration"],
        "resolution": f"{timing['width']}x{timing['height']}",
        "timing_contract": timing_contract,
        "gaze_start_frame": timing.get("gaze_start", 0),
        "placement_start_frame": timing["placement_start"],
        "placement_end_frame_exclusive": timing["placement_end_exclusive"],
        "usable_count": timing["usable_count"],
        "turn_frame_count": timing.get("turn_frames", timing["usable_count"]),
        "delay_frames": delay_frames,
        "rotation_speed_deg_per_sec": timing["rotation_speed"],
        "full_turn_seconds": timing["full_turn_seconds"],
    }

    if timing_contract == TIMING_CONTRACT_CROPPED_RESET:
        prov.update({
            "fixation_format": "cropped_reset_offset_2000",
            "fixation_start_index": 0,
            "crop_start_seconds": CROP_START_SECONDS,
            "crop_end_seconds": CROP_END_SECONDS,
            "crop_start_frames": timing["crop_start_frames"],
            "crop_end_frames": timing["crop_end_frames"],
        })
    else:
        prov.update({
            "fixation_format": "one_turn_from_start_offset_0",
            "fixation_start_index": timing.get("gaze_start", 0),
            "crop_start_seconds": 0.0,
            "crop_end_seconds": 0.0,
            "crop_start_frames": 0,
            "crop_end_frames": 0,
        })

    if fixation_data_tag is not None:
        prov["fixation_data_tag"] = fixation_data_tag

    return prov


# ── processed JSON loader ─────────────────────────────────────────────────────

def load_processed_track(
    fixation_path: Path,
    placement_path: Path,
    *,
    dataset: str,
    model: str,
    canonical_name: str | None = None,
    timing_contract: str = TIMING_CONTRACT_CROPPED_RESET,
    delay_seconds: float = 0.0,
    fixation_data_tag: str | None = None,
) -> LoadedTrack:
    """Load a processed fixation JSON and pair with its placement JSON.

    Parameters
    ----------
    fixation_path:
        Path to fixations.json for this model.
    placement_path:
        Path to the canonical placement JSON.
    dataset:
        Dataset name, e.g. "3DVA", "MeshMamba_non_texture", "SAL3D".
    model:
        Canonical model name, e.g. "A380".
    canonical_name:
        Full canonical name, e.g. "3DVA_A380". Derived from dataset+model if
        omitted.
    timing_contract:
        "cropped_reset" (default): skip crop_start/crop_end seconds.
        "one_turn_from_start": take one full rotation from frame 0.
    delay_seconds:
        Only used with "one_turn_from_start". Positive = gaze leads placement
        (gaze_start = round(delay_seconds * fps)). Negative = gaze lags.
    fixation_data_tag:
        Optional label embedded in provenance (e.g. "mesh_json__offset_0").

    Raises
    ------
    MissingFixationError:
        Fixation file not found.
    InvalidFixationError:
        Fixation file fails structural validation (wrong frame count, bad
        coordinates, etc.).
    TimingValidationError:
        Placement JSON fails timing or full-turn validation.
    """
    import numpy as np  # deferred: not all callers need numpy

    if canonical_name is None:
        canonical_name = f"{dataset}_{model}"

    fixation_path = resolve_processed_fixation_path(fixation_path)
    if not fixation_path.is_file():
        raise MissingFixationError(canonical_name, fixation_path)

    placement = _load_placement(placement_path)

    if timing_contract == TIMING_CONTRACT_ONE_TURN:
        timing = _derive_timing_one_turn(placement, placement_path, delay_seconds)
    else:
        timing = _derive_timing(placement, placement_path)

    # Load and validate fixation JSON.
    try:
        raw: list = json.loads(fixation_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise InvalidFixationError(canonical_name, f"cannot read JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise InvalidFixationError(canonical_name, "top level must be a list of frames")

    if len(raw) == 0:
        raise InvalidFixationError(
            canonical_name,
            "fixation file is empty (0 frames); participant excluded from benchmark",
        )

    total_frames = timing["total_frames"]

    if timing_contract == TIMING_CONTRACT_ONE_TURN:
        gaze_start = timing["gaze_start"]
        turn_frames = timing["turn_frames"]
        required_gaze_frames = gaze_start + turn_frames
        if len(raw) < required_gaze_frames:
            raise InvalidFixationError(
                canonical_name,
                f"fixation frames {len(raw)} < required {required_gaze_frames} "
                f"(turn_frames={turn_frames}, gaze_start={gaze_start}, "
                f"delay_frames={timing['delay_frames']})",
            )
    else:
        gaze_start = 0
        usable_count_expected = timing["usable_count"]
        if len(raw) != usable_count_expected:
            raise InvalidFixationError(
                canonical_name,
                f"cropped fixation frames {len(raw)} != expected {usable_count_expected} "
                f"(total_frames={total_frames}, "
                f"crop_start={timing['crop_start_frames']}, crop_end={timing['crop_end_frames']})",
            )

    width = timing["width"]
    height = timing["height"]
    placement_start = timing["placement_start"]
    placement_end_exclusive = timing["placement_end_exclusive"]
    usable_count = timing["usable_count"]

    # Build gaze_batches.
    gaze_batches: dict[int, GazeBatch] = {}
    for k in range(usable_count):
        gaze_idx = gaze_start + k              # index into fixations.json
        frame_idx = placement_start + k        # absolute placement frame index

        frame_points = raw[gaze_idx]
        if not isinstance(frame_points, list):
            raise InvalidFixationError(
                canonical_name, f"frame {gaze_idx} is not a list"
            )

        xs: list[float] = []
        ys: list[float] = []
        for point in frame_points:
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)
            ):
                raise InvalidFixationError(
                    canonical_name, f"invalid point at frame {gaze_idx}: {point!r}"
                )
            x_px, y_px = float(point[0]), float(point[1])
            if x_px < 0 or x_px >= width or y_px < 0 or y_px >= height:
                # Out-of-bounds in a validated release file is a data-contract
                # violation (validate_data_contract.py confirms no valid release
                # file contains such points).  Raise rather than silently drop.
                raise InvalidFixationError(
                    canonical_name,
                    f"out-of-bounds pixel point at frame {gaze_idx}: "
                    f"[{x_px}, {y_px}] outside {width}x{height}",
                )
            xs.append(x_px / width)
            ys.append(y_px / height)

        gaze_batches[frame_idx] = GazeBatch(
            x_norm=np.asarray(xs, dtype=np.float64),
            y_norm=np.asarray(ys, dtype=np.float64),
        )

    provenance = _build_provenance(
        canonical_name=canonical_name,
        dataset=dataset,
        model=model,
        fixation_path=fixation_path,
        placement_path=placement_path,
        timing=timing,
        input_mode="processed_json",
        timing_contract=timing_contract,
        delay_frames=timing.get("delay_frames", 0),
        fixation_data_tag=fixation_data_tag,
    )

    return LoadedTrack(
        canonical_name=canonical_name,
        dataset=dataset,
        model=model,
        fixation_path=fixation_path,
        placement_path=placement_path,
        video_info=placement["video_info"],
        animation=placement["animation"],
        fps=timing["fps"],
        total_frames=total_frames,
        width=width,
        height=height,
        crop_start_frames=timing["crop_start_frames"],
        crop_end_frames=timing["crop_end_frames"],
        placement_start=placement_start,
        placement_end_exclusive=placement_end_exclusive,
        usable_count=usable_count,
        gaze_batches=gaze_batches,
        input_mode="processed_json",
        provenance=provenance,
    )


# ── resume guard ─────────────────────────────────────────────────────────────

def guard_report_compatible(
    report_path: Path,
    *,
    timing_contract: str,
    fixation_data_tag: str | None = None,
    delay_frames: int | None = None,
    turn_frame_count: int | None = None,
) -> None:
    """Raise ResumeContractMismatchError if an existing report has incompatible provenance.

    Call before writing a new report.  No-op when the report does not exist or
    cannot be read.  Prevents silently reusing an old cropped_reset report as
    if it were produced under the one_turn_from_start contract (and vice-versa),
    or with a different delay or dataset tag.

    Checked fields (any mismatch raises):
      timing_contract, fixation_data_tag, delay_frames, turn_frame_count.
    """
    if not report_path.is_file():
        return
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    prov = report.get("participant_input", {})

    def _check(field: str, expected: Any) -> None:
        existing = prov.get(field)
        if existing is not None and existing != expected:
            raise ResumeContractMismatchError(report_path, field, existing, expected)

    _check("timing_contract", timing_contract)

    if fixation_data_tag is not None:
        _check("fixation_data_tag", fixation_data_tag)

    if delay_frames is not None:
        _check("delay_frames", delay_frames)

    if turn_frame_count is not None:
        _check("turn_frame_count", turn_frame_count)


# ── old-CSV compatibility loader ──────────────────────────────────────────────

def load_csv_compat_track(
    csv_path: Path,
    placement_path: Path,
    *,
    dataset: str,
    model: str,
    canonical_name: str | None = None,
    video_id: int | None = None,
) -> LoadedTrack:
    """Load a legacy participant CSV and pair with its placement JSON.

    This is an explicit compatibility mode only. Use load_processed_track for
    new benchmark runs. This function must not be called from processed-JSON
    batch runners without an explicit --csv-compat flag.

    CSV samples outside the approved window [placement_start, placement_end_exclusive)
    are dropped. They are never clamped to the boundary frame.

    Parameters
    ----------
    csv_path:
        Path to the per-model CSV file.
    placement_path:
        Path to the canonical placement JSON.
    dataset, model, canonical_name:
        Identity (same semantics as load_processed_track).
    video_id:
        If provided, filters rows by the video_id column (needed for A380).

    Raises
    ------
    TimingValidationError:
        Placement JSON fails validation.
    FileNotFoundError:
        CSV or placement path not found.
    """
    import numpy as np  # deferred

    if canonical_name is None:
        canonical_name = f"{dataset}_{model}"

    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found for '{canonical_name}': {csv_path}")

    placement = _load_placement(placement_path)
    timing = _derive_timing(placement, placement_path)

    fps = timing["fps"]
    total_frames = timing["total_frames"]
    width = timing["width"]
    height = timing["height"]
    placement_start = timing["placement_start"]
    placement_end_exclusive = timing["placement_end_exclusive"]
    usable_count = timing["usable_count"]

    per_frame_xs: dict[int, list[float]] = {}
    per_frame_ys: dict[int, list[float]] = {}

    num_rows = 0
    participants: set = set()
    total_points = 0
    dropped_out_of_window = 0
    dropped_out_of_bounds = 0

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            num_rows += 1
            if "participation_id" in row:
                participants.add(row["participation_id"])
            if video_id is not None:
                if "video_id" not in row:
                    raise ValueError(
                        f"video_id filter requested but CSV has no video_id column: {csv_path}"
                    )
                if int(float(row["video_id"])) != video_id:
                    continue
            gaze = ast.literal_eval(row["data_gazes"])
            for t, x, y in zip(gaze.get("t", []), gaze.get("x", []), gaze.get("y", [])):
                t, x, y = float(t), float(x), float(y)
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    dropped_out_of_bounds += 1
                    continue
                # Map timestamp to placement frame — floor, no clamping.
                frame = int(math.floor(t * fps))
                if frame < placement_start or frame >= placement_end_exclusive:
                    # Out of approved window: drop, never clamp.
                    dropped_out_of_window += 1
                    continue
                per_frame_xs.setdefault(frame, []).append(x)
                per_frame_ys.setdefault(frame, []).append(y)
                total_points += 1

    gaze_batches: dict[int, GazeBatch] = {
        frame: GazeBatch(
            x_norm=np.asarray(per_frame_xs[frame], dtype=np.float64),
            y_norm=np.asarray(per_frame_ys[frame], dtype=np.float64),
        )
        for frame in sorted(per_frame_xs)
    }

    provenance = _build_provenance(
        canonical_name=canonical_name,
        dataset=dataset,
        model=model,
        fixation_path=csv_path,
        placement_path=placement_path,
        timing=timing,
        input_mode="csv_compat",
    )
    provenance["csv_num_rows"] = num_rows
    provenance["csv_num_participants"] = len(participants)
    provenance["csv_total_points"] = total_points
    provenance["csv_dropped_out_of_window"] = dropped_out_of_window
    provenance["csv_dropped_out_of_bounds"] = dropped_out_of_bounds
    provenance["csv_video_id_filter"] = video_id

    return LoadedTrack(
        canonical_name=canonical_name,
        dataset=dataset,
        model=model,
        fixation_path=csv_path,
        placement_path=placement_path,
        video_info=placement["video_info"],
        animation=placement["animation"],
        fps=fps,
        total_frames=total_frames,
        width=width,
        height=height,
        crop_start_frames=timing["crop_start_frames"],
        crop_end_frames=timing["crop_end_frames"],
        placement_start=placement_start,
        placement_end_exclusive=placement_end_exclusive,
        usable_count=usable_count,
        gaze_batches=gaze_batches,
        input_mode="csv_compat",
        provenance=provenance,
    )
