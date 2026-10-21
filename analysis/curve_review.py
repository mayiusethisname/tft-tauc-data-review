"""Portable curve checks carried over from the original review server.

The reversal and isolated-spike thresholds match saturation_review_alert.
This module returns evidence and a next action for the working UI.
"""

from __future__ import annotations

import math
from statistics import median


def review_saturation(points: list[dict], candidates: list[dict], drive_sign: int) -> list[dict]:
    findings = []
    if candidates and not any(c.get("reliability_status") == "statistically_reliable_candidate" for c in candidates):
        findings.append({"code": "unstable_fit", "title": "안정성 기준에 들어온 후보가 없어요", "detail": "직선 적합도·잔차·인접 구간 변화를 함께 확인했습니다.", "action": "후보별 추천 근거를 비교하고 측정 조건과 원곡선을 다시 확인해 보세요."})
    ordered = sorted(((drive_sign * float(p["x"]), float(p["root_current_A"])) for p in points if math.isfinite(float(p["x"])) and math.isfinite(float(p["root_current_A"]))), key=lambda p: p[0])
    values = [y for _, y in ordered]
    if len(values) < 6:
        return findings
    spread = max(values) - min(values)
    if not spread:
        return findings
    changes = [b - a for a, b in zip(values, values[1:])]
    for i in range(5, len(changes)-5):
        jump = changes[i]
        neighbors = changes[i-5:i] + changes[i+1:i+6]
        typical = median(abs(v) for v in neighbors)
        if abs(jump) >= .04 * spread and abs(jump) > 8 * max(typical, spread * 1e-6):
            if any(jump*v < 0 and abs(v) > abs(jump)*.5 for v in (changes[i-1], changes[i+1])):
                continue
            voltage = ordered[i+1][0] * drive_sign
            findings.append({"code":"current_step", "title":"전류 곡선에 단차가 있습니다",
                "detail":f"{voltage:.2f} V 부근의 변화가 주변 10개 간격 중앙값의 8배를 넘습니다.",
                "action":"해당 전압의 측정 레인지·연결 상태와 원자료를 확인해 주세요.",
                "voltages":[voltage]})
            break
    peak_index = max(range(len(values)), key=values.__getitem__)
    tail_level = median(values[-5:])
    if len(values)*.5 <= peak_index < len(values)-5 and values[peak_index]-tail_level >= .08*spread:
        bounds = sorted((ordered[peak_index][0]*drive_sign, ordered[-1][0]*drive_sign))
        findings.append({"code":"high_drive_rolloff", "title":"고전압 구간에서 전류가 감소합니다",
            "detail":f"최대점과 마지막 5점 중앙값의 √|IDS| 차이가 전체 범위의 {(values[peak_index]-tail_level)/spread*100:.1f}%입니다.",
            "action":"표시 구간의 연결·접촉 상태와 스윕 기록을 확인하고, 피팅 범위를 비교해 주세요.",
            "ranges":[bounds]})
    if abs(values[-1] - median(values[-5:-1])) >= .2*spread:
        findings.append({"code":"endpoint_discontinuity", "title":"마지막 측정점의 전류 확인 필요",
            "detail":"종료점의 √|IDS|가 직전 4점 중앙값과 전체 범위의 20% 이상 차이 납니다.",
            "action":"마지막 점의 원자료와 스윕 종료 기록을 확인해 주세요.",
            "voltages":[ordered[-1][0]*drive_sign]})
    meaningful = [v for v in changes if abs(v) >= spread * .02]
    if len(meaningful) >= 5 and sum(v < 0 for v in meaningful) / len(meaningful) >= .15:
        findings.append({"code": "curve_reversal", "title": "전류가 구동 방향에서 반복해 되돌아가요", "detail": "전체 변화 폭의 2% 이상인 변화 중 감소 방향이 15% 이상입니다.", "action": "스윕 방향과 극성, 측정 중 흔들림을 확인해 보세요."})
    spikes = [i for i in range(1, len(values) - 1) if abs(values[i] - values[i-1]) / spread >= .25 and abs(values[i+1] - values[i]) / spread >= .25 and (values[i] - values[i-1]) * (values[i+1] - values[i]) < 0]
    if spikes:
        voltages = [ordered[i][0] * drive_sign for i in spikes]
        findings.append({"code": "isolated_spike", "title": "주변 측정점과 크게 다른 전류가 있어요", "detail": "앞뒤 변화가 전체 √|IDS| 범위의 25% 이상이며 방향이 반전되는 점을 찾았습니다.", "action": "표시된 전압의 원자료와 측정 기록을 확인해 보세요. 해당 점을 자동으로 삭제하지 않았습니다.", "voltages": voltages})
    return findings
