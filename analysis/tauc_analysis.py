from __future__ import annotations

import math
from bisect import bisect_left, bisect_right

import tauc_file_intake as intake


HC_EV_NM = 1239.841984
ALPHA_MODELS = (
    "beer_lambert_apparent",
    "reflection_corrected_simplified",
)
REFLECTION_FORMULA_PROVENANCE = {
    "legacy_formula_text": "x = (-A + sqrt(A^2 - 4*B*T^2)) / (2*B*T)",
    "computed_formula": "x = (-A + sqrt(A^2 + 4*B*T^2)) / (2*B*T)",
    "verification": "forward_inverse_round_trip",
}


def photon_energy_ev(wavelength_nm: float) -> float:
    if not math.isfinite(wavelength_nm) or wavelength_nm <= 0:
        raise ValueError("invalid_wavelength")
    return HC_EV_NM / wavelength_nm


def _validate_optical_input(
    transmittance_fraction: float, thickness_nm: float
) -> None:
    if (
        not math.isfinite(transmittance_fraction)
        or not 0.0 < transmittance_fraction <= 1.0
    ):
        raise ValueError("invalid_transmittance")
    if not math.isfinite(thickness_nm) or thickness_nm <= 0:
        raise ValueError("invalid_thickness")


def beer_lambert_alpha(
    transmittance_fraction: float, thickness_nm: float
) -> float:
    _validate_optical_input(transmittance_fraction, thickness_nm)
    return -math.log(transmittance_fraction) / (thickness_nm * 1e-7)


def fresnel_reflectance(n_i: float, n_j: float) -> float:
    if (
        not math.isfinite(n_i)
        or not math.isfinite(n_j)
        or n_i <= 0
        or n_j <= 0
    ):
        raise ValueError("invalid_refractive_index")
    return ((n_i - n_j) / (n_i + n_j)) ** 2


def reflection_forward_transmittance(
    alpha_cm_inv: float,
    thickness_nm: float,
    n_air: float,
    n_film: float,
    n_glass: float,
) -> float:
    if not math.isfinite(alpha_cm_inv) or alpha_cm_inv < 0:
        raise ValueError("invalid_absorption_coefficient")
    if not math.isfinite(thickness_nm) or thickness_nm <= 0:
        raise ValueError("invalid_thickness")
    r_air_film = fresnel_reflectance(n_air, n_film)
    r_film_glass = fresnel_reflectance(n_film, n_glass)
    a = (1.0 - r_air_film) * (1.0 - r_film_glass)
    b = r_air_film * r_film_glass
    x = math.exp(-alpha_cm_inv * thickness_nm * 1e-7)
    denominator = 1.0 - b * x * x
    if denominator <= 0:
        raise ValueError("reflection_model_domain")
    return a * x / denominator


def reflection_corrected_alpha(
    transmittance_fraction: float,
    thickness_nm: float,
    n_air: float,
    n_film: float,
    n_glass: float,
) -> float:
    _validate_optical_input(transmittance_fraction, thickness_nm)
    r_air_film = fresnel_reflectance(n_air, n_film)
    r_film_glass = fresnel_reflectance(n_film, n_glass)
    a = (1.0 - r_air_film) * (1.0 - r_film_glass)
    b = r_air_film * r_film_glass
    if a <= 0:
        raise ValueError("reflection_model_domain")
    discriminant = a * a + 4.0 * b * transmittance_fraction**2
    # Rationalized positive root.  This is algebraically identical to
    # (-A + sqrt(discriminant)) / (2*B*T), but remains stable when B is tiny.
    x = (2.0 * transmittance_fraction) / (
        a + math.sqrt(discriminant)
    )
    if not math.isfinite(x) or not 0.0 < x <= 1.0:
        raise ValueError("reflection_model_domain")
    return -math.log(x) / (thickness_nm * 1e-7)


def tauc_ordinate(
    alpha_cm_inv: float, energy_ev: float, transition_model: str
) -> float:
    if (
        not math.isfinite(alpha_cm_inv)
        or alpha_cm_inv < 0
        or not math.isfinite(energy_ev)
        or energy_ev <= 0
    ):
        raise ValueError("invalid_tauc_input")
    base = alpha_cm_inv * energy_ev
    if transition_model in {"indirect_allowed", "legacy_amorphous"}:
        return math.sqrt(base)
    if transition_model == "direct_allowed":
        return base * base
    raise ValueError("unsupported_transition_model")


