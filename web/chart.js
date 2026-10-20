(function (root) {
  "use strict";
  let chartId = 0;
  const colors = { data: "#2459d3", fit: "#c35a14", spike: "#bb3442", ink: "#243b56", grid: "#e0e7f0" };
  const safe = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function tick(value) {
    if (value === 0) return "0";
    if (Math.abs(value) < .01 || Math.abs(value) >= 10000) return value.toExponential(1);
    return Number(value.toPrecision(4)).toLocaleString("en-US", { maximumFractionDigits: 3 });
  }
  function mount(container, config) {
    const series = config.series.map((s) => ({ ...s, points: s.points.filter((p) => p.every(Number.isFinite)) }));
    const all = series.flatMap((s) => s.points);
    if (all.length < 2) { container.innerHTML = ""; return { destroy() {} }; }
    const id = "plot-clip-" + (++chartId);
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    const xmin = Math.min(...xs, ...(config.xDomain || [])), xmax = Math.max(...xs, ...(config.xDomain || []));
    const ymin = Math.min(0, ...ys), ymax = Math.max(...ys);
    const xpad = (xmax - xmin || 1) * .025, ypad = (ymax - ymin || 1) * .1;
    const full = { x0: xmin - xpad, x1: xmax + xpad, y0: ymin >= 0 ? 0 : ymin - ypad * .04, y1: ymax + ypad };
    let view = { ...full }, drag = null, width = 900;
    const touch = matchMedia("(hover: none) and (pointer: coarse)").matches;
    container.innerHTML = `
      <div class="chart-shell">
        <div class="chart-heading"><div><h3>${safe(config.title)}</h3><p>${touch ? "버튼으로 확대·축소 · 손가락으로 밀어 이동 · 두 번 누르면 전체 보기" : "휠로 확대·축소 · 드래그로 이동 · 두 번 누르면 전체 보기"}</p></div>
          <div class="chart-controls"><button type="button" data-chart="in" aria-label="그래프 확대">＋ 확대</button><button type="button" data-chart="out" aria-label="그래프 축소">－ 축소</button><button type="button" data-chart="reset">전체 보기</button><span class="zoom-value">100%</span></div></div>
        <div class="chart-legend">${series.filter((s) => s.label).map((s) => `<span><i class="legend-swatch" style="background:${s.color || colors.data}"></i>${safe(s.label)}</span>`).join("")}${config.window ? '<span><i class="legend-swatch window"></i>선택한 구간</span>' : ""}${config.annotations?.length ? '<span><i class="legend-swatch issue"></i>확인할 위치</span>' : ""}</div>
        <div class="chart-stage"><svg role="img" tabindex="0" aria-label="${safe(config.title + ". " + config.xLabel + ", " + config.yLabel + ". 확대·축소 버튼 또는 더하기·빼기 키로 조작할 수 있습니다.")}"></svg></div>
        <div class="chart-readout" aria-live="off">${touch ? "그래프를 누르면 가까운 측정값을 볼 수 있어요." : "그래프 위에 커서를 올리면 가까운 측정값을 볼 수 있어요."}</div>
      </div>`;
    const stage = container.querySelector(".chart-stage");
    const svg = stage.querySelector("svg");
    const readout = container.querySelector(".chart-readout");
    function dimensions() {
      width = Math.max(280, stage.clientWidth);
      return { width, height: width < 600 ? 320 : 390, left: width < 600 ? 69 : 86, right: 24, top: 42, bottom: 57 };
    }
    function draw() {
      const d = dimensions(), pw = d.width - d.left - d.right, ph = d.height - d.top - d.bottom;
      const sx = (x) => d.left + (x - view.x0) / (view.x1 - view.x0) * pw;
      const sy = (y) => d.top + ph - (y - view.y0) / (view.y1 - view.y0) * ph;
      const count = width < 500 ? 3 : 5;
      let grid = "", labels = "";
      for (let i = 0; i < count; i++) {
        const ratio = i / (count - 1), x = d.left + pw * ratio, y = d.top + ph * ratio;
        grid += `<path d="M${x} ${d.top}V${d.top + ph} M${d.left} ${y}H${d.left + pw}" fill="none" stroke="${colors.grid}" stroke-width="1"/>`;
        labels += `<text x="${x}" y="${d.top + ph + 24}" text-anchor="middle">${tick(view.x0 + (view.x1 - view.x0) * ratio)}</text><text x="${d.left - 10}" y="${y + 4}" text-anchor="end">${tick(view.y1 - (view.y1 - view.y0) * ratio)}</text>`;
      }
      let marks = "";
      for (const [index, a] of (config.annotations || []).entries()) {
        const lo = Math.min(...a.range), hi = Math.max(...a.range);
        const x0 = sx(lo), x1 = sx(hi);
        marks += `<g data-annotation="${index}"><rect x="${x0}" y="${d.top}" width="${Math.max(2, x1-x0)}" height="${ph}" fill="url(#${id}-issue)" stroke="#bb3442" stroke-dasharray="4 4"/><text x="${Math.max(d.left + 6, Math.min(x0 + 7, d.left + pw - 130))}" y="${d.top + 18 + index * 17}" fill="#9a2433" font-size="12" font-weight="700">${safe(a.label || '확인할 구간')}</text></g>`;
      }
      for (const limit of (config.limits || [])) {
        marks += `<path d="M${d.left} ${sy(limit)}H${d.left+pw}" fill="none" stroke="#9a2433" stroke-dasharray="6 5" stroke-width="1.6"/><text x="${d.left+8}" y="${sy(limit)-8}" fill="#9a2433" font-size="12">${safe(limit)}% 기준선</text>`;
      }
      if (config.window) {
        const x0 = sx(Math.min(...config.window)), x1 = sx(Math.max(...config.window));
        marks += `<rect x="${x0}" y="${d.top}" width="${Math.max(0, x1 - x0)}" height="${ph}" fill="#dce7ff" fill-opacity=".65" stroke="#6e91df" stroke-dasharray="5 4"/>`;
      }
      for (const s of series) {
        const color = s.color || colors.data;
        const path = s.points.map((p, i) => {
          const previous = s.points[i-1];
          const gap = previous && s === series[0] && (config.gaps || []).some(([lo, hi]) => Math.min(previous[0], p[0]) <= lo + 1e-8 && Math.max(previous[0], p[0]) >= hi - 1e-8);
          return (i && !gap ? "L" : "M") + sx(p[0]).toFixed(2) + "," + sy(p[1]).toFixed(2);
        }).join(" ");
        if (s.line !== false) marks += `<path d="${path}" fill="none" stroke="${color}" stroke-width="${s.width || 2.7}" stroke-linecap="round" stroke-linejoin="round" ${s.dashed ? 'stroke-dasharray="7 5"' : ""}/>`;
        if (s.dots) {
          const step = Math.max(1, Math.floor(s.points.length / 100));
          marks += s.points.filter((_, i) => i % step === 0).map((p) => `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="2.3" fill="white" stroke="${color}" stroke-width="1.4"/>`).join("");
        }
      }
      for (const p of (config.markers || [])) marks += `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="6" fill="white" stroke="${colors.spike}" stroke-width="3"/>`;
      if (Number.isFinite(config.intercept)) {
        const x = sx(config.intercept);
        marks += `<path d="M${x} ${sy(0)}V${d.top}" fill="none" stroke="${colors.fit}" stroke-width="1.3" stroke-dasharray="3 5"/>`;
      }
      svg.setAttribute("viewBox", `0 0 ${d.width} ${d.height}`);
      svg.setAttribute("height", String(d.height));
      svg.dataset.xSpan = String(view.x1 - view.x0);
      svg.dataset.xMin = String(view.x0);
      svg.innerHTML = `<defs><clipPath id="${id}"><rect x="${d.left}" y="${d.top}" width="${pw}" height="${ph}"/></clipPath><pattern id="${id}-issue" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#fff0f1" fill-opacity=".65"/><path d="M-2 2L2 -2M0 8L8 0M6 10L10 6" stroke="#e4a5ad" stroke-width="1"/></pattern></defs>
        ${grid}<g clip-path="url(#${id})">${marks}</g>
        <path d="M${d.left} ${d.top}V${d.top + ph}H${d.left + pw}" fill="none" stroke="#526780" stroke-width="1.3"/>
        <g fill="${colors.ink}" font-family="ui-monospace,Consolas,monospace" font-size="${width < 500 ? 11 : 12}">${labels}</g>
        <g fill="${colors.ink}" font-family="Pretendard,Malgun Gothic,sans-serif" font-size="13" font-weight="600"><text x="${d.left}" y="23">${safe(config.yLabel)}</text><text x="${d.left + pw / 2}" y="${d.height - 9}" text-anchor="middle">${safe(config.xLabel)}</text></g>`;
      container.querySelector(".zoom-value").textContent = Math.round((full.x1 - full.x0) / (view.x1 - view.x0) * 100) + "%";
    }
    function zoom(factor, rx = .5, ry = .5) {
      const spanX = view.x1 - view.x0, spanY = view.y1 - view.y0;
      const nextX = Math.max((full.x1 - full.x0) / 150, Math.min((full.x1 - full.x0) * 1.2, spanX * factor));
      const nextY = spanY * (nextX / spanX);
      const x = view.x0 + spanX * rx, y = view.y0 + spanY * ry;
      view = { x0: x - nextX * rx, x1: x + nextX * (1 - rx), y0: y - nextY * ry, y1: y + nextY * (1 - ry) };
      draw();
    }
    function ratios(event) {
      const box = svg.getBoundingClientRect(), d = dimensions();
      return { x: Math.max(0, Math.min(1, (event.clientX - box.left - d.left) / (d.width - d.left - d.right))), y: Math.max(0, Math.min(1, 1 - (event.clientY - box.top - d.top) / (d.height - d.top - d.bottom))) };
    }
    function control(event) {
      const button = event.target.closest("[data-chart]");
      if (!button) return;
      if (button.dataset.chart === "reset") { view = { ...full }; draw(); }
      else zoom(button.dataset.chart === "in" ? .7 : 1 / .7);
    }
    function wheel(event) { event.preventDefault(); const r = ratios(event); zoom(event.deltaY < 0 ? .82 : 1 / .82, r.x, r.y); }
    function down(event) { if (event.button !== 0) return; move(event); drag = { x: event.clientX, y: event.clientY, view: { ...view } }; svg.setPointerCapture(event.pointerId); svg.classList.add("is-dragging"); }
    function move(event) {
      const d = dimensions();
      if (drag) {
        const dx = (event.clientX - drag.x) / (d.width - d.left - d.right) * (drag.view.x1 - drag.view.x0);
        const dy = (event.clientY - drag.y) / (d.height - d.top - d.bottom) * (drag.view.y1 - drag.view.y0);
        view = { x0: drag.view.x0 - dx, x1: drag.view.x1 - dx, y0: drag.view.y0 + dy, y1: drag.view.y1 + dy };
        draw(); return;
      }
      const x = view.x0 + (view.x1 - view.x0) * ratios(event).x;
      const nearest = series[0].points.reduce((a, b) => Math.abs(b[0] - x) < Math.abs(a[0] - x) ? b : a);
      readout.textContent = config.xLabel + ": " + tick(nearest[0]) + "  ·  " + config.yLabel + ": " + tick(nearest[1]);
    }
    function up() { drag = null; svg.classList.remove("is-dragging"); }
    function reset() { view = { ...full }; draw(); }
    function focus(ranges) {
      const edges = ranges.flat().filter(Number.isFinite);
      if (!edges.length) return;
      const lo = Math.min(...edges), hi = Math.max(...edges);
      const pad = Math.max(Math.min((hi-lo)*.3, (full.x1-full.x0)*.08), (full.x1-full.x0)*.035);
      const values = series[0].points.filter((p) => p[0] >= lo-pad && p[0] <= hi+pad).map((p) => p[1]);
      const y0 = values.length ? Math.min(...values) : full.y0, y1 = values.length ? Math.max(...values) : full.y1;
      const ypad = Math.max((y1-y0)*.2, (full.y1-full.y0)*.02);
      view = { x0:Math.max(full.x0,lo-pad), x1:Math.min(full.x1,hi+pad), y0:y0-ypad, y1:y1+ypad };
      draw();
    }
    function key(event) { if (["+", "=", "-", "0"].includes(event.key)) { event.preventDefault(); if (event.key === "0") reset(); else zoom(event.key === "-" ? 1 / .7 : .7); } }
    container.addEventListener("click", control);
    svg.addEventListener("wheel", wheel, { passive: false });
    svg.addEventListener("pointerdown", down);
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerup", up);
    svg.addEventListener("pointercancel", up);
    svg.addEventListener("dblclick", reset);
    svg.addEventListener("keydown", key);
    const observer = new ResizeObserver(draw);
    observer.observe(stage); draw();
    return { focus, getView() { return {...view}; }, setView(next) {
      if ([next.x0,next.x1,next.y0,next.y1].every(Number.isFinite) && next.x1 > next.x0 && next.y1 > next.y0) { view = {...next}; draw(); }
    }, destroy() { observer.disconnect(); container.removeEventListener("click", control); } };
  }
  root.MeasurementChart = { mount };
})(window);
