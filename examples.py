"""Measured controls and reproducible modified copies used by both demo and upload."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

SAMPLE_ROOT = Path(__file__).resolve().parent / "samples"
SAMPLES: dict[str, dict] = {}


def add_tft(sample_id: str, material: str, prefix: str, width: int, length: int, asset: str) -> None:
    SAMPLES[sample_id] = {
        "id": sample_id, "domain": "tft", "kind": "measured", "material": material,
        "title": f"{material} · W{width}/L{length}",
        "description": f"채널 폭 {width} μm, 길이 {length} μm의 실측 곡선이에요.",
        "filename": f"{prefix}{width:02d}{length:02d}.csv", "asset": asset,
        "width_um": width, "length_um": length,
        "profile": {"material": material, "width_um": width, "length_um": length, "conditions_confirmed": True},
        "source": f"TFT 실험자료 · {material} W{width}/L{length} · MOBILITY 발췌",
        "modification": "측정 숫자를 유지하고 VD·ID 열을 VGS=VDS·IDS로 연결했습니다.",
        "lesson": "대표 구간과 주변 구간에서의 결과 변화를 함께 보세요. 자세한 후보는 아래에서 펼쳐볼 수 있어요.",
    }


for row in [
    ("tft-asi-02", "a-Si", "aSi", 20, 2, "asi20_02.csv"),
    ("tft-asi-06", "a-Si", "aSi", 20, 6, "asi20_06.csv"),
    ("tft-asi-20", "a-Si", "aSi", 20, 20, "asi20_20.csv"),
    ("tft-clear", "a-IGZO", "IGZO", 20, 4, "igzo20_04.csv"),
    ("tft-igzo-02", "a-IGZO", "IGZO", 20, 2, "igzo20_02.csv"),
    ("tft-igzo-10", "a-IGZO", "IGZO", 20, 10, "igzo20_10.csv"),
    ("tft-window", "LTPS", "LTPS", 10, 2, "ltps10_02.csv"),
    ("tft-ltps-05", "LTPS", "LTPS", 10, 5, "ltps10_05.csv"),
    ("tft-ltps-10", "LTPS", "LTPS", 10, 10, "ltps10_10.csv"),
]:
    add_tft(*row)

FAULTS = {
    "spike": ("전류 한 점이 튀는 파일", "튀는 점의 위치와 주변 측정값을 비교해 보세요.", "전류 한 점을 원본 최대 절댓값의 15배로 바꿨습니다."),
    "gap": ("중간 측정점이 빠진 파일", "측정 간격이 벌어진 곳을 그래프에서 찾아보세요.", "중앙의 연속된 측정점 11개를 삭제했습니다."),
    "missing_current": ("전류 열 이름이 빠진 파일", "숫자는 있지만 어떤 물리량인지 확인이 필요한 경우예요.", "IDS 열 이름만 UNKNOWN으로 바꿨습니다. 숫자는 유지했습니다."),
    "short_spectrum": ("측정 범위가 잘린 파일", "실제로 남은 구간과 헤더가 요구하는 범위를 비교해요.", "4,001점 헤더는 두고 300~380 nm의 801개 점만 남겼습니다."),
    "invalid_percent": ("투과율이 범위를 벗어난 파일", "100% 기준선 밖의 측정점을 확인해 보세요.", "400 nm의 투과율 한 점을 120%로 바꿨습니다."),
}


def add_fault(sample_id: str, control_id: str, fault: str) -> None:
    sample = deepcopy(SAMPLES[control_id])
    title, description, change = FAULTS[fault]
    sample.update(
        id=sample_id, kind="modified", control_id=control_id, fault=fault,
        title=title, description=description,
        filename=sample["filename"].replace(".csv", f"_{fault}.csv"),
        source=sample["source"] + " · 오류 주입 복사본",
        modification=change,
        lesson="확인 의견에서 위치를 누르고, 그래프의 표시와 원본 대조를 살펴보세요. 안내에 따라 파일을 고친 뒤 다시 넣어보세요.",
    )
    SAMPLES[sample_id] = sample


for material, control, key in [("a-Si", "tft-asi-06", "asi"), ("a-IGZO", "tft-clear", "igzo"), ("LTPS", "tft-window", "ltps")]:
    for fault in ("spike", "gap", "missing_current"):
        sample_id = {("igzo", "spike"): "tft-spike", ("igzo", "missing_current"): "tft-hold"}.get((key, fault), f"tft-{key}-{fault}")
        add_fault(sample_id, control, fault)

for sample_id, material, filename, asset in [
    ("tauc-clear", "a-Si", "a-Si.csv", "a_si_uvvis.csv"),
    ("tauc-igzo", "a-IGZO", "a-IGZO.csv", "a_igzo_uvvis.csv"),
    ("tauc-poly", "Poly-Si", "poly-Si.csv", "poly_si_uvvis.csv"),
]:
    SAMPLES[sample_id] = {
        "id": sample_id, "domain": "tauc", "kind": "measured", "material": material,
        "title": f"{material} · 실측 투과율", "description": "300~700 nm의 실측 4,001점으로 스펙트럼과 Tauc 변환을 살펴봐요.",
        "filename": filename, "asset": asset, "profile": {"material": material, "conditions_confirmed": True},
        "source": f"UV–Vis 실험자료 · {material} · JASCO 투과율 CSV",
        "modification": "파장·투과율 숫자와 700→300 nm 측정 순서를 유지했습니다. 개인 메타데이터는 제외했습니다.",
        "lesson": "원본 스펙트럼과 변환 후 직선 구간을 연결해 보세요. 서로 다른 모델의 후보는 계산 조건을 함께 확인해 주세요.",
    }
    for fault in ("short_spectrum", "invalid_percent"):
        fault_id = "tauc-range" if sample_id == "tauc-clear" and fault == "short_spectrum" else f"{sample_id}-{fault}"
        add_fault(fault_id, sample_id, fault)


def get_sample(sample_id: str) -> tuple[dict, bytes]:
    sample = deepcopy(SAMPLES[sample_id])
    raw = (SAMPLE_ROOT / sample["asset"]).read_bytes()
    fault = sample.get("fault")
    if fault == "missing_current":
        raw = raw.replace(b"VGS,VDS,IDS", b"VGS,VDS,UNKNOWN", 1)
    elif fault in {"spike", "gap"}:
        rows = raw.decode("utf-8").splitlines()
        index = 1 + (len(rows) - 1) // 2
        if fault == "gap":
            del rows[index - 5:index + 6]
        else:
            currents = [abs(float(row.split(",")[2])) for row in rows[1:]]
            cells = rows[index].split(",")
            cells[2] = format(max(currents) * 15, ".17g")
            rows[index] = ",".join(cells)
        raw = ("\n".join(rows) + "\n").encode()
    elif fault in {"short_spectrum", "invalid_percent"}:
        header, data = raw.decode().split("XYDATA,\n", 1)
        rows = data.splitlines()
        if fault == "short_spectrum":
            rows = [row for row in rows if float(row.split(",")[0]) <= 380]
        else:
            index = next(i for i, row in enumerate(rows) if abs(float(row.split(",")[0]) - 400) < 1e-6)
            cells = rows[index].split(",")
            cells[1] = "120"
            rows[index] = ",".join(cells)
        raw = (header + "XYDATA,\n" + "\n".join(rows) + "\n").encode()
    return sample, raw


def sample_catalog() -> list[dict]:
    return [{key: deepcopy(value) for key, value in item.items() if key not in {"asset", "fault", "profile"}} for item in SAMPLES.values()]
