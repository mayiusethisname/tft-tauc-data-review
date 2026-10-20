"""Draw only explicit numeric columns; previews never substitute for validated fits."""
from __future__ import annotations

import csv
import io
import math
from statistics import median


def gap_findings(points: list[dict]) -> list[dict]:
    xs = sorted({float(p['x']) for p in points})
    steps = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    if len(steps) < 6:
        return []
    usual = median(steps)
    ranges = [[a, b] for a, b in zip(xs, xs[1:]) if b - a > 5 * usual + 1e-8]
    if not ranges:
        return []
    largest = max(b - a for a, b in ranges)
    return [{
        'code': 'measurement_gap', 'title': '주변보다 측정 간격이 넓은 곳이 있어요',
        'detail': f'보통 간격은 {usual:.3g} V인데, 표시한 구간은 최대 {largest:.3g} V입니다. 중간 값은 연결하거나 채우지 않았어요.',
        'action': '의도적으로 측정 간격을 바꾼 건지, 내보내는 과정에서 행이 빠진 건지 확인해 주세요. 원본을 확인한 뒤 다시 분석해 주세요.',
        'ranges': ranges, 'blocking': True,
    }]


def unknown_column_preview(content: str) -> dict | None:
    """An unknown numeric column may be displayed by its literal header, without units."""
    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = reader.fieldnames or []
        if not {'VGS', 'VDS'}.issubset(headers) or 'IDS' in headers:
            return None
        unknown = [h for h in headers if h not in {'VGS', 'VDS'}]
        if len(unknown) != 1:
            return None
        column = unknown[0]
        points = []
        for row in reader:
            x, y = float(row['VGS']), float(row[column])
            if math.isfinite(x) and math.isfinite(y) and abs(x) <= 1000 and abs(y) <= 1e100:
                points.append([x, y])
        if len(points) < 2:
            return None
        return {
            'title': '열 확인 전 · 원본 숫자 미리보기', 'x_label': 'VGS 열의 원본 숫자',
            'y_label': f'{column} 열 (단위 미확정)', 'points': sorted(points),
            'note': f'{column}을 전류로 가정하지 않고 숫자만 표시했어요. 열 이름과 단위를 확인하면 물리량 계산을 진행할 수 있어요.',
            'table': {'headers': headers, 'rows': [[str(v) for v in row.values()] for row in list(csv.DictReader(io.StringIO(content)))[:3]]},
            'annotations': [],
        }
    except (ValueError, TypeError, csv.Error, KeyError):
        return None


def optical_preview(raw: bytes) -> tuple[dict | None, list[dict]]:
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = raw.decode('cp949')
        except UnicodeDecodeError:
            return None, []
    rows = list(csv.reader(io.StringIO(text)))
    split = next((i for i, r in enumerate(rows) if r and r[0].strip().upper() == 'XYDATA'), None)
    if split is None:
        return None, []
    metadata = {r[0].strip().upper(): r[1].strip() for r in rows[:split] if len(r) > 1}
    # A plot is allowed only when the file explicitly identifies both physical axes.
    if metadata.get('XUNITS', '').upper() != 'NANOMETERS' or metadata.get('YUNITS', '').upper() != 'TRANSMITTANCE':
        return None, []
    points = []
    for row in rows[split + 1:]:
        if row and row[0].strip().startswith('#####'):
            break
        if len(row) < 2:
            continue
        try:
            x, y = float(row[0]), float(row[1])
        except ValueError:
            continue
        if math.isfinite(x) and math.isfinite(y) and abs(x) <= 1e6 and abs(y) <= 1e6:
            points.append([x, y])
    if len(points) < 2:
        return None, []
    points.sort()
    findings, annotations = [], []
    try:
        lo, hi = sorted((float(metadata['FIRSTX']), float(metadata['LASTX'])))
        count = int(metadata['NPOINTS'])
        if not math.isfinite(lo) or not math.isfinite(hi) or not 2 <= count <= 20000:
            raise ValueError("invalid preview range")
    except (KeyError, ValueError, OverflowError):
        lo, hi, count = points[0][0], points[-1][0], len(points)
    missing = []
    if points[0][0] > lo + 1e-6:
        missing.append([lo, points[0][0]])
    if points[-1][0] < hi - 1e-6:
        missing.append([points[-1][0], hi])
    expected_step = (hi - lo) / (count - 1) if count > 1 else 0
    if expected_step > 0:
        missing.extend([a[0], b[0]] for a, b in zip(points, points[1:])
                       if b[0] - a[0] > expected_step * 1.5 + 1e-6)
    if len(points) != count or missing:
        annotations = [{'range': r, 'label': '측정값 없음'} for r in missing]
        findings.append({
            'code': 'spectrum_incomplete', 'title': '헤더에 적힌 범위만큼 데이터가 없어요',
            'detail': f'헤더에는 {lo:g}~{hi:g} nm, {count:,}점이 적혀 있지만 실제로는 {points[0][0]:g}~{points[-1][0]:g} nm, {len(points):,}점이 있어요.',
            'action': '원본 CSV에서 4,001개 측정점이 모두 내보내졌는지 확인해 주세요. 비어 있는 범위를 채우기 전에는 Eg 계산을 보류해요.',
            'ranges': missing, 'blocking': True,
        })
    invalid = [[x, y] for x, y in points if not 0 < y <= 100]
    if invalid:
        ranges = [[x - 2, x + 2] for x, _ in invalid[:10]]
        annotations.extend({'range': r, 'label': '범위 밖 측정값'} for r in ranges)
        findings.append({
            'code': 'transmittance_out_of_range', 'title': '투과율 계산 범위를 벗어난 값이 있어요',
            'detail': '이 분석은 0% 초과, 100% 이하의 투과율을 사용해요. ' + ', '.join(f'{x:g} nm에서 {y:g}%' for x, y in invalid[:5]) + '가 확인됐어요.',
            'action': '측정값의 %, 소수 표기와 기준선 설정을 확인해 주세요. 값을 임의로 자르지 않고 계산을 멈췄어요.',
            'ranges': ranges, 'blocking': True,
        })
    # Retain every issue point even when reducing the preview resolution.
    boundaries = {edge for interval in missing for edge in interval}
    reduced = points[::max(1, len(points) // 600)] + points[-1:] + invalid + [p for p in points if p[0] in boundaries]
    preview = {
        'title': '계산 전 · 원본 투과율 점검', 'x_label': '파장 λ (nm)', 'y_label': '투과율 (%)',
        'points': sorted({(x, y) for x, y in reduced}), 'x_domain': [lo, hi],
        'point_count': len(points),
        'gaps': missing,
        'annotations': annotations, 'markers': invalid, 'limits': [100],
        'note': '파란 선은 실제로 읽은 값이에요. 표시된 구간을 확인한 뒤 원본 파일을 다시 넣어주세요.',
    }
    return preview, findings
