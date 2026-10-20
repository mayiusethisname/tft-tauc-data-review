"""Compare public numeric excerpts with originals, without analysis transforms."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tft_pairs(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="latin1" if path.suffix.lower() == ".dat" else "utf-8-sig")
    rows = csv.reader(io.StringIO(text), delimiter="\t" if path.suffix.lower() == ".dat" else ",")
    active, header, pairs = False, None, []
    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue
        marker = " ".join(cell.strip() for cell in row if cell.strip())
        if marker.startswith("DATA:"):
            if active:
                break
            active = marker.split()[1] == "MOBILITY"
            continue
        if not active:
            continue
        if header is None:
            if "VD" in row and "ID" in row:
                header = row
            continue
        x, y = float(row[header.index("VD")]), float(row[header.index("ID")])
        assert math.isfinite(x) and math.isfinite(y), path.name
        pairs.append((x, y))
    assert pairs, f"No MOBILITY pairs: {path.name}"
    return pairs


def optical_pairs(path: Path) -> list[tuple[float, float]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949")
    rows = list(csv.reader(io.StringIO(text)))
    start = next(i for i, row in enumerate(rows) if row and row[0].strip() == "XYDATA")
    pairs = []
    for row in rows[start + 1:]:
        if row and row[0].startswith("#####"):
            break
        if row and row[0].strip():
            pairs.append((float(row[0]), float(row[1])))
    assert pairs and all(math.isfinite(v) for pair in pairs for v in pair), path.name
    return pairs


def compare_pairs(before: list, after: list, label: str) -> None:
    assert len(before) == len(after), f"{label}: point count differs"
    differences = [(i + 1, a, b) for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert not differences, f"{label}: {len(differences)} numeric differences; first={differences[:1]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tft-dir", type=Path, required=True)
    parser.add_argument("--uvvis-dir", type=Path, required=True)
    args = parser.parse_args()
    # Positive control: a sign change must be detected by the same comparison.
    try:
        compare_pairs([(0.0, -1.0)], [(0.0, 1.0)], "sign-control")
    except AssertionError:
        pass
    else:
        raise AssertionError("Comparison failed to detect sign loss")
    manifest = json.loads((ROOT / "samples/manifest.json").read_text(encoding="utf-8"))
    total = negative = 0
    for item in manifest["files"]:
        asset = ROOT / "samples" / item["asset"]
        source = (args.uvvis_dir if item["source_section"] == "XYDATA" else args.tft_dir) / item["source_name"]
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == item["sha256"], asset.name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["source_sha256"], source.name
        if item["source_section"] == "XYDATA":
            before, after = optical_pairs(source), optical_pairs(asset)
        else:
            before = tft_pairs(source)
            rows = list(csv.DictReader(io.StringIO(asset.read_text(encoding="utf-8"))))
            assert all(float(row["VGS"]) == float(row["VDS"]) for row in rows), asset.name
            after = [(float(row["VDS"]), float(row["IDS"])) for row in rows]
            negative += sum(y < 0 for _, y in before)
        compare_pairs(before, after, asset.name)
        assert len(after) == item["point_count"], asset.name
        total += len(after)
        print(f"{asset.name}: {len(after)} pairs, 0 differences")
    print(f"SOURCE_VERIFIED {len(manifest['files'])} files, {total} pairs, {negative} signed negative currents preserved")


if __name__ == "__main__":
    main()