def centered_moving_average_11(values: list[float]) -> list[float | None]:
    return [
        None
        if index < 5 or index >= len(values) - 5
        else sum(values[index - 5 : index + 6]) / 11.0
        for index in range(len(values))
    ]


def alpha_for_model(
    alpha_model: str,
    transmittance_fraction: float,
    result: intake.TaucIntakeResult,
) -> float:
    if result.thickness_nm is None:
        raise ValueError("sample_thickness_unconfirmed")
    if alpha_model == "beer_lambert_apparent":
        return beer_lambert_alpha(
            transmittance_fraction, result.thickness_nm
        )
    if alpha_model == "reflection_corrected_simplified":
        if result.film_refractive_index is None:
            raise ValueError("sample_refractive_index_unconfirmed")
        return reflection_corrected_alpha(
            transmittance_fraction,
            result.thickness_nm,
            1.0,
            result.film_refractive_index,
            1.5,
        )
    raise ValueError("unsupported_alpha_model")


def build_tauc_combinations(
    result: intake.TaucIntakeResult,
) -> list[dict[str, object]]:
    combinations: list[dict[str, object]] = []
    smoothed_transmittance = centered_moving_average_11(
        [point.transmittance_percent / 100.0 for point in result.points]
    )
    for alpha_model in ALPHA_MODELS:
        for transition_model in result.transition_models:
            points: list[dict[str, float | None]] = []
            errors: list[str] = []
            for point, smoothed_t in zip(result.points, smoothed_transmittance):
                transmittance_fraction = point.transmittance_percent / 100.0
                energy_ev = photon_energy_ev(point.wavelength_nm)
                try:
                    alpha = alpha_for_model(
                        alpha_model, transmittance_fraction, result
                    )
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                smoothed_ordinate = None
                if smoothed_t is not None:
                    try:
                        smoothed_ordinate = tauc_ordinate(
                            alpha_for_model(alpha_model, smoothed_t, result),
                            energy_ev,
                            transition_model,
                        )
                    except ValueError:
                        errors.append("smoothing_model_domain")
                points.append(
                    {
                        "wavelength_nm": point.wavelength_nm,
                        "transmittance_percent": point.transmittance_percent,
                        "energy_eV": energy_ev,
                        "alpha_cm_inv": alpha,
                        "tauc_ordinate": tauc_ordinate(
                            alpha, energy_ev, transition_model
                        ),
                        "smoothed_tauc_ordinate": smoothed_ordinate,
                    }
                )
            points.sort(key=lambda item: float(item["energy_eV"]))
            combinations.append(
                {
                    "combination_id": (
                        f"{alpha_model}__{transition_model}"
                    ),
                    "alpha_model": alpha_model,
                    "transition_model": transition_model,
                    "points": points,
                    "model_errors": sorted(set(errors)),
                }
            )
    return combinations


START_STEP_EV = 0.02
WINDOW_SPANS_EV = (0.25, 0.35, 0.50, 0.75)
MIN_POINTS = 80


def linear_fit(points: list[dict[str, float]]) -> dict[str, float]:
    if len(points) < 2:
        raise ValueError("linear_fit_undefined")
    xs = [float(point["energy_eV"]) for point in points]
    ys = [float(point["tauc_ordinate"]) for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        raise ValueError("linear_fit_undefined")
    slope = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
    ) / sxx
    intercept = mean_y - slope * mean_x
    residuals = [
        y - (slope * x + intercept) for x, y in zip(xs, ys)
    ]
    ss_res = sum(value * value for value in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    rmse = math.sqrt(ss_res / len(points))
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": 1.0 - ss_res / ss_tot if ss_tot else 1.0,
        "rmse": rmse,
        "eg_eV": -intercept / slope if slope else math.nan,
    }


