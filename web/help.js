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
    geometry: ["W와 L · 채널 크기", "W는 전류가 흐르는 채널의 폭, L은 소스와 드레인 사이 채널의 길이예요. 둘 다 μm 단위이며 이동도 계산에 사용해요."],
    residual: ["잔차", "측정값에서 피팅 직선의 예측값을 뺀 차이예요. 구간 한쪽에서 계속 벌어지거나 곡선처럼 휘는지도 확인해요."]
  };
  const box = document.createElement("div");
  box.id = "term-tooltip";
  box.className = "term-tooltip";
  box.role = "tooltip";
  box.hidden = true;
  document.body.appendChild(box);
  let trigger = null, timer = 0, pinned = false;
  const geometry = '<svg viewBox="0 0 280 103" aria-hidden="true"><rect x="48" y="27" width="184" height="44" rx="3" fill="#eaf1ff" stroke="#88a5dd"/><rect x="26" y="23" width="28" height="52" rx="4" fill="#485c75"/><rect x="226" y="23" width="28" height="52" rx="4" fill="#485c75"/><path d="M59 88H221M59 83V93M221 83V93M14 28V70M9 28H19M9 70H19" stroke="#2459d3" fill="none"/><text x="140" y="100" text-anchor="middle">L · 길이</text><text x="6" y="18">W · 폭</text><text x="40" y="15" text-anchor="middle">소스</text><text x="240" y="15" text-anchor="middle">드레인</text><text x="140" y="54" text-anchor="middle">채널 · 전류가 흐르는 길</text></svg>';
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
    const title = document.createElement("strong"), paragraph = document.createElement("p");
    title.textContent = data[0]; paragraph.textContent = data[1];
    box.append(title, paragraph);
    if (node.dataset.help === "geometry") {
      const example = document.createElement("p");
      example.className = "term-example";
      example.textContent = node.dataset.w ? "W" + node.dataset.w + "/L" + node.dataset.l + " = 폭 " + node.dataset.w + " μm · 길이 " + node.dataset.l + " μm" : "예: W20/L4 = 폭 20 μm · 길이 4 μm";
      box.appendChild(example);
      const illustration = document.createElement("div");
      illustration.innerHTML = geometry;
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
