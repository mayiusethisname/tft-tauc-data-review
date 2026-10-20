"""8주차 TFT 원자료 구조·파라미터 재현 진단.

이 스크립트는 SigmaPlot에서 사용한 xfm 루틴의 핵심 계산을
재현 가능한 Python 표로 옮긴 진단용 동반 파일이다.

주의:
- mu_FE_raw_max와 mu_sat_fit은 원자료에서 정해진 단순 규칙으로 계산한 값이다.
- SigmaPlot의 smoothing/lookup/수동 회귀 구간을 완전히 동일하게 재현한다고
  주장하지 않는다. 따라서 결과 파일은 '검증용 진단'으로 취급한다.
- JNB는 SigmaPlot 바이너리 파일이라 이 스크립트의 입력으로 사용하지 않는다.
- 발표 수치 중 Oxide 70/2와 LTPS 40/1.5는 현재 원자료와 매핑하지 않는다.
  현재 15개 원자료에는 별도 제외 파일이 없다.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("TFT_DATA_DIR", PROJECT_ROOT / "data"))
OUT = Path(os.environ.get("TFT_REPORT_DIR", PROJECT_ROOT / "reports"))
C_OXIDE = 1.75e-8
VDS_LINEAR = 0.1
DELTA_VG = 0.1
VTH_CURRENT = 10e-12

# 분석 범위 제외는 현재 원자료에 실제로 존재하는 파일만 등록한다.
# 발표 수치 Oxide 70/2와 LTPS 40/1.5는 원자료 파일이 아니므로 여기에 넣지 않는다.
EXCLUDED_RAW_PATTERNS: dict[tuple[str, int, int], str] = {}


@dataclass
class Section:
    name: str
    marker: str
    measured_at: str
    header: list[str]
    rows: list[dict[str, Optional[float]]]
    raw_widths: list[int]
    missing_tokens: int


def parse_number(token: str) -> Optional[float]:
    token = token.strip()
    if token in {"", "*"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_marker(marker: str) -> tuple[str, str]:
    parts = marker.split()
    name = parts[1] if len(parts) > 1 else "UNKNOWN"
    match = re.search(r"(\d{2}/\d{2}/\d{4})", marker)
    measured_at = match.group(1) if match else ""
    return name, measured_at


def normalize_header(tokens: list[str]) -> list[str]:
    names: list[str] = []
    extra_index = 1
    for token in tokens:
        name = token.strip()
        if not name:
            name = f"__extra_{extra_index}"
            extra_index += 1
        names.append(name)
    return names


def looks_like_header(tokens: list[str]) -> bool:
    names = {token.strip() for token in tokens}
    return bool(names & {"VG", "VD", "ID", "IID", "S"})


def looks_like_data(tokens: list[str]) -> bool:
    if not any(token.strip() for token in tokens):
        return False
    return sum(parse_number(token) is not None for token in tokens) >= 2 and all(
        parse_number(token) is not None or token.strip() in {"", "*"}
        for token in tokens
    )


def build_rows(header: list[str], token_rows: Iterable[list[str]]) -> tuple[list[dict[str, Optional[float]]], int]:
    rows: list[dict[str, Optional[float]]] = []
    missing_tokens = 0
    for tokens in token_rows:
        if len(tokens) < len(header):
            continue
        values = tokens[: len(header)]
        missing_tokens += sum(token.strip() in {"", "*"} for token in values)
        rows.append({name: parse_number(value) for name, value in zip(header, values)})
    return rows, missing_tokens


def parse_dat(path: Path) -> list[Section]:
    lines = path.read_text(encoding="latin1", errors="replace").splitlines()
    marker_indices = [i for i, line in enumerate(lines) if line.startswith("DATA:")]
    sections: list[Section] = []
    for idx, marker_index in enumerate(marker_indices):
        end = marker_indices[idx + 1] if idx + 1 < len(marker_indices) else len(lines)
        marker = lines[marker_index]
        name, measured_at = parse_marker(marker)
        block = lines[marker_index + 1 : end]
        header_index = next(
            (i for i, line in enumerate(block) if line.strip() and "\t" in line and looks_like_header(line.split("\t"))),
            None,
        )
        if header_index is None:
            continue
        header_tokens = block[header_index].split("\t")
        header = normalize_header(header_tokens)
        data_tokens = [line.split("\t") for line in block[header_index + 1 :] if "\t" in line]
        data_tokens = [tokens for tokens in data_tokens if looks_like_data(tokens)]
        rows, missing_tokens = build_rows(header, data_tokens)
        sections.append(
            Section(
                name=name,
                marker=marker,
                measured_at=measured_at,
                header=header,
                rows=rows,
                raw_widths=sorted({len(tokens) for tokens in data_tokens}),
                missing_tokens=missing_tokens,
            )
        )
    return sections


def parse_csv_file(path: Path) -> list[Section]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.reader(handle))
    sections: list[Section] = []
    current_marker: Optional[str] = None
    current_name: Optional[str] = None
    current_date = ""
    current_header: Optional[list[str]] = None
    current_tokens: list[list[str]] = []

    def flush() -> None:
        nonlocal current_marker, current_name, current_date, current_header, current_tokens
        if current_name is None or current_header is None:
            return
        data_tokens = [tokens for tokens in current_tokens if looks_like_data(tokens)]
        rows, missing_tokens = build_rows(current_header, data_tokens)
        sections.append(
            Section(
                name=current_name,
                marker=current_marker or "",
                measured_at=current_date,
                header=current_header,
                rows=rows,
                raw_widths=sorted({len(tokens) for tokens in data_tokens}),
                missing_tokens=missing_tokens,
            )
        )

    for row in raw_rows:
        joined = " ".join(item.strip() for item in row if item.strip())
        if joined.startswith("DATA:"):
            flush()
            current_marker = joined
            current_name, current_date = parse_marker(joined)
            current_header = None
            current_tokens = []
            continue
        if current_name is None:
            continue
        if current_header is None:
            if looks_like_header(row):
                current_header = normalize_header(row)
            continue
        current_tokens.append(row)
    flush()
    return sections


def parse_file(path: Path) -> list[Section]:
    if path.suffix.lower() == ".dat":
        return parse_dat(path)
    if path.suffix.lower() == ".csv":
        return parse_csv_file(path)
    return []


def material_and_dimensions(path: Path) -> tuple[str, int, int]:
    stem = path.stem.lower()
    match = re.search(r"(\d{4})", stem)
    if not match:
        return "unknown", 0, 0
    dimensions = match.group(1)
    width = int(dimensions[:2])
    length = int(dimensions[2:])
    if stem.startswith("asi"):
        return "a-Si", width, length
    if stem.startswith("ltps"):
        return "LTPS", width, length
    if stem.startswith("igzo"):
        return "a-IGZO", width, length
    return "unknown", width, length


def get_vector(section: Section, x_key: str, y_key: str) -> tuple[list[float], list[float]]:
    x: list[float] = []
    y: list[float] = []
    for row in section.rows:
        xv = row.get(x_key)
        yv = row.get(y_key)
        if xv is not None and yv is not None and math.isfinite(xv) and math.isfinite(yv):
            x.append(xv)
            y.append(abs(yv))
    return x, y


def linear_regression(x: list[float], y: list[float]) -> tuple[float, float, float]:
    if len(x) < 2 or len(x) != len(y):
        return math.nan, math.nan, math.nan
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    sxx = sum((value - x_mean) ** 2 for value in x)
    if sxx == 0:
        return math.nan, math.nan, math.nan
    slope = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y)) / sxx
    intercept = y_mean - slope * x_mean
    residual = sum((value - (slope * a + intercept)) ** 2 for a, value in zip(x, y))
    total = sum((value - y_mean) ** 2 for value in y)
    r2 = 1 - residual / total if total else math.nan
    return slope, intercept, r2


def saturation_fit(
    x: list[float],
    y: list[float],
    fit_range: Optional[tuple[float, float]] = None,
) -> tuple[float, float, float, int]:
    """Fit sqrt(IDS) only when a fitting window has been explicitly supplied."""
    if fit_range is None:
        return math.nan, math.nan, math.nan, 0
    lower, upper = sorted(fit_range)
    fit_x: list[float] = []
    fit_y: list[float] = []
    for xv, yv in zip(x, y):
        if lower <= xv <= upper and yv >= 0:
            fit_x.append(xv)
            fit_y.append(math.sqrt(yv))
    slope, intercept, r2 = linear_regression(fit_x, fit_y)
    return slope, intercept, r2, len(fit_x)


def evaluate_saturation_drive_window(
    x: list[float],
    current: list[float],
    *,
    drive_sign: int,
    fit_range_drive: tuple[float, float],
) -> dict[str, float | int | str]:
    """Evaluate one intended drive-voltage window and report its coverage."""
    if drive_sign not in {-1, 1}:
        raise ValueError("drive_sign must be -1 or 1")
    lower, upper = sorted(fit_range_drive)
    requested_span = upper - lower
    if requested_span <= 0:
        return {"status": "invalid_range", "coverage_ratio": 0.0, "points": 0}

    selected = sorted(
        (
            (drive_sign * xv, math.sqrt(abs(yv)))
            for xv, yv in zip(x, current)
            if math.isfinite(xv)
            and math.isfinite(yv)
            and lower <= drive_sign * xv <= upper
        ),
        key=lambda record: record[0],
    )
    if len(selected) < 2:
        return {"status": "insufficient_points", "coverage_ratio": 0.0, "points": len(selected)}

    fit_x = [record[0] for record in selected]
    fit_y = [record[1] for record in selected]
    actual_span = fit_x[-1] - fit_x[0]
    coverage_ratio = min(actual_span / requested_span, 1.0)
    slope, intercept, r2 = linear_regression(fit_x, fit_y)
    status = "ok" if coverage_ratio >= 0.99 else "incomplete_voltage_coverage"
    if not (math.isfinite(slope) and math.isfinite(intercept) and math.isfinite(r2)) or slope == 0:
        status = "invalid_regression"
    vth_drive = -intercept / slope if slope and math.isfinite(slope) else math.nan
    return {
        "status": status,
        "requested_start_drive_V": lower,
        "requested_end_drive_V": upper,
        "actual_start_drive_V": fit_x[0],
        "actual_end_drive_V": fit_x[-1],
        "coverage_ratio": coverage_ratio,
        "points": len(selected),
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "vth_drive_V": vth_drive,
        "vth_raw_V": vth_drive / drive_sign,
    }


def recommend_saturation_windows(
    x: list[float],
    current: list[float],
    *,
    drive_sign: int,
    window_spans_v: tuple[float, ...] = (2.0, 3.0, 4.0, 5.0),
    candidate_step_v: float = 0.5,
    min_points: int = 30,
    top_k: int = 3,
) -> list[dict[str, object]]:
    """Rank measured linear-region candidates in sqrt(|IDS|) versus drive voltage."""
    if drive_sign not in {-1, 1}:
        raise ValueError("drive_sign must be -1 or 1")
    spans = tuple(sorted({float(value) for value in window_spans_v if value > 0}))
    if not spans or candidate_step_v <= 0 or min_points < 2 or top_k < 1:
        return []

    records = sorted(
        (
            (drive_sign * xv, xv, math.sqrt(abs(yv)))
            for xv, yv in zip(x, current)
            if math.isfinite(xv) and math.isfinite(yv)
        ),
        key=lambda record: record[0],
    )
    if records:
        extent = records[-1][0] - records[0][0]
        if (len(records) > 5000 or not math.isfinite(extent) or extent > 200
                or max(abs(record[0]) for record in records) > 1000
                or max(abs(value) for value in current) > 1):
            raise ValueError("TFT 지원 범위를 벗어났어요. 5,000점 이하, 전압 ±1,000 V·범위 200 V 이하, 전류 ±1 A를 확인해 주세요.")
        starts = sum(max(0, math.floor((extent - span) / candidate_step_v) + 2) for span in spans)
        # ponytail: at most two million point visits per polarity; larger sweeps need an indexed window search.
        if starts * len(records) > 2_000_000:
            raise ValueError("한 번에 비교할 구간이 너무 많아요. 측정 구간을 나눠서 넣어주세요.")
    if len(records) < min_points:
        return []

    min_drive = records[0][0]
    max_drive = records[-1][0]
    tolerance = max(candidate_step_v * 1e-6, 1e-9)
    candidates: list[dict[str, object]] = []
    for window_span_v in spans:
        first_step = math.ceil((min_drive - tolerance) / candidate_step_v)
        last_step = math.floor((max_drive - window_span_v + tolerance) / candidate_step_v)
        for step_index in range(first_step, last_step + 1):
            lower = round(step_index * candidate_step_v, 10)
            upper = round(lower + window_span_v, 10)
            selected = [record for record in records if lower - tolerance <= record[0] <= upper + tolerance]
            if len(selected) < min_points:
                continue
            selected_drive = [record[0] for record in selected]
            selected_y = [record[2] for record in selected]
            if selected_drive[-1] - selected_drive[0] < window_span_v - tolerance:
                continue
            slope, intercept, r2 = linear_regression(selected_drive, selected_y)
            if not (math.isfinite(slope) and math.isfinite(intercept) and math.isfinite(r2)) or slope <= 0:
                continue
            vth_drive = -intercept / slope
            if vth_drive >= lower:
                continue

            predictions = [slope * value + intercept for value in selected_drive]
            rmse = math.sqrt(
                sum((actual - predicted) ** 2 for actual, predicted in zip(selected_y, predictions))
                / len(selected_y)
            )
            y_range = max(selected_y) - min(selected_y)
            normalized_rmse = rmse / y_range if y_range else math.inf

            midpoint = len(selected_drive) // 2
            left_slope, _, _ = linear_regression(selected_drive[: midpoint + 1], selected_y[: midpoint + 1])
            right_slope, _, _ = linear_regression(selected_drive[midpoint:], selected_y[midpoint:])
            if math.isfinite(left_slope) and math.isfinite(right_slope):
                slope_stability = abs(left_slope - right_slope) / abs(slope)
            else:
                slope_stability = math.inf
            raw_bounds = sorted((lower / drive_sign, upper / drive_sign))
            candidates.append(
                {
                    "start_drive_V": lower,
                    "end_drive_V": upper,
                    "start_raw_V": raw_bounds[0],
                    "end_raw_V": raw_bounds[1],
                    "window_span_V": window_span_v,
                    "points": len(selected),
                    "slope": slope,
                    "intercept": intercept,
                    "r2": r2,
                    "normalized_rmse": normalized_rmse,
                    "slope_stability": slope_stability,
                    "curvature_ratio": slope_stability,
                    "vth_drive_V": vth_drive,
                    "vth_raw_V": vth_drive / drive_sign,
                }
            )

    candidate_index = {
        (round(float(candidate["window_span_V"]), 10), round(float(candidate["start_drive_V"]), 10)): candidate
        for candidate in candidates
    }
    for candidate in candidates:
        span = float(candidate["window_span_V"])
        start = float(candidate["start_drive_V"])
        slope = float(candidate["slope"])
        vth_drive = float(candidate["vth_drive_V"])
        neighboring = [
            candidate_index.get((round(span, 10), round(start + direction * candidate_step_v, 10)))
            for direction in (-1, 1)
        ]
        neighboring = [value for value in neighboring if value is not None]
        if neighboring:
            base_mu_proxy = slope**2
            candidate["mu_shift_max_pct"] = max(
                abs(float(value["slope"]) ** 2 - base_mu_proxy) / base_mu_proxy * 100
                for value in neighboring
            )
            candidate["vth_shift_max_V"] = max(
                abs(float(value["vth_drive_V"]) - vth_drive) for value in neighboring
            )
        else:
            candidate["mu_shift_max_pct"] = math.inf
            candidate["vth_shift_max_V"] = math.inf

        short_window_penalty = max(0.0, 3.0 / span - 1.0) * 0.002
        candidate["quality_score"] = (
            float(candidate["r2"])
            - float(candidate["normalized_rmse"])
            - 0.05 * float(candidate["slope_stability"])
            - 0.0002 * min(float(candidate["mu_shift_max_pct"]), 1000.0)
            - 0.01 * min(float(candidate["vth_shift_max_V"]) / span, 10.0)
            - short_window_penalty
        )
        is_reliable = (
            float(candidate["r2"]) >= 0.995
            and float(candidate["normalized_rmse"]) <= 0.02
            and float(candidate["slope_stability"]) <= 0.20
            and float(candidate["mu_shift_max_pct"]) <= 15.0
            and float(candidate["vth_shift_max_V"]) <= 0.5
        )
        candidate["reliability_status"] = (
            "statistically_reliable_candidate" if is_reliable else "review_required"
        )

    candidates.sort(
        key=lambda candidate: (
            candidate["reliability_status"] != "statistically_reliable_candidate",
            -float(candidate["window_span_V"]),
            -float(candidate["quality_score"]),
            -float(candidate["r2"]),
            -float(candidate["start_drive_V"]),
        )
    )
    return candidates[:top_k]


def build_saturation_analysis_rows(
    *,
    source_file: str,
    material: str,
    width: int,
    length: int,
    analysis_scope: str,
    x: list[float],
    current: list[float],
    drive_sign: int | None = None,
) -> list[dict[str, object]]:
    """Build ranked candidates without exposing a fixed-window coverage warning."""
    if drive_sign is None:
        drive_sign = -1 if material == "LTPS" else 1
    ratio = width / length if length else math.nan

    common = {
        "source_file": source_file,
        "material": material,
        "W_um": width,
        "L_um": length,
        "analysis_scope": analysis_scope,
        "drive_sign": drive_sign,
    }
    rows: list[dict[str, object]] = []

    candidates = recommend_saturation_windows(
        x,
        current,
        drive_sign=drive_sign,
        window_spans_v=(2.0, 3.0, 4.0, 5.0),
        candidate_step_v=0.5,
        min_points=20,
        top_k=3,
    )
    for rank, candidate in enumerate(candidates, start=1):
        slope = float(candidate["slope"])
        rows.append(
            {
                **common,
                "candidate_type": "ai_candidate",
                "candidate_rank": rank,
                "status": "candidate_only",
                "approval_status": "human_review_required",
                "start_drive_V": candidate["start_drive_V"],
                "end_drive_V": candidate["end_drive_V"],
                "start_raw_V": candidate["start_raw_V"],
                "end_raw_V": candidate["end_raw_V"],
                "window_span_V": candidate["window_span_V"],
                "points": candidate["points"],
                "r2": candidate["r2"],
                "normalized_rmse": candidate["normalized_rmse"],
                "slope_stability": candidate["slope_stability"],
                "curvature_ratio": candidate["curvature_ratio"],
                "mu_shift_max_pct": candidate["mu_shift_max_pct"],
                "vth_shift_max_V": candidate["vth_shift_max_V"],
                "quality_score": candidate["quality_score"],
                "reliability_status": candidate["reliability_status"],
                "mu_sat_cm2_Vs": 2 * slope**2 / (C_OXIDE * ratio)
                if math.isfinite(slope) and math.isfinite(ratio)
                else math.nan,
                "vth_sat_raw_V": candidate["vth_raw_V"],
                "recommendation_reason": (
                    f"R2={float(candidate['r2']):.6f}, "
                    f"nRMSE={float(candidate['normalized_rmse']):.4f}, "
                    f"shift_mu={float(candidate['mu_shift_max_pct']):.2f}%, "
                    f"shift_vth={float(candidate['vth_shift_max_V']):.3f} V"
                ),
            }
        )
    return rows


def vth_lookup(x: list[float], y: list[float], target: float) -> tuple[Optional[float], int]:
    candidates: list[tuple[float, float]] = []
    crossings = 0
    for index in range(len(x) - 1):
        y1, y2 = y[index], y[index + 1]
        if (y1 - target) * (y2 - target) <= 0 and y1 != y2:
            fraction = (target - y1) / (y2 - y1)
            candidates.append((x[index] + fraction * (x[index + 1] - x[index]), abs(math.log10(max(y1, 1e-30) / target))))
            crossings += 1
    if candidates:
        return min(candidates, key=lambda pair: pair[1])[0], crossings
    nearest = min(range(len(y)), key=lambda index: abs(math.log10(max(y[index], 1e-30) / target))) if y else None
    return (x[nearest] if nearest is not None else None), crossings


def parameter_diagnostic(
    path: Path,
    section_map: dict[str, Section],
    material: str,
    width: int,
    length: int,
    sat_fit_range: Optional[tuple[float, float]] = None,
) -> dict[str, object]:
    low = section_map.get("LOWTRANS")
    mobility = section_map.get("MOBILITY")
    exclusion_reason = EXCLUDED_RAW_PATTERNS.get((material, width, length), "")
    row: dict[str, object] = {
        "source_file": path.name,
        "material": material,
        "W_um": width,
        "L_um": length,
        "W_over_L": width / length if length else math.nan,
        "C_oxide_F_per_cm2": C_OXIDE,
        "low_rows": len(low.rows) if low else 0,
        "mobility_rows": len(mobility.rows) if mobility else 0,
        "analysis_scope": "excluded" if exclusion_reason else "included",
        "exclusion_reason": exclusion_reason,
        "status": "ok",
    }
    if low is None or mobility is None:
        row["status"] = "missing_LOWTRANS_or_MOBILITY"
        return row

    current_key = "IID" if "IID" in low.header else "ID"
    x, y = get_vector(low, "VG", current_key)
    target = (width / length) * VTH_CURRENT
    vth, crossing_count = vth_lookup(x, y, target)
    fit_x = [xv for xv, yv in zip(x, y) if 1e-11 <= yv <= 1e-10]
    fit_y = [math.log10(yv) for yv in y if 1e-11 <= yv <= 1e-10]
    ss_slope, _, ss_r2 = linear_regression(fit_x, fit_y)
    mu_values: list[float] = []
    for left, right in zip(y, y[1:]):
        mu_values.append(abs(right - left) / DELTA_VG * length / (width * C_OXIDE * VDS_LINEAR))
    if mu_values:
        mu_index = max(range(len(mu_values)), key=lambda index: mu_values[index])
        row["mu_fe_raw_max_cm2_Vs"] = mu_values[mu_index]
        row["mu_fe_peak_VG_start"] = x[mu_index] if mu_index < len(x) else math.nan
    else:
        row["mu_fe_raw_max_cm2_Vs"] = math.nan
        row["mu_fe_peak_VG_start"] = math.nan

    sat_x, sat_i = get_vector(mobility, "VD", "ID")
    sat_slope, sat_intercept, sat_r2, sat_fit_points = saturation_fit(sat_x, sat_i, sat_fit_range)
    ratio = width / length
    row.update(
        {
            "vth_lookup_V": vth,
            "vth_target_A": target,
            "vth_crossing_count": crossing_count,
            "ss_fit_V_dec": abs(1 / ss_slope) if ss_slope and math.isfinite(ss_slope) else math.nan,
            "ss_fit_points": len(fit_x),
            "ss_fit_r2": ss_r2,
            "mu_sat_fit_cm2_Vs": 2 * sat_slope**2 / (C_OXIDE * ratio) if math.isfinite(sat_slope) else math.nan,
            "vth_sat_fit_V": -sat_intercept / sat_slope if sat_slope and math.isfinite(sat_slope) else math.nan,
            "sat_fit_points": sat_fit_points,
            "sat_fit_r2": sat_r2,
            "sat_fit_status": "fitted_explicit_range" if sat_fit_range is not None else "not_fitted_missing_explicit_range",
        }
    )
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source_files = sorted(path for path in ROOT.iterdir() if path.suffix.lower() in {".dat", ".csv"})
    structure_rows: list[dict[str, object]] = []
    parameter_rows: list[dict[str, object]] = []
    saturation_rows: list[dict[str, object]] = []

    for path in source_files:
        material, width, length = material_and_dimensions(path)
        sections = parse_file(path)
        section_map = {section.name: section for section in sections}
        for section in sections:
            structure_rows.append(
                {
                    "source_file": path.name,
                    "material": material,
                    "W_um": width,
                    "L_um": length,
                    "format": path.suffix.lower().lstrip("."),
                    "section": section.name,
                    "measured_at": section.measured_at,
                    "rows": len(section.rows),
                    "header": "|".join(section.header),
                    "raw_widths": "|".join(str(value) for value in section.raw_widths),
                    "missing_tokens": section.missing_tokens,
                }
            )
        if "LOWTRANS" in section_map and "MOBILITY" in section_map:
            diagnostic = parameter_diagnostic(path, section_map, material, width, length)
            parameter_rows.append(diagnostic)
            sat_x, sat_i = get_vector(section_map["MOBILITY"], "VD", "ID")
            saturation_rows.extend(
                build_saturation_analysis_rows(
                    source_file=path.name,
                    material=material,
                    width=width,
                    length=length,
                    analysis_scope=str(diagnostic["analysis_scope"]),
                    x=sat_x,
                    current=sat_i,
                )
            )

    structure_path = OUT / "8주차_원자료_구조검증.csv"
    parameter_path = OUT / "8주차_파라미터_재현진단.csv"
    saturation_path = OUT / "8주차_saturation_구간후보.csv"
    json_path = OUT / "8주차_원자료_구조검증.json"
    with structure_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(structure_rows[0].keys()))
        writer.writeheader()
        writer.writerows(structure_rows)
    with parameter_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(parameter_rows[0].keys()))
        writer.writeheader()
        writer.writerows(parameter_rows)
    with saturation_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(saturation_rows[0].keys()))
        writer.writeheader()
        writer.writerows(saturation_rows)
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source_root": str(ROOT),
                "source_file_count": len(source_files),
                "structure_rows": structure_rows,
                "parameter_rows": parameter_rows,
                "saturation_rows": saturation_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"source_files={len(source_files)}")
    print(f"sections={len(structure_rows)}")
    print(f"parameter_files_included={sum(row.get('analysis_scope') == 'included' for row in parameter_rows)}")
    print(f"parameter_files_excluded={sum(row.get('analysis_scope') == 'excluded' for row in parameter_rows)}")
    print(f"structure_csv={structure_path}")
    print(f"parameter_csv={parameter_path}")
    print(f"saturation_csv={saturation_path}")
    print(f"json={json_path}")


if __name__ == "__main__":
    main()


