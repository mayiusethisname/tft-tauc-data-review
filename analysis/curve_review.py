"""Portable curve checks carried over from the original review server.

The reversal and isolated-spike thresholds match saturation_review_alert.
This module returns evidence and a next action for the working UI.
"""

from __future__ import annotations

import math


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
    meaningful = [v for v in changes if abs(v) >= spread * .02]
    if len(meaningful) >= 5 and sum(v < 0 for v in meaningful) / len(meaningful) >= .15:
        findings.append({"code": "curve_reversal", "title": "전류가 구동 방향에서 반복해 되돌아가요", "detail": "전체 변화 폭의 2% 이상인 변화 중 감소 방향이 15% 이상입니다.", "action": "스윕 방향과 극성, 측정 중 흔들림을 확인해 보세요."})
    spikes = [i for i in range(1, len(values) - 1) if abs(values[i] - values[i-1]) / spread >= .25 and abs(values[i+1] - values[i]) / spread >= .25 and (values[i] - values[i-1]) * (values[i+1] - values[i]) < 0]
    if spikes:
        voltages = [ordered[i][0] * drive_sign for i in spikes]
        findings.append({"code": "isolated_spike", "title": "주변 측정점과 크게 다른 전류가 있어요", "detail": "앞뒤 변화가 전체 √|IDS| 범위의 25% 이상이며 방향이 반전되는 점을 찾았습니다.", "action": "표시된 전압의 원자료와 측정 기록을 확인해 보세요. 해당 점을 자동으로 삭제하지 않았습니다.", "voltages": voltages})
    return findings