def solve_3x3(
    matrix: list[list[float]], vector: list[float]
) -> list[float]:
    augmented = [
        row[:] + [value] for row, value in zip(matrix, vector)
    ]
    for pivot in range(3):
        swap = max(
            range(pivot, 3),
            key=lambda row: abs(augmented[row][pivot]),
        )
        augmented[pivot], augmented[swap] = (
            augmented[swap],
            augmented[pivot],
        )
        if abs(augmented[pivot][pivot]) <= 1e-18:
            raise ValueError("quadratic_fit_undefined")
        scale = augmented[pivot][pivot]
        augmented[pivot] = [
            value / scale for value in augmented[pivot]
        ]
        for row in range(3):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            augmented[row] = [
                value - factor * base
                for value, base in zip(
                    augmented[row], augmented[pivot]
                )
            ]
    return [augmented[row][3] for row in range(3)]


def quadratic_rmse(points: list[dict[str, float]]) -> float:
    if len(points) < 3:
        raise ValueError("quadratic_fit_undefined")
    xs = [float(point["energy_eV"]) for point in points]
    ys = [float(point["tauc_ordinate"]) for point in points]
    center = sum(xs) / len(xs)
    zs = [x - center for x in xs]
    sums = [
        len(zs),
        sum(zs),
        sum(z * z for z in zs),
        sum(z**3 for z in zs),
        sum(z**4 for z in zs),
    ]
    quadratic, linear, constant = solve_3x3(
        [
            [sums[4], sums[3], sums[2]],
            [sums[3], sums[2], sums[1]],
            [sums[2], sums[1], sums[0]],
        ],
        [
            sum(z * z * y for z, y in zip(zs, ys)),
            sum(z * y for z, y in zip(zs, ys)),
            sum(ys),
        ],
    )
    errors = [
        y - (quadratic * z * z + linear * z + constant)
        for z, y in zip(zs, ys)
    ]
    return math.sqrt(sum(error * error for error in errors) / len(errors))


def coverage_distance(
    eg_ev: float, measured_min: float, measured_max: float
) -> float:
    if eg_ev < measured_min:
        return measured_min - eg_ev
    if eg_ev > measured_max:
        return eg_ev - measured_max
    return 0.0


def fit_for_field(
    points: list[dict[str, float | None]], field: str
) -> dict[str, float] | None:
    usable = [
        {
            "energy_eV": float(point["energy_eV"]),
            "tauc_ordinate": float(point[field]),
        }
        for point in points
        if point.get(field) is not None
        and math.isfinite(float(point[field]))
    ]
    if len(usable) < MIN_POINTS:
        return None
    try:
        fit = linear_fit(usable)
    except ValueError:
        return None
    if (
        fit["slope"] <= 0
        or not math.isfinite(fit["eg_eV"])
        or fit["eg_eV"] <= 0
    ):
        return None
    return fit


def energy_window(
    points: list[dict[str, float | None]],
    energies: list[float],
    lower: float,
    upper: float,
) -> list[dict[str, float | None]]:
    start = bisect_left(energies, lower - 1e-12)
    end = bisect_right(energies, upper + 1e-12)
    return points[start:end]


def calculate_window_and_smoothing_sensitivity(
    points: list[dict[str, float | None]],
    candidate: dict[str, object],
    energies: list[float] | None = None,
) -> dict[str, float | None]:
    if energies is None:
        energies = [float(point["energy_eV"]) for point in points]
    span = float(candidate["end_eV"]) - float(candidate["start_eV"])
    shifted_eg: list[float] = []
    for delta in (-0.05, 0.05):
        lower = float(candidate["start_eV"]) + delta
        upper = lower + span
        if (
            lower < float(points[0]["energy_eV"])
            or upper > float(points[-1]["energy_eV"])
        ):
            shifted_eg = []
            break
        shifted = energy_window(points, energies, lower, upper)
        fit = fit_for_field(shifted, "tauc_ordinate")
        if fit is None:
            shifted_eg = []
            break
        shifted_eg.append(fit["eg_eV"])
    original_window = energy_window(
        points,
        energies,
        float(candidate["start_eV"]),
        float(candidate["end_eV"]),
    )
    smoothed_fit = fit_for_field(
        original_window, "smoothed_tauc_ordinate"
    )
    return {
        "eg_shift_max_eV": max(
            (
                abs(value - float(candidate["eg_eV"]))
                for value in shifted_eg
            ),
            default=None,
        ),
        "eg_smoothing_delta_eV": (
            None
            if smoothed_fit is None
            else abs(smoothed_fit["eg_eV"] - float(candidate["eg_eV"]))
        ),
    }


