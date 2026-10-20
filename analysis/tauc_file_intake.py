from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from pathlib import Path


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SAMPLE_CONFIGS = {
    "a-si.csv": {
        "material": "a-Si",
        "thickness_nm": 50.0,
        "film_n": 4.045,
        "transitions": ["indirect_allowed"],
    },
    "poly-si.csv": {
        "material": "Poly-Si",
        "thickness_nm": 50.0,
        "film_n": 3.715,
        "transitions": ["indirect_allowed"],
    },
    "a-igzo.csv": {
        "material": "a-IGZO",
        "thickness_nm": 40.0,
        "film_n": 1.92,
        "transitions": ["legacy_amorphous", "direct_allowed"],
    },
}


@dataclass(frozen=True)
class TaucPoint:
    wavelength_nm: float
    transmittance_percent: float


@dataclass
class TaucIntakeResult:
    status: str
    source_file: str
    material: str = "unknown"
    thickness_nm: float | None = None
    film_refractive_index: float | None = None
    transition_models: list[str] = field(default_factory=list)
    encoding: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    points: list[TaucPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hold_reasons: list[str] = field(default_factory=list)


def safe_name(filename: str) -> str:
    return Path(str(filename).replace("\\", "/")).name or "uploaded.csv"


def decode_uploaded_bytes(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("unsupported_encoding")


def _result(
    status: str,
    source_file: str,
    *,
    encoding: str = "",
    metadata: dict[str, object] | None = None,
    points: list[TaucPoint] | None = None,
    hold_reasons: list[str] | None = None,
) -> TaucIntakeResult:
    return TaucIntakeResult(
        status=status,
        source_file=source_file,
        encoding=encoding,
        metadata=metadata or {},
        points=points or [],
        hold_reasons=hold_reasons or [],
    )


def inspect_uploaded_bytes(filename: str, raw: bytes) -> TaucIntakeResult:
    source_file = safe_name(filename)
    if Path(source_file).suffix.lower() != ".csv":
        return _result(
            "rejected",
            source_file,
            hold_reasons=["JASCO CSV만 지원합니다."],
        )
    if not raw:
        return _result(
            "rejected",
            source_file,
            hold_reasons=["파일 내용이 비어 있습니다."],
        )
    if len(raw) > MAX_UPLOAD_BYTES:
        return _result(
            "rejected",
            source_file,
            hold_reasons=["파일 크기가 10 MB를 초과합니다."],
        )

    try:
        text, encoding = decode_uploaded_bytes(raw)
    except ValueError:
        return _result(
            "rejected",
            source_file,
            hold_reasons=["unsupported_encoding"],
        )

    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            hold_reasons=["invalid_csv_structure"],
        )
    xy_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row and row[0].strip().upper() == "XYDATA"
        ),
        None,
    )
    if xy_index is None:
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            hold_reasons=["jasco_xydata_missing"],
        )

    metadata = {
        row[0].strip().upper(): row[1].strip()
        for row in rows[:xy_index]
        if len(row) >= 2 and row[0].strip()
    }
    required = {
        "DATA TYPE",
        "ORIGIN",
        "DELTAX",
        "XUNITS",
        "YUNITS",
        "FIRSTX",
        "LASTX",
        "NPOINTS",
    }
    if not required.issubset(metadata):
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            hold_reasons=["jasco_metadata_missing"],
        )
    if (
        metadata["ORIGIN"].upper() != "JASCO"
        or metadata["DATA TYPE"].upper() != "ULTRAVIOLET SPECTRUM"
        or metadata["XUNITS"].upper() != "NANOMETERS"
        or metadata["YUNITS"].upper() != "TRANSMITTANCE"
    ):
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            hold_reasons=["unsupported_axis_or_quantity"],
        )

    try:
        npoints = int(metadata["NPOINTS"])
        first_x = float(metadata["FIRSTX"])
        last_x = float(metadata["LASTX"])
        delta_x = float(metadata["DELTAX"])
        if npoints <= 0 or not all(
            math.isfinite(value) for value in (first_x, last_x, delta_x)
        ):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            hold_reasons=["invalid_jasco_metadata_value"],
        )

    numeric_rows = []
    for row in rows[xy_index + 1:]:
        if row and row[0].strip().startswith("#####"):
            break
        if any(cell.strip() for cell in row):
            numeric_rows.append(row)
    if len(numeric_rows) != npoints:
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            hold_reasons=["point_count_mismatch"],
        )

    points: list[TaucPoint] = []
    for row in numeric_rows:
        try:
            wavelength_nm = float(row[0])
            transmittance_percent = float(row[1])
        except (IndexError, TypeError, ValueError, OverflowError):
            return _result(
                "needs_confirmation",
                source_file,
                encoding=encoding,
                metadata=metadata,
                hold_reasons=["point_count_mismatch"],
            )
        if (
            not math.isfinite(wavelength_nm)
            or wavelength_nm <= 0
            or not math.isfinite(transmittance_percent)
            or not 0 < transmittance_percent <= 100
        ):
            return _result(
                "needs_confirmation",
                source_file,
                encoding=encoding,
                metadata=metadata,
                hold_reasons=["invalid_wavelength_or_transmittance"],
            )
        points.append(TaucPoint(wavelength_nm, transmittance_percent))

    points.sort(key=lambda point: point.wavelength_nm)
    if len({point.wavelength_nm for point in points}) != npoints:
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            points=points,
            hold_reasons=["duplicate_wavelength"],
        )

    spacing_ok = all(
        abs(
            points[index + 1].wavelength_nm
            - points[index].wavelength_nm
            - 0.1
        )
        <= 1e-6
        for index in range(len(points) - 1)
    )
    metadata_grid_ok = (
        abs(first_x - 700.0) <= 1e-6
        and abs(last_x - 300.0) <= 1e-6
        and abs(delta_x + 0.1) <= 1e-9
    )
    if (
        abs(points[0].wavelength_nm - 300.0) > 1e-6
        or abs(points[-1].wavelength_nm - 700.0) > 1e-6
        or npoints != 4001
        or not spacing_ok
        or not metadata_grid_ok
    ):
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata=metadata,
            points=points,
            hold_reasons=["measurement_grid_mismatch"],
        )

    common_metadata = {
        "baseline_type": "air",
        "substrate": "glass",
        "same_substrate_family": True,
        "air_refractive_index": 1.0,
        "glass_refractive_index": 1.5,
        "metadata_source": "experiment_provided",
    }
    config = SAMPLE_CONFIGS.get(source_file.lower())
    if config is None:
        return _result(
            "needs_confirmation",
            source_file,
            encoding=encoding,
            metadata={**metadata, **common_metadata},
            points=points,
            hold_reasons=["sample_metadata_unconfirmed"],
        )

    return TaucIntakeResult(
        status="ready",
        source_file=source_file,
        material=str(config["material"]),
        thickness_nm=float(config["thickness_nm"]),
        film_refractive_index=float(config["film_n"]),
        transition_models=list(config["transitions"]),
        encoding=encoding,
        metadata={**metadata, **common_metadata},
        points=points,
    )


