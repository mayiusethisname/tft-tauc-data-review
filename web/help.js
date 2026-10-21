(function () {
  "use strict";
  const definitions = {
    "a-Si": ["a-Si · 비정질 실리콘", "원자가 긴 규칙으로 배열되지 않은 실리콘이에요. 대면적 디스플레이 TFT에 널리 쓰이며, 다른 재료와 이동도·문턱전압을 비교할 때 기준이 되기도 해요."],
    "a-IGZO": ["a-IGZO · 비정질 산화물", "인듐·갈륨·아연·산소로 이루어진 반도체예요. 실리콘과 다른 산화물 재료로, TFT의 이동도와 낮은 누설전류를 함께 살펴볼 수 있어요."],
    "LTPS": ["LTPS · 저온 다결정 실리콘", "작은 결정립이 모인 실리콘을 저온 공정으로 만든 TFT 재료예요. a-Si보다 높은 이동도가 필요한 디스플레이 구동에 쓰여요."],
    "Poly-Si": ["Poly-Si · 다결정 실리콘", "여러 실리콘 결정립이 모인 재료예요. 여기서는 측정한 투과율을 변환해 광학 밴드갭 후보를 살펴봐요."],
    mu: ["이동도 μ", "전하가 전기장에 따라 얼마나 잘 이동하는지 나타내요. 여기서는 선택 구간의 기울기와 W/L을 이용해 계산해요. 단위는 cm²/(V·s)예요."],
    vth: ["문턱전압 Vth", "소자가 켜지기 시작하는 기준을 나타내는 값이에요. 이 화면에서는 선택한 피팅 직선을 전압축까지 연장한 절편으로 구해요."],
    r2: ["직선 적합도 R²", "선택한 측정점들이 직선에 얼마나 잘 맞는지 보여줘요. 1에 가까울수록 잘 맞아요. 주변 구간의 결과 변화도 함께 읽어보세요."],
    eg: ["광학 밴드갭 Eg", "빛 흡수와 관련된 에너지 간격이에요. Tauc 변환에서 선택한 직선을 에너지축까지 연장한 절편으로 구해요. 단위는 eV예요."],
    sensitivity: ["구간 선택 민감도", "구간 위치를 바꿔 다시 계산한 결과의 차이예요. TFT 표는 같은 폭으로 ±0.5 V 옮긴 μ·Vth를 비교해요. 다른 후보의 차이와 구분해서 읽을 수 있어요."],
    geometry: ["W와 L · 채널 크기", "W는 채널 폭, L은 Source–Drain 사이의 채널 길이입니다. 포화 이동도는 선택 구간의 기울기와 L/W, 절연막 정전용량 Ci로 계산합니다."],
    residual: ["잔차", "측정값에서 피팅 직선의 예측값을 뺀 차이예요. 구간 한쪽에서 계속 벌어지거나 곡선처럼 휘는지도 확인해요."]
  };
  const box = document.createElement("div");
  box.id = "term-tooltip";
  box.className = "term-tooltip";
  box.role = "tooltip";
  box.hidden = true;
  document.body.appendChild(box);
  let trigger = null, timer = 0, pinned = false;
  function geometryDiagram(rawW, rawL) {
    const w = Number(rawW) > 0 ? Number(rawW) : 20;
    const l = Number(rawL) > 0 ? Number(rawL) : 4;
    const scale = Math.min(100 / w, 100 / l);
    const h = w * scale, span = l * scale;
    const left = 205 - span / 2, right = 205 + span / 2, top = 95 - h / 2;
    return `<svg viewBox="0 0 360 310" role="img" aria-label="W ${w} μm, L ${l} μm. Source와 Drain 사이 채널, 점선 Gate 영역과 절연막 단면 개념도">
      <text x="16" y="18" font-size="12">평면 · W/L 비례</text>
      <rect x="${left - 8}" y="${top - 10}" width="${span + 16}" height="${h + 20}" fill="#fff6e9" stroke="#a46b23" stroke-width="1.5" stroke-dasharray="4 3"/>
      <rect x="${left - 34}" y="${top}" width="${span + 68}" height="${h}" fill="#eaf1ff" stroke="#6f94dc"/>
      <rect x="${left - 48}" y="${top - 4}" width="48" height="${h + 8}" rx="3" fill="#334b65"/>
      <rect x="${right}" y="${top - 4}" width="48" height="${h + 8}" rx="3" fill="#334b65"/>
      <text x="${left - 24}" y="99" text-anchor="middle" font-size="12" fill="white">Source</text>
      <text x="${right + 24}" y="99" text-anchor="middle" font-size="12" fill="white">Drain</text>
      <path d="M65 ${top}V${top + h} M59 ${top}H71 M59 ${top + h}H71" fill="none" stroke="#2459d3" stroke-width="1.5"/>
      <text x="52" y="89" text-anchor="end" font-size="13" fill="#243b56">W</text>
      <text x="52" y="107" text-anchor="end" font-size="12">${w} μm</text>
      <path d="M205 ${top + h + 10}V170H294" fill="none" stroke="#a46b23" stroke-width="1.5"/>
      <text x="300" y="174" font-size="12" fill="#85551e">Gate</text>
      <path d="M${left} 192H${right} M${left} 186V198 M${right} 186V198" fill="none" stroke="#2459d3" stroke-width="1.5"/>
      <text x="205" y="216" text-anchor="middle" font-size="13" fill="#243b56">L · ${l} μm</text>
      <text x="16" y="246" font-size="12">단면 개념</text>
      <rect x="116" y="239" width="158" height="10" fill="#dce7ff" stroke="#6f94dc"/>
      <rect x="116" y="254" width="158" height="12" fill="#eef1f5" stroke="#97a5b5"/>
      <rect x="116" y="271" width="158" height="10" fill="#fff0d7" stroke="#a46b23"/>
      <text x="282" y="248" font-size="12">Active</text>
      <text x="282" y="265" font-size="12">절연막</text>
      <text x="282" y="281" font-size="12">Gate</text>
      <text x="116" y="303" font-size="12">Ci = εi / ti · 절연막 정전용량 / 면적</text>
    </svg>`;
  }
  function position() {
    if (!trigger?.isConnected) return close();
    const a = trigger.getBoundingClientRect(), b = box.getBoundingClientRect();
    if (a.bottom < 0 || a.top > innerHeight) return close();
    box.style.left = Math.max(12, Math.min(a.left + a.width / 2 - b.width / 2, innerWidth - b.width - 12)) + "px";
    box.style.top = (a.bottom + b.height + 12 < innerHeight ? a.bottom + 8 : Math.max(12, a.top - b.height - 8)) + "px";
  }
  function close() {
    clearTimeout(timer);
    trigger?.removeAttribute("aria-describedby");
    trigger = null; pinned = false; box.hidden = true;
  }
  function show(node) {
    const data = definitions[node.dataset.help];
    if (!data) return;
    if (trigger !== node) trigger?.removeAttribute("aria-describedby");
    trigger = node;
    box.replaceChildren();
    box.classList.toggle("geometry-tooltip", node.dataset.help === "geometry");
    const title = document.createElement("strong"), paragraph = document.createElement("p");
    title.textContent = data[0]; paragraph.textContent = data[1];
    box.append(title, paragraph);
    if (node.dataset.help === "geometry") {
      const example = document.createElement("p");
      example.className = "term-example";
      example.textContent = node.dataset.w ? "W" + node.dataset.w + "/L" + node.dataset.l + " = 폭 " + node.dataset.w + " μm · 길이 " + node.dataset.l + " μm" : "예: W20/L4 = 폭 20 μm · 길이 4 μm";
      box.appendChild(example);
      const illustration = document.createElement("div");
      illustration.innerHTML = geometryDiagram(node.dataset.w, node.dataset.l);
      box.appendChild(illustration);
    }
    box.hidden = false; node.setAttribute("aria-describedby", box.id); position();
  }
  document.addEventListener("pointerover", (event) => {
    const node = event.target.closest("[data-help]");
    if (!node || node === trigger) return;
    clearTimeout(timer); pinned = false;
    timer = setTimeout(() => show(node), 220);
  });
  document.addEventListener("pointerout", (event) => {
    const node = event.target.closest("[data-help]");
    if (!node || pinned || node.contains(event.relatedTarget) || box.contains(event.relatedTarget)) return;
    clearTimeout(timer); timer = setTimeout(close, 130);
  });
  box.addEventListener("pointerenter", () => clearTimeout(timer));
  box.addEventListener("pointerleave", () => { if (!pinned) timer = setTimeout(close, 130); });
  document.addEventListener("focusin", (event) => {
    const node = event.target.closest("[data-help]");
    if (node) { clearTimeout(timer); show(node); }
  });
  document.addEventListener("focusout", (event) => {
    if (event.target === trigger && !pinned) close();
  });
  document.addEventListener("click", (event) => {
    const node = event.target.closest("[data-help]");
    if (node) {
      if (trigger === node && pinned) close();
      else { clearTimeout(timer); pinned = true; show(node); }
    } else if (!box.contains(event.target)) close();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  window.addEventListener("scroll", () => { if (pinned) position(); else close(); }, { passive: true, capture: true });
  window.addEventListener("resize", close);
})();