def candidate_rationale(candidate: dict[str, object]) -> str:
    prefix = "안정 후보" if candidate["status"] == "stable" else "우선 검토"
    if float(candidate["coverage_distance_eV"]) > 0:
        facts = [
            (
                "Eg가 측정 범위에서 "
                f"{float(candidate['coverage_distance_eV']):.2f} eV 벗어남"
            ),
            f"R² {float(candidate['r2']):.4f}",
        ]
    else:
        sensitivity_values = [
            float(value)
            for value in (
                candidate["eg_shift_max_eV"],
                candidate["eg_smoothing_delta_eV"],
            )
            if value is not None
        ]
        sensitivity = (
            max(sensitivity_values) if sensitivity_values else math.inf
        )
        facts = [
            (
                "낮은 잔차"
                if float(candidate["normalized_rmse"]) <= 0.03
                else "잔차 확인 필요"
            ),
            (
                "민감도 계산 불가"
                if not math.isfinite(sensitivity)
                else f"Eg 최대 변화 {sensitivity:.2f} eV"
            ),
        ]
    return (prefix + " · " + ", ".join(facts))[:120]


def candidate_status(candidate: dict[str, object]) -> str:
    stable = (
        float(candidate["r2"]) >= 0.995
        and float(candidate["normalized_rmse"]) <= 0.03
        and float(candidate["split_slope_delta"]) <= 0.15
        and float(candidate["quadratic_gain"]) <= 0.10
        and candidate["eg_shift_max_eV"] is not None
        and float(candidate["eg_shift_max_eV"]) <= 0.10
        and candidate["eg_smoothing_delta_eV"] is not None
        and float(candidate["eg_smoothing_delta_eV"]) <= 0.10
        and float(candidate["coverage_distance_eV"]) == 0.0
    )
    return "stable" if stable else "review"


def generate_candidates(
    points: list[dict[str, float | None]],
    alpha_model: str,
    transition_model: str,
) -> list[dict[str, object]]:
    if len(points) < MIN_POINTS:
        return []
    measured_min = float(points[0]["energy_eV"])
    measured_max = float(points[-1]["energy_eV"])
    energies = [float(point["energy_eV"]) for point in points]
    start_tick = math.ceil(measured_min / START_STEP_EV) * START_STEP_EV
    candidates: list[dict[str, object]] = []
    tick = start_tick
    while tick <= measured_max:
        for span in WINDOW_SPANS_EV:
            if tick + span > measured_max + 1e-12:
                continue
            selected = energy_window(points, energies, tick, tick + span)
            if len(selected) < MIN_POINTS:
                continue
            fit_points = [
                {
                    "energy_eV": float(point["energy_eV"]),
                    "tauc_ordinate": float(point["tauc_ordinate"]),
                }
                for point in selected
            ]
            fit = linear_fit(fit_points)
            ys = [float(point["tauc_ordinate"]) for point in selected]
            y_range = max(ys) - min(ys)
            normalized_rmse = (
                fit["rmse"] / y_range if y_range > 1e-12 else math.inf
            )
            if (
                fit["slope"] <= 0
                or fit["r2"] < 0.98
                or normalized_rmse > 0.08
                or not math.isfinite(fit["eg_eV"])
                or fit["eg_eV"] <= 0
            ):
                continue
            midpoint = len(fit_points) // 2
            first_fit = linear_fit(fit_points[:midpoint])
            second_fit = linear_fit(fit_points[midpoint:])
            split_delta = abs(
                first_fit["slope"] - second_fit["slope"]
            ) / max(abs(fit["slope"]), 1e-12)
            quad_rmse = quadratic_rmse(fit_points)
            quadratic_gain = (
                0.0
                if fit["rmse"] <= max(1e-12, y_range * 1e-12)
                else max(
                    0.0,
                    (fit["rmse"] - quad_rmse) / fit["rmse"],
                )
            )
            candidate: dict[str, object] = {
                "candidate_id": (
                    f"{alpha_model}__{transition_model}__"
                    f"{tick:.2f}__{tick + span:.2f}"
                ),
                "alpha_model": alpha_model,
                "transition_model": transition_model,
                "start_eV": tick,
                "end_eV": tick + span,
                "points": len(selected),
                "slope": fit["slope"],
                "intercept": fit["intercept"],
                "eg_eV": fit["eg_eV"],
                "r2": fit["r2"],
                "normalized_rmse": normalized_rmse,
                "split_slope_delta": split_delta,
                "quadratic_gain": quadratic_gain,
                "coverage_distance_eV": coverage_distance(
                    fit["eg_eV"], measured_min, measured_max
                ),
            }
            candidate.update(
                calculate_window_and_smoothing_sensitivity(
                    points, candidate, energies
                )
            )
            candidate["status"] = candidate_status(candidate)
            candidate["rationale"] = candidate_rationale(candidate)
            candidates.append(candidate)
        tick = round(tick + START_STEP_EV, 10)
    return candidates


