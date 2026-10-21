"""Shared analysis entry point for local and Vercel demos."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from examples import get_sample, sample_catalog


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "analysis"))

import profile_8week as profile  # noqa: E402
import tauc_analysis  # noqa: E402
import tauc_file_intake  # noqa: E402
import tft_file_intake  # noqa: E402
from curve_review import review_saturation  # noqa: E402
from window_evidence import window_evidence  # noqa: E402
from diagnostics import gap_findings, unknown_column_preview, optical_preview  # noqa: E402


ANALYSIS_VERSION = "portfolio-3.3"
MAX_UPLOAD_BYTES = 3 * 1024 * 1024
TFT_MATERIAL_PREFIX = {"a-Si": "aSi", "a-IGZO": "IGZO", "LTPS": "LTPS"}
TAUC_PROFILE_FILENAME = {
    "a-Si": "a-Si.csv",
    "Poly-Si": "poly-Si.csv",
    "a-IGZO": "a-IGZO.csv",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _decision_key(domain: str, raw: bytes, config: dict[str, object]) -> str:
    fingerprint = json.dumps(
        {"domain": domain, "version": ANALYSIS_VERSION, "config": config},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw + b"\0" + fingerprint).hexdigest()


def _decode_tft(filename: str, raw: bytes) -> str:
    if Path(filename).suffix.lower() == ".dat":
        return raw.decode("latin1")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("이 파일의 문자 인코딩을 읽을 수 없어요.")


def _tft_parse_name(filename: str, config: dict[str, object]) -> str:
    material = str(config.get("material", ""))
    try:
        width = int(config.get("width_um", 0))
        length = int(config.get("length_um", 0))
    except (ValueError, TypeError, OverflowError):
        return filename
    prefix = TFT_MATERIAL_PREFIX.get(material)
    if not prefix or not (1 <= width <= 99 and 1 <= length <= 99):
        return filename
    suffix = Path(filename).suffix.lower()
    if suffix not in {".dat", ".csv"}:
        suffix = ".csv"
    return f"{prefix}{width:02d}{length:02d}{suffix}"


def _conditions(domain: str, filename: str, config: dict) -> dict:
    """Validate what will be used; acknowledgement is separate from inference."""
    material = str(config.get("material", ""))
    hint = None
    if domain == "tft":
        if material not in TFT_MATERIAL_PREFIX:
            raise ValueError("재료를 선택해 주세요.")
        dimensions = {}
        for key in ("width_um", "length_um"):
            number = config.get(key)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 1 <= number <= 99 or int(number) != number:
                raise ValueError("W와 L은 1~99 μm의 정수로 입력해 주세요.")
            dimensions[key] = int(number)
        values = {"material": material, **dimensions, "polarity": config.get("polarity", "auto")}
        hm, hw, hl = profile.material_and_dimensions(Path(filename))
        structured = re.match(r"^(aIGZO|aSi|LTPS)_W(\d{1,2})_?L(\d{1,2})(?:_|\.)", filename, re.I)
        if structured:
            hm = {"aigzo":"a-IGZO", "asi":"a-Si", "ltps":"LTPS"}[structured[1].lower()]
            hw, hl = int(structured[2]), int(structured[3])
        if hm != "unknown" and hw and hl:
            hint = {"material": hm, "width_um": hw, "length_um": hl}
    else:
        parser_name = TAUC_PROFILE_FILENAME.get(material)
        if parser_name is None:
            raise ValueError("재료를 선택해 주세요.")
        preset = tauc_file_intake.SAMPLE_CONFIGS[parser_name.lower()]
        values = {"material": material, "thickness_nm": preset["thickness_nm"],
                  "film_refractive_index": preset["film_n"], "baseline_type": "air", "substrate": "glass"}
        for key, expected in values.items():
            if key in config and config[key] != expected:
                raise ValueError("선택한 실험 프로파일과 다른 광학 조건이 있어요. 두께·굴절률·air 기준선·glass 기판을 확인해 주세요.")
        if "film_n" in config and config["film_n"] != preset["film_n"]:
            raise ValueError("이 프로파일과 다른 박막 굴절률은 지원하지 않아요.")
        hinted = next((name for name, source in TAUC_PROFILE_FILENAME.items() if source.lower() == filename.lower()), None)
        if hinted:
            hint = {"material": hinted}
    mismatch = bool(hint and any(values.get(key) != value for key, value in hint.items()))
    return {"confirmed": config.get("conditions_confirmed") is True, "source": "user_confirmed",
            "values": values, "filename_hint": hint, "override": mismatch}


def _condition_hold(conditions: dict) -> dict:
    return {"status": "needs_confirmation", "message": "계산에 사용할 측정 조건을 확인해 주세요.",
            "conditions": conditions, "intake": conditions["values"], "data": {},
            "findings": [{"code": "conditions_unconfirmed", "title": "계산에 사용할 조건을 확인해 주세요",
                          "detail": "파일명에서 읽힌 조건과 직접 입력한 조건을 나란히 확인해 주세요.",
                          "action": "측정 조건을 확인했다는 항목에 체크한 뒤 다시 분석해 주세요."}]}


def _intake_findings(domain: str, reasons: list[str]) -> list[dict[str, str]]:
    findings = []
    for reason in reasons:
        if domain == "tauc":
            title = "파장 범위와 측정점 수가 맞지 않아요" if any(word in reason for word in ("grid", "point", "range")) else "스펙트럼의 측정 정보를 확인해야 해요"
            action = "300~700 nm, 0.1 nm 간격의 4,001개 점이 모두 있는지 확인하고 원본 CSV를 다시 내보내 주세요."
            detail = "헤더의 범위·점 수와 실제로 읽힌 파장 데이터를 대조했습니다."
        else:
            title = "전류·전압 열을 연결하지 못했어요" if any(word in reason.lower() for word in ("열", "column", "mapping", "측정", "header")) else "측정 조건을 확인해야 해요"
            detail = reason if any("가" <= ch <= "힣" for ch in reason) else "재료, W/L, 전압·전류 열과 숫자 구성을 확인했습니다."
            action = "전류 열을 IDS(A), 전압 열을 VGS(V)·VDS(V)로 정리하고 재료와 W/L을 확인해 주세요."
        findings.append({"code": reason, "title": title, "detail": detail, "action": action})
    return findings


def _tft_points(intake_result: tft_file_intake.IntakeResult) -> list[dict[str, float]]:
    section = next((s for s in intake_result.sections if s.name == "MOBILITY"), None)
    if section is None:
        return []
    points = [{"x": row["VD"], "current_A": row["ID"], "root_current_A": math.sqrt(abs(row["ID"]))}
              for row in section.rows if row.get("VD") is not None and row.get("ID") is not None
              and math.isfinite(row["VD"]) and math.isfinite(row["ID"])]
    points.sort(key=lambda point: point["x"])
    if points and (len(points) > 5000 or abs(points[0]["x"]) > 1000 or abs(points[-1]["x"]) > 1000
                   or points[-1]["x"] - points[0]["x"] > 200
                   or max(abs(point["current_A"]) for point in points) > 1):
        raise ValueError("TFT 지원 범위를 벗어났어요. 5,000점 이하, 전압 ±1,000 V·범위 200 V 이하, 전류 ±1 A를 확인해 주세요.")
    return points


def _tft_candidates(
    intake_result: tft_file_intake.IntakeResult,
    polarity: str,
) -> tuple[list[dict[str, object]], list[dict[str, float]]]:
    points = _tft_points(intake_result)
    if len(points) < 2:
        return [], []
    candidates = profile.build_saturation_analysis_rows(
        source_file=intake_result.source_file,
        material=intake_result.material,
        width=intake_result.width_um,
        length=intake_result.length_um,
        analysis_scope="included",
        x=[point["x"] for point in points],
        current=[point["current_A"] for point in points],
        drive_sign={"p": -1, "n": 1}.get(polarity),
    )
    for candidate in candidates:
        start, end = sorted(
            (float(candidate["start_raw_V"]), float(candidate["end_raw_V"]))
        )
        selected = [point for point in points if start <= point["x"] <= end]
        slope, intercept, r2 = profile.linear_regression(
            [point["x"] for point in selected],
            [point["root_current_A"] for point in selected],
        )
        candidate["fit"] = {
            "slope": slope,
            "intercept": intercept,
            "r2": r2,
            "points": len(selected),
        }
        candidate.update(window_evidence(points, candidate, intake_result.width_um, intake_result.length_um))
        if not candidate["model_check"]["passed"]:
            candidate["reliability_status"] = "review_required"
    return candidates, points


def _analyze_tft(
    filename: str,
    raw: bytes,
    config: dict[str, object],
) -> dict[str, object]:
    try:
        content = _decode_tft(filename, raw)
    except ValueError as error:
        return {"status": "rejected", "message": str(error), "intake": {}}

    polarity = str(config.get("polarity", "auto"))
    if polarity not in {"auto", "p", "n"}:
        return {"status": "rejected", "message": "극성 선택을 확인해주세요.", "intake": {}}
    parse_name = _tft_parse_name(filename, config)
    result = tft_file_intake.inspect_uploaded_text(parse_name, content)
    result.source_file = Path(filename.replace("\\", "/")).name or "uploaded.csv"
    intake_summary = {
        "filename": result.source_file,
        "material": result.material,
        "width_um": result.width_um,
        "length_um": result.length_um,
        "format": result.format_kind,
        "point_count": result.input_count,
        "row_scope": "MOBILITY" if "DATA:" in content else "flat_table",
        "measurements": result.available_measurements,
        "headers": result.detected_headers,
        "mapping": result.detected_mappings,
        "warnings": result.warnings,
        "hold_reasons": result.hold_reasons,
        "input_count": result.input_count,
        "valid_count": result.valid_count,
        "excluded_count": result.excluded_count,
        "row_issues": result.row_issues,
    }
    payload: dict[str, object] = {
        "status": result.status,
        "message": "측정값을 읽었어요." if result.status == "ready" else "파일 정보를 더 확인해야 해요.",
        "intake": intake_summary,
        "data": {"points": [], "candidates": []},
        "findings": _intake_findings("tft", result.hold_reasons),
    }
    if result.status != "ready":
        if result.row_issues:
            points = [] if any(issue.get("kind") == "ambiguous_header" for issue in result.row_issues) else _tft_points(result)
            payload["data"]["points"] = points
            intake_summary["point_count"] = result.input_count
            detail = "; ".join(f"{issue['line']}행 {issue['column']}: {issue['value'] or '(빈칸)'}" for issue in result.row_issues[:5])
            voltages = sorted({issue["voltage"] for issue in result.row_issues if issue.get("voltage") is not None and math.isfinite(issue["voltage"])})
            payload["findings"] = [{"code": "invalid_numeric_rows", "title": "읽지 못한 측정값이 있어요",
                "detail": f"전체 {result.input_count}행 중 {result.excluded_count}행을 읽지 못했어요. {detail}",
                "action": "표시한 행과 열을 원파일에서 확인해 주세요. 값을 임의로 빼지 않고 계산을 보류했어요.",
                "ranges": [[v - .05, v + .05] for v in voltages], "blocking": True}]
            if any(issue.get("voltage") is None for issue in result.row_issues):
                payload["findings"][0]["action"] += " 전압 위치를 알 수 없는 행이 있어 미리보기는 점만 표시해요."
        preview = unknown_column_preview(content)
        if preview:
            payload["preview"] = preview
        return payload

    points = _tft_points(result)
    gaps = gap_findings(points)
    if gaps:
        payload.update(status="needs_confirmation", message="측정 간격을 확인한 뒤 구간을 계산해 주세요.")
        payload["data"]["points"] = points
        payload["findings"] = gaps
        return payload
    candidates, points = _tft_candidates(result, polarity)
    if not candidates:
        payload["status"] = "needs_confirmation"
        payload["message"] = "비교할 포화 구간 후보를 찾지 못했어요. 측정값을 확인해주세요."
        intake_summary["hold_reasons"] = [
            *result.hold_reasons,
            "실측점이 부족하거나 후보 구간을 만들지 못했습니다.",
        ]
    payload["data"] = {
        "points": points,
        "candidates": candidates,
        "measurements": result.available_measurements,
    }
    drive_sign = int(candidates[0]["drive_sign"]) if candidates else (-1 if result.material == "LTPS" else 1)
    payload["findings"] = [*payload["findings"], *review_saturation(points, candidates, drive_sign)]
    if candidates and not candidates[0]["model_check"]["passed"]:
        payload["findings"].append({"code":"bias_condition", "title":"포화 모델의 바이어스 조건 확인 필요",
            "detail":"VGS=VDS 매핑과 피팅한 Vth를 대입했을 때 VDS ≥ VGS−Vth 조건이 충족되지 않습니다.",
            "action":"연결 조건과 측정 기록을 확인한 뒤 이 구간의 이동도 사용 여부를 결정해 주세요."})
    gaps = gap_findings(points)
    if gaps:
        payload["findings"].extend(gaps)
        payload["status"] = "needs_confirmation"
        payload["data"]["candidates"] = []
        payload["message"] = "측정 간격을 확인한 뒤 구간을 계산해 주세요."
    if payload["status"] != "ready" and not payload["findings"]:
        payload["findings"] = [{"code": "no_candidate", "title": "비교할 구간 후보를 찾지 못했어요", "detail": "후보를 만들 만큼 측정점이나 구간이 충분하지 않습니다.", "action": "측정 범위와 측정점 수를 확인해 주세요."}]
    return payload


def _tauc_candidate_view(analysis: dict[str, object]) -> list[dict[str, object]]:
    output = []
    for combination in analysis.get("combinations", []):
        if not isinstance(combination, dict):
            continue
        candidates = combination.get("candidates", [])
        for candidate in candidates[:2]:
            if not isinstance(candidate, dict):
                continue
            output.append(
                {
                    "transition_model": combination.get("transition_model"),
                    "plot_id": combination.get("combination_id"),
                    "alpha_model": combination.get("alpha_model"),
                    "status": candidate.get("status"),
                    "rank": candidate.get("rank"),
                    "eg_ev": candidate.get("eg_eV", candidate.get("Eg_eV")),
                    "r2": candidate.get("r2"),
                    "normalized_rmse": candidate.get("normalized_rmse"),
                    "interval_ev": [candidate.get("start_eV"), candidate.get("end_eV")],
                    "energy_min_ev": candidate.get("start_eV"),
                    "energy_max_ev": candidate.get("end_eV"),
                    "slope": candidate.get("slope"),
                    "intercept": candidate.get("intercept"),
                    "points": candidate.get("points"),
                    "eg_shift_max_ev": candidate.get("eg_shift_max_eV"),
                    "eg_smoothing_delta_ev": candidate.get("eg_smoothing_delta_eV"),
                    "split_slope_delta": candidate.get("split_slope_delta"),
                    "rationale": candidate.get("rationale"),
                }
            )
    # Keep the model order; R² from different physical models is not a common ranking scale.
    return output


def _analyze_tauc(
    filename: str,
    raw: bytes,
    config: dict[str, object],
) -> dict[str, object]:
    material = str(config.get("material", ""))
    parser_name = TAUC_PROFILE_FILENAME.get(material)
    if parser_name is None:
        return {
            "status": "needs_confirmation",
            "message": "재료를 선택해주세요.",
            "intake": {"filename": filename, "hold_reasons": ["재료 정보가 필요합니다."]},
            "data": {},
        }
    result = tauc_file_intake.inspect_uploaded_bytes(parser_name, raw)
    result.source_file = filename
    intake_summary = {
        "filename": filename,
        "material": result.material if result.material != "unknown" else material,
        "encoding": result.encoding,
        "point_count": len(result.points),
        "hold_reasons": result.hold_reasons,
        "warnings": result.warnings,
    }
    payload: dict[str, object] = {
        "status": result.status,
        "message": "스펙트럼을 읽었어요." if result.status == "ready" else "측정 범위를 확인해주세요.",
        "intake": intake_summary,
        "data": {},
        "findings": _intake_findings("tauc", result.hold_reasons),
    }
    if result.status != "ready":
        preview, specific = optical_preview(raw)
        if preview:
            payload["preview"] = preview
            intake_summary["point_count"] = preview["point_count"]
        if specific:
            payload["findings"] = specific
        return payload

    analysis = tauc_analysis.analyze_intake(result)
    spectra = analysis["transmittance_points"]
    payload["data"] = {
        "point_count": len(result.points),
        "spectrum": spectra[::10] + (spectra[-1:] if spectra and (len(spectra) - 1) % 10 else []),
        "measurement_range": analysis["measurement_range"],
        "input_metadata": analysis["input_metadata"],
        "candidates": _tauc_candidate_view(analysis),
        "plots": {
            str(combination["combination_id"]): {
                "transition_model": combination["transition_model"],
                "points": [[point["energy_eV"], point["tauc_ordinate"]] for point in combination["points"][::max(1, len(combination["points"]) // 650)]],
            }
            for combination in analysis["combinations"]
        },
    }
    return payload


def analyze_bytes(
    domain: str,
    filename: str,
    raw: bytes,
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    config = dict(config or {})
    if domain == "tft":
        config["polarity"] = config.get("polarity", "auto")
    safe_filename = Path(filename.replace("\\", "/")).name or "uploaded.csv"
    if len(raw) > MAX_UPLOAD_BYTES:
        return {"status": "rejected", "message": "파일은 3 MB 이하로 올려주세요.", "intake": {}}
    if not raw:
        return {"status": "rejected", "message": "파일 내용이 비어 있어요.", "intake": {}}
    if domain not in {"tft", "tauc"}:
        return {"status": "rejected", "message": "분석 종류를 선택해주세요.", "intake": {}}
    if Path(safe_filename).suffix.lower() not in ({".dat", ".csv"} if domain == "tft" else {".csv"}):
        return input_error_response(ValueError("지원하는 파일 확장자를 확인해 주세요. TFT는 DAT·CSV, UV–Vis는 CSV를 읽어요."))
    if raw.count(b"\n") > 20000:
        return input_error_response(ValueError("파일당 20,000행까지 확인할 수 있어요. 측정 섹션을 나눠서 넣어주세요."))

    raw_hash = hashlib.sha256(raw).hexdigest()
    try:
        conditions = _conditions(domain, safe_filename, config)
        if not conditions["confirmed"]:
            result = _condition_hold(conditions)
        else:
            result = (_analyze_tft(safe_filename, raw, config) if domain == "tft"
                      else _analyze_tauc(safe_filename, raw, config))
            result["conditions"] = conditions
            if conditions["override"]:
                result.setdefault("findings", []).append({"code": "conditions_override", "title": "입력한 조건으로 계산했어요",
                    "detail": "파일명에서 읽힌 조건과 달라요. 사용자가 확인한 입력 조건을 적용했어요.",
                    "action": "의도한 변경인지 결과 옆의 측정 조건을 다시 확인해 주세요."})
    except (csv.Error, UnicodeError, ValueError, ArithmeticError) as error:
        result = input_error_response(error)
    result.update(
        {
            "domain": domain,
            "filename": safe_filename,
            "sha256": raw_hash,
            "analysis_version": ANALYSIS_VERSION,
            "decision_key": _decision_key(domain, raw, config),
        }
    )
    return _json_safe(result)


def input_error_response(error: Exception) -> dict:
    message = str(error)
    if isinstance(error, csv.Error):
        code, message = "csv_structure", "CSV의 구분자나 셀 길이를 확인해 주세요. 한 셀은 131,072자까지 읽을 수 있어요."
    elif isinstance(error, ArithmeticError):
        code, message = "numeric_range", "계산 범위를 벗어난 숫자가 있어요. 전압·전류 값과 단위를 확인해 주세요."
    else:
        code = "input_values"
        if not any("가" <= ch <= "힣" for ch in message):
            message = "파일의 숫자 형식과 측정 조건을 확인해 주세요."
    return {"status": "needs_confirmation", "code": code, "message": message, "intake": {}, "data": {},
            "findings": [{"code": code, "title": "파일을 확인한 뒤 다시 분석해 주세요", "detail": message,
                          "action": "원파일의 해당 값이나 형식을 고친 뒤 새 파일을 선택해 주세요.", "blocking": True}]}


def analyze_request(payload: dict[str, object]) -> dict[str, object]:
    sample_id = payload.get("sample_id")
    if sample_id:
        try:
            sample, raw = get_sample(str(sample_id))
        except KeyError:
            return {"status": "rejected", "message": "샘플을 찾지 못했어요.", "intake": {}}
        config = sample.get("profile") if isinstance(sample.get("profile"), dict) else {}
        if sample["domain"] == "tauc" and isinstance(config, dict):
            config = {**config, "material": config.get("material")}
        result = analyze_bytes(str(sample["domain"]), str(sample["filename"]), raw, config)
        result["sample"] = {key: sample[key] for key in ("id", "title", "kind", "source", "modification", "lesson", "material", "filename")}
        if sample.get("control_id"):
            control, _ = get_sample(str(sample["control_id"]))
            result["sample"]["control_id"] = control["id"]
            result["sample"]["control_title"] = control["title"]
        return result

    domain = str(payload.get("domain", ""))
    filename = str(payload.get("filename", "uploaded.csv"))
    encoded = payload.get("content_base64")
    if not isinstance(encoded, str):
        return {"status": "rejected", "message": "파일을 선택해주세요.", "intake": {}}
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        return {"status": "rejected", "message": "파일을 읽지 못했어요. 다시 선택해주세요.", "intake": {}}
    config_value = payload.get("config")
    config = config_value if isinstance(config_value, dict) else {}
    return analyze_bytes(domain, filename, raw, config)


def sample_file(sample_id: str) -> tuple[str, bytes]:
    sample, raw = get_sample(sample_id)
    return str(sample["filename"]), raw


def public_samples() -> list[dict[str, object]]:
    return sample_catalog()
