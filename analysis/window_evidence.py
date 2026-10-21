"""Bias consistency and explicit window shifts for the MOBILITY transfer model."""
from __future__ import annotations

import math
import profile_8week as profile


def window_evidence(points: list[dict], candidate: dict, width: int, length: int) -> dict:
    """Keep measured coverage, model assumptions and regression sensitivity separate."""
    sign = int(candidate["drive_sign"])
    lower, upper = float(candidate["start_raw_V"]), float(candidate["end_raw_V"])
    selected = [p for p in points if lower - 1e-8 <= p["x"] <= upper + 1e-8]
    threshold = sign * float(candidate["vth_sat_raw_V"])
    overdrive = [sign * p["x"] - threshold for p in selected]
    # The source MOBILITY profile maps its VD column to both VGS and VDS.
    # This tests that mapping against the fitted ideal-model bias inequalities.
    margin = [sign * p["x"] - value for p, value in zip(selected, overdrive)]
    model = {"basis": "MOBILITY: VGS = VDS", "overdrive_min_V": min(overdrive),
             "saturation_margin_min_V": min(margin),
             "passed": min(overdrive) > 0 and min(margin) >= -1e-8}
    base_mu, base_vth = float(candidate["mu_sat_cm2_Vs"]), float(candidate["vth_sat_raw_V"])
    shifts = []
    for shift in (-0.5, 0.0, 0.5):
        lo, hi = lower + shift, upper + shift
        row = {"shift_V": shift, "start_raw_V": lo, "end_raw_V": hi}
        chosen = sorted((p for p in points if lo - 1e-8 <= p["x"] <= hi + 1e-8), key=lambda p:p["x"])
        if len(chosen) < 20 or chosen[0]["x"] > lo + 1e-8 or chosen[-1]["x"] < hi - 1e-8:
            shifts.append({**row, "status":"outside_coverage", "points":len(chosen)})
            continue
        slope, intercept, r2 = profile.linear_regression([p["x"] for p in chosen], [p["root_current_A"] for p in chosen])
        if not all(math.isfinite(v) for v in (slope, intercept, r2)) or sign * slope <= 0:
            shifts.append({**row, "status":"invalid_slope", "points":len(chosen)})
            continue
        mu = 2 * slope**2 / (profile.C_OXIDE * width / length)
        vth = -intercept / slope
        shifts.append({**row, "status":"calculated", "points":len(chosen), "mu_cm2_Vs":mu,
                       "vth_V":vth, "r2":r2, "delta_mu_pct":(mu/base_mu - 1)*100,
                       "delta_vth_V":vth-base_vth})
    changed = [r for r in shifts if r["status"] == "calculated" and r["shift_V"]]
    return {"model_check":model, "sensitivity":{"axis":"raw_voltage", "shift_V":0.5, "rows":shifts,
            "complete":len(changed)==2,
            "max_mu_change_pct":max((abs(r["delta_mu_pct"]) for r in changed), default=None),
            "max_vth_change_V":max((abs(r["delta_vth_V"]) for r in changed), default=None)}}