def interval_iou(
    left: dict[str, object], right: dict[str, object]
) -> float:
    overlap = max(
        0.0,
        min(float(left["end_eV"]), float(right["end_eV"]))
        - max(float(left["start_eV"]), float(right["start_eV"])),
    )
    union = max(float(left["end_eV"]), float(right["end_eV"])) - min(
        float(left["start_eV"]), float(right["start_eV"])
    )
    return overlap / union if union else 1.0


def same_candidate_family(
    left: dict[str, object], right: dict[str, object]
) -> bool:
    return interval_iou(left, right) >= 0.80 and abs(
        float(left["eg_eV"]) - float(right["eg_eV"])
    ) <= 0.05


def rank_key(candidate: dict[str, object]) -> tuple[object, ...]:
    sensitivity = max(
        (
            float(value) if value is not None else math.inf
            for value in (
                candidate["eg_shift_max_eV"],
                candidate["eg_smoothing_delta_eV"],
            )
        )
    )
    return (
        0 if candidate["status"] == "stable" else 1,
        float(candidate["coverage_distance_eV"]),
        sensitivity,
        -float(candidate["r2"]),
        float(candidate["normalized_rmse"]),
        float(candidate["split_slope_delta"]),
        -(float(candidate["end_eV"]) - float(candidate["start_eV"])),
        float(candidate["start_eV"]),
    )


def rank_and_deduplicate(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    for candidate in sorted(candidates, key=rank_key):
        if any(
            same_candidate_family(candidate, existing) for existing in kept
        ):
            continue
        kept.append(dict(candidate))
    for rank, candidate in enumerate(kept, 1):
        candidate["rank"] = rank
    return kept[:3]


def analyze_intake(result: intake.TaucIntakeResult) -> dict[str, object]:
    if result.status != "ready" or not result.points:
        raise ValueError("tauc_intake_not_ready")
    combinations = build_tauc_combinations(result)
    for combination in combinations:
        candidates = generate_candidates(
            combination["points"],
            str(combination["alpha_model"]),
            str(combination["transition_model"]),
        )
        combination["candidates"] = rank_and_deduplicate(candidates)
        combination["status"] = (
            "hold"
            if not combination["candidates"]
            else combination["candidates"][0]["status"]
        )
    return {
        "source_file": result.source_file,
        "sample_id": result.material,
        "input_metadata": {
            "thickness_nm": result.thickness_nm,
            "baseline_type": "air",
            "substrate": "glass",
            "film_refractive_index": result.film_refractive_index,
            "air_refractive_index": 1.0,
            "glass_refractive_index": 1.5,
            "measurement_date": result.metadata.get("DATE", ""),
            "point_count": len(result.points),
        },
        "calculation_provenance": {
            "reflection_model": dict(REFLECTION_FORMULA_PROVENANCE)
        },
        "measurement_range": {
            "wavelength_nm": [
                result.points[0].wavelength_nm,
                result.points[-1].wavelength_nm,
            ],
            "energy_eV": [
                photon_energy_ev(result.points[-1].wavelength_nm),
                photon_energy_ev(result.points[0].wavelength_nm),
            ],
        },
        "transmittance_points": [
            {
                "wavelength_nm": point.wavelength_nm,
                "transmittance_percent": point.transmittance_percent,
            }
            for point in result.points
        ],
        "combinations": combinations,
    }


