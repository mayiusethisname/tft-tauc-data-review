"""Local-only DAT/CSV structure inspection for the TFT review prototype."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import profile_8week as profile


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_SUFFIXES = {".dat", ".csv"}


@dataclass
class IntakeResult:
    status: str
    source_file: str
    material: str = "unknown"
    width_um: int = 0
    length_um: int = 0
    format_kind: str = "unknown"
    sections: list[profile.Section] = field(default_factory=list)
    available_measurements: list[str] = field(default_factory=list)
    detected_mappings: dict[str, str] = field(default_factory=dict)
    detected_headers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hold_reasons: list[str] = field(default_factory=list)
    input_count: int = 0
    valid_count: int = 0
    excluded_count: int = 0
    row_issues: list[dict] = field(default_factory=list)


ALIASES = {
    "VGS": {"VG", "VGS", "GATEVOLTAGE", "GATEV"},
    "VDS": {"VD", "VDS", "DRAINVOLTAGE", "DRAINV"},
    "IDS": {"ID", "IDS", "IID", "DRAINCURRENT", "DRAINI"},
    "IGS": {"IG", "IGS", "GATECURRENT", "GATEI"},
}


def safe_name(filename: str) -> str:
    return Path(str(filename).replace("\\", "/")).name or "uploaded.dat"


def normalized_header(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def infer_mapping(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    matches: dict[str, list[str]] = {key: [] for key in ALIASES}
    for header in headers:
        normalized = normalized_header(header)
        for canonical, aliases in ALIASES.items():
            if normalized in aliases:
                matches[canonical].append(header)
    mapping = {key: values[0] for key, values in matches.items() if len(values) == 1}
    ambiguous = [key for key, values in matches.items() if len(values) > 1]
    return mapping, ambiguous


def parse_float(value: str) -> float | None:
    try:
        number = float(value.strip())
        return number if math.isfinite(number) else None
    except (AttributeError, ValueError):
        return None


def available_from_sections(sections: list[profile.Section]) -> list[str]:
    names = {section.name for section in sections}
    available: list[str] = []
    if "MOBILITY" in names:
        available.append("saturation")
    if "LOWTRANS" in names:
        available.append("transfer")
    if "OUTPUT_2" in names:
        available.append("output")
    return available


def parse_sectioned(filename: str, content: str) -> list[profile.Section]:
    """Keep every source row; auxiliary cells never discard a valid VD/ID pair."""
    reader = csv.reader(io.StringIO(content), delimiter="\t" if Path(filename).suffix.lower() == ".dat" else ",")
    sections, rows, widths = [], [], []
    marker, name, date, header = "", "", "", []
    def flush():
        if name and header:
            sections.append(profile.Section(name=name, marker=marker, measured_at=date, header=header,
                                            rows=rows.copy(), raw_widths=sorted(set(widths)),
                                            missing_tokens=sum(value is None for row in rows for value in row.values())))
    for tokens in reader:
        if not tokens or not any(token.strip() for token in tokens):
            continue
        joined = " ".join(token.strip() for token in tokens if token.strip())
        if joined.startswith("DATA:"):
            flush()
            marker = joined
            name, date = profile.parse_marker(marker)
            header, rows, widths = [], [], []
        elif name and not header and profile.looks_like_header(tokens):
            header = profile.normalize_header(tokens)
        elif name and header:
            widths.append(len(tokens))
            rows.append({key: parse_float(tokens[i]) if i < len(tokens) else None for i, key in enumerate(header)})
    flush()
    return sections


def flat_rows(content: str) -> tuple[list[str], list[list[str]]]:
    sample = content[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    raw = [row for row in csv.reader(io.StringIO(content), dialect) if any(cell.strip() for cell in row)]
    if not raw:
        return [], []
    headers = [cell.strip() for cell in raw[0]]
    return headers, raw[1:]


def unique_count(values: list[float]) -> int:
    return len({round(value, 12) for value in values})


def build_flat_section(headers: list[str], rows: list[list[str]]) -> tuple[profile.Section | None, dict[str, str], list[str]]:
    mapping, ambiguous = infer_mapping(headers)
    if ambiguous or not {"VGS", "VDS", "IDS"}.issubset(mapping):
        return None, mapping, ambiguous
    indices = {canonical: headers.index(actual) for canonical, actual in mapping.items()}
    parsed: list[tuple[float, float, float]] = []
    for row in rows:
        if len(row) <= max(indices["VGS"], indices["VDS"], indices["IDS"]):
            continue
        vgs = parse_float(row[indices["VGS"]])
        vds = parse_float(row[indices["VDS"]])
        ids = parse_float(row[indices["IDS"]])
        if vgs is not None and vds is not None and ids is not None:
            parsed.append((vgs, vds, ids))
    if len(parsed) < 2:
        return None, mapping, ambiguous

    vgs_values = [row[0] for row in parsed]
    vds_values = [row[1] for row in parsed]
    same_voltage = all(abs(vgs - vds) <= 1e-9 for vgs, vds, _ in parsed)
    if same_voltage:
        name = "MOBILITY"
        canonical_header = ["VD", "ID"]
        canonical_rows = [{"VD": vgs, "ID": ids} for vgs, _, ids in parsed]
    elif unique_count(vgs_values) > 1 and unique_count(vds_values) == 1:
        name = "LOWTRANS"
        canonical_header = ["VG", "VD", "IID"]
        canonical_rows = [{"VG": vgs, "VD": vds, "IID": ids} for vgs, vds, ids in parsed]
    elif unique_count(vds_values) > 1 and unique_count(vgs_values) == 1:
        name = "OUTPUT_2"
        canonical_header = ["VD", "ID", "VG"]
        canonical_rows = [{"VD": vds, "ID": ids, "VG": vgs} for vgs, vds, ids in parsed]
    else:
        return None, mapping, ambiguous
    section = profile.Section(
        name=name,
        marker="UPLOADED FLAT TABLE",
        measured_at="",
        header=canonical_header,
        rows=canonical_rows,
        raw_widths=[len(headers)],
        missing_tokens=0,
    )
    return section, mapping, ambiguous


def _inspect_uploaded_text(filename: str, content: str) -> IntakeResult:
    filename = safe_name(filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return IntakeResult(status="rejected", source_file=filename, hold_reasons=["DAT와 CSV만 지원합니다."])
    if not content or not content.strip():
        return IntakeResult(status="rejected", source_file=filename, hold_reasons=["파일 내용이 비어 있습니다."])
    if len(content.encode("utf-8")) > MAX_UPLOAD_BYTES:
        return IntakeResult(status="rejected", source_file=filename, hold_reasons=["파일 크기가 10 MB를 초과합니다."])

    material, width, length = profile.material_and_dimensions(Path(filename))
    if "DATA:" in content:
        sections = parse_sectioned(filename, content)
        available = available_from_sections(sections)
        if not available:
            return IntakeResult(
                status="needs_confirmation",
                source_file=filename,
                material=material,
                width_um=width,
                length_um=length,
                format_kind="sectioned_dat" if suffix == ".dat" else "sectioned_csv",
                hold_reasons=["포화·전이·출력 측정 섹션을 찾지 못했습니다."],
            )
        if material == "unknown" or not width or not length:
            return IntakeResult(
                status="needs_confirmation",
                source_file=filename,
                material=material,
                width_um=width,
                length_um=length,
                format_kind="sectioned_dat" if suffix == ".dat" else "sectioned_csv",
                sections=sections,
                available_measurements=available,
                hold_reasons=["재료와 W/L을 파일명에서 확인할 수 없습니다."],
            )
        return IntakeResult(
            status="ready",
            source_file=filename,
            material=material,
            width_um=width,
            length_um=length,
            format_kind="sectioned_dat" if suffix == ".dat" else "sectioned_csv",
            sections=sections,
            available_measurements=available,
        )

    headers, rows = flat_rows(content)
    section, mapping, ambiguous = build_flat_section(headers, rows)
    if section is None:
        reasons = ["VGS/VDS/IDS 열을 확정할 수 없습니다."]
        if ambiguous:
            reasons.append("같은 역할로 해석되는 열이 둘 이상입니다: " + ", ".join(ambiguous))
        return IntakeResult(
            status="needs_confirmation",
            source_file=filename,
            material=material,
            width_um=width,
            length_um=length,
            format_kind="flat_table",
            detected_mappings=mapping,
            detected_headers=headers,
            hold_reasons=reasons,
        )
    if material == "unknown" or not width or not length:
        return IntakeResult(
            status="needs_confirmation",
            source_file=filename,
            material=material,
            width_um=width,
            length_um=length,
            format_kind="flat_table",
            sections=[section],
            available_measurements=available_from_sections([section]),
            detected_mappings=mapping,
            detected_headers=headers,
            hold_reasons=["재료와 W/L을 파일명에서 확인할 수 없습니다."],
        )
    return IntakeResult(
        status="ready",
        source_file=filename,
        material=material,
        width_um=width,
        length_um=length,
        format_kind="flat_table",
        sections=[section],
        available_measurements=available_from_sections([section]),
        detected_mappings=mapping,
        detected_headers=headers,
        warnings=["열 이름을 기준으로 전압은 V, 전류는 A로 해석했습니다."],
    )


def audit_numeric_rows(content: str) -> tuple[int, int, list[dict]]:
    """Read source line numbers before the legacy section parser can discard rows."""
    sectioned = "DATA:" in content
    active = not sectioned
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in content[:8192] else csv.excel
    reader = csv.reader(io.StringIO(content), dialect)
    indices, headers = {}, []
    ambiguous_header = False
    count = excluded = 0
    issues = []
    for row in reader:
        if reader.line_num > 20000:
            raise ValueError("이 도구는 파일당 20,000행까지 확인할 수 있어요. 측정 섹션을 나눠서 넣어주세요.")
        if not row or not any(cell.strip() for cell in row):
            continue
        marker = " ".join(cell.strip() for cell in row if cell.strip())
        if sectioned and marker.startswith("DATA:"):
            indices, headers = {}, []
            ambiguous_header = False
            active = len(marker.split()) > 1 and marker.split()[1] == "MOBILITY"
            continue
        if not active:
            continue
        if not headers:
            mapping, ambiguous = infer_mapping([cell.strip() for cell in row])
            required = {"VGS", "VDS", "IDS"} if not sectioned else set(mapping) & {"VGS", "VDS", "IDS", "IGS"}
            if ambiguous and len(mapping) + len(ambiguous) >= 2:
                headers = [cell.strip() for cell in row]
                ambiguous_header = True
                issues.append({"line": reader.line_num, "column": ", ".join(ambiguous),
                               "value": "같은 역할의 열이 둘 이상이에요", "voltage": None, "kind": "ambiguous_header"})
                continue
            if len(required) < 2 or not required.issubset(mapping):
                continue
            headers = [cell.strip() for cell in row]
            indices = {key: headers.index(mapping[key]) for key in required}
            continue
        count += 1
        if ambiguous_header:
            excluded += 1
            continue
        bad = []
        for key, index in indices.items():
            token = row[index].strip() if index < len(row) else ""
            if parse_float(token) is None:
                bad.append({"line": reader.line_num, "column": headers[index], "value": token[:80]})
        if bad:
            excluded += 1
            voltage = next((parse_float(row[index]) for key, index in indices.items()
                            if key in {"VGS", "VDS"} and index < len(row) and parse_float(row[index]) is not None), None)
            for issue in bad:
                issue["voltage"] = voltage
            issues.extend(bad[:max(0, 100 - len(issues))])
    return count, excluded, issues


def inspect_uploaded_text(filename: str, content: str) -> IntakeResult:
    count, excluded, issues = audit_numeric_rows(content)
    result = _inspect_uploaded_text(filename, content)
    result.input_count, result.valid_count = count, count - excluded
    result.excluded_count, result.row_issues = excluded, issues
    if issues and result.status != "rejected":
        result.status = "needs_confirmation"
        result.hold_reasons.append("invalid_numeric_rows")
    return result


