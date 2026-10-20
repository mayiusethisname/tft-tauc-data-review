(function () {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const MAX_FILE_BYTES = 3 * 1024 * 1024;
  const state = { domain: "tft", material: "a-IGZO", reference: null, compareOpen: false, samples: [], result: null, selected: 0, reason: 0, plotMode: "tauc", activeSample: "", fromUpload: false, requestId: 0, controller: null, chart: null, note: "", toastTimer: 0 };
  const fileInput = $("#file-input"), form = $("#upload-form");
  const escape = (value) => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  const num = (value, digits = 3) => value != null && Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
  const candidates = () => state.result?.data?.candidates || [];
  const chosen = () => candidates()[state.selected] || null;
  const candidateKey = (c) => c ? [c.plot_id || "tft", c.start_raw_V ?? c.energy_min_ev, c.end_raw_V ?? c.energy_max_ev].join(":") : "";
  const modelName = (key) => ({ indirect_allowed: "간접 허용 전이", legacy_amorphous: "기존 비정질 변환 (지수 ½)", direct_allowed: "직접 허용 전이", indirect_forbidden: "간접 금지 전이", direct_forbidden: "직접 금지 전이", beer_lambert_apparent: "투과율 기반 흡수계수", reflection_corrected_simplified: "반사 보정 흡수계수" }[key] || "측정 조건 확인");
  const opticalProfiles = { "a-Si": [50, 4.045], "a-IGZO": [40, 1.92], "Poly-Si": [50, 3.715] };
  function filenameHint(name) {
    const match = /^(asi|a-si|igzo|a-igzo|ltps)[_-]?(\d{2})[_-]?(\d{2})(?=[_.]|$)/i.exec(name || "");
    return match ? {material: /si$/i.test(match[1]) ? "a-Si" : /igzo/i.test(match[1]) ? "a-IGZO" : "LTPS", width: Number(match[2]), length: Number(match[3])} : null;
  }
  function updateUploadConditions() {
    const file = fileInput.files?.[0], tft = state.domain === "tft";
    const material = $(tft ? "#tft-material" : "#tauc-material").value;
    const width = Number($("#tft-width").value), length = Number($("#tft-length").value);
    const hint = tft && file ? filenameHint(file.name) : null;
    const mismatch = hint && (hint.material !== material || hint.width !== width || hint.length !== length);
    const preset = opticalProfiles[material];
    $("#condition-values").textContent = tft ? material + " · W" + width + "/L" + length + " μm · Ci 17.5 nF/cm² 적용" : material + " · 두께 " + preset[0] + " nm · 박막 굴절률 " + preset[1] + " · air 기준선 · glass 기판";
    $("#filename-conditions").textContent = hint ? "파일명에서 읽은 조건: " + hint.material + " · W" + hint.width + "/L" + hint.length + " μm" + (mismatch ? ". 현재 입력과 달라요." : ". 측정 기록과 맞는지 확인해 주세요.") : tft ? "측정 기록을 보고 재료와 W/L을 확인해 주세요. DAT는 MOBILITY 포화 측정을 읽어요." : "이 실험 프로파일과 같은 조건의 JASCO 투과율 CSV를 넣어주세요.";
    $("#filename-conditions").classList.toggle("condition-mismatch", Boolean(mismatch));
    $("#condition-confirm-label").textContent = mismatch ? "파일명과 다른 위 입력 조건을 확인했고, 이 조건으로 계산할게요" : "파일의 측정 조건이 위 내용과 맞는지 확인했어요";
    $("#analyze-file").disabled = !file || !$("#condition-confirm").checked || Boolean(state.controller);
    $("#upload-state").textContent = file && !$("#condition-confirm").checked ? "측정 조건을 확인하고 체크하면 분석할 수 있어요." : "선택 취소를 누르면 파일과 분석 화면을 비울 수 있어요.";
  }
  function storage() { try { return localStorage; } catch (_) { return null; } }
  function dismissToast() { clearTimeout(state.toastTimer); $("#toast").classList.remove("is-visible"); $("#toast").textContent = ""; }
  function toast(message) { const target = $("#toast"); target.textContent = message; target.classList.add("is-visible"); clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => target.classList.remove("is-visible"), 2800); }
  function step(number) {
    document.querySelectorAll(".workflow [data-step]").forEach((node) => {
      const own = Number(node.dataset.step);
      node.classList.toggle("is-current", own === number);
      node.classList.toggle("is-done", own < number);
      if (own === number) node.setAttribute("aria-current", "step"); else node.removeAttribute("aria-current");
    });
  }
  function stopRequest() { state.controller?.abort(); state.controller = null; state.requestId += 1; return state.requestId; }
  function resetFileInput() {
    fileInput.value = ""; $("#file-label").textContent = "선택한 파일이 없어요";
    $("#clear-file").disabled = true; $("#clear-file").textContent = "선택 취소"; $("#analyze-file").disabled = true;
    $("#upload-state").textContent = "파일을 바꾸려면 선택 취소 후 새 파일을 넣어주세요.";
    $("#condition-confirm").checked = false; updateUploadConditions();
  }
  function empty(message = "위에서 실측 사례를 하나 골라보세요", detail = "이 파일 분석하기를 누르면 파일 점검 결과와 그래프가 여기에 나와요. 이어서 후보를 눌러 추천 근거를 비교할 수 있어요.") {
    state.chart?.destroy(); state.chart = null; state.result = null;
    $("#result-panel").setAttribute("aria-busy", "false");
    $("#result-panel").innerHTML = `<div class="empty-state"><span class="empty-number">2</span><h3>${escape(message)}</h3><p>${escape(detail)}</p></div>`;
    $("#review").classList.add("is-hidden"); step(1);
  }
  function clearFile() {
    stopRequest(); resetFileInput(); state.fromUpload = false; state.activeSample = ""; state.note = "";
    renderSamples(); empty("파일 선택을 취소했어요", "새 파일을 선택하거나 실측 예제로 다시 시작해 보세요."); toast("선택한 파일과 분석 화면을 비웠어요.");
  }
  function setDomain(domain) {
    stopRequest(); state.domain = domain; state.material = domain === "tft" ? "a-IGZO" : "a-Si"; state.activeSample = ""; state.fromUpload = false; state.selected = 0; state.note = ""; state.plotMode = "tauc";
    resetFileInput();
    document.querySelectorAll(".domain-tab").forEach((node) => { const active = node.dataset.domain === domain; node.classList.toggle("is-active", active); node.setAttribute("aria-selected", String(active)); });
    $("#domain-panel").setAttribute("aria-labelledby", "tab-" + domain);
    $("#tft-fields").classList.toggle("is-hidden", domain !== "tft"); $("#tauc-fields").classList.toggle("is-hidden", domain !== "tauc");
    $("#tft-width").required = domain === "tft"; $("#tft-length").required = domain === "tft";
    $("#upload-format").textContent = domain === "tft" ? "DAT 또는 CSV · 파일당 3 MB 이하" : "JASCO 투과율 CSV · 파일당 3 MB 이하";
    fileInput.accept = domain === "tft" ? ".dat,.csv,text/csv" : ".csv,text/csv";
    renderSamples(); empty();
  }
  function help(key, label, extra = "") {
    return '<button class="help-trigger" type="button" data-help="' + escape(key) + '" aria-label="' + escape(label) + ' 설명"' + extra + '><span aria-hidden="true">i</span></button>';
  }
  function renderSamples() {
    const domain = state.samples.filter((sample) => sample.domain === state.domain);
    const materials = state.domain === "tft" ? ["a-IGZO", "a-Si", "LTPS"] : ["a-Si", "a-IGZO", "Poly-Si"];
    $("#material-list").innerHTML = materials.map((material) => '<div class="material-option ' + (state.material === material ? 'is-active' : '') + '"><button type="button" data-action="material" data-material="' + material + '" aria-pressed="' + (state.material === material) + '">' + material + '</button>' + help(material, material) + '</div>').join("");
    const visible = domain.filter((sample) => sample.material === state.material);
    const measured = visible.filter((sample) => sample.kind === "measured");
    const faults = visible.filter((sample) => sample.kind === "modified");
    $("#sample-count").textContent = state.material + " · 실측 " + measured.length + "개";
    $("#material-description").textContent = state.domain === "tft" ? "파일명과 채널 크기를 보고 선택해 주세요. W/L 옆의 i에서 크기를 읽는 법을 볼 수 있어요." : "물질별 원본 스펙트럼 1개와 오류를 넣은 비교 예제를 준비했어요.";
    const card = (sample, index) => {
      const modified = sample.kind === "modified";
      const dimensions = sample.width_um ? '<div class="sample-geometry"><span>W' + sample.width_um + '/L' + sample.length_um + ' μm</span>' + help("geometry", "채널 폭과 길이", ' data-w="' + sample.width_um + '" data-l="' + sample.length_um + '"') + '</div>' : "";
      return '<article class="sample-card ' + (state.activeSample === sample.id ? 'is-selected' : '') + '" data-sample="' + sample.id + '"><div class="sample-top"><span class="kind-badge ' + (modified ? 'modified' : '') + '">' + (modified ? '오류 주입' : '실측 자료') + '</span>' + dimensions + '</div><h3>' + escape(modified ? sample.title : sample.filename) + '</h3><p>' + escape(sample.description) + '</p><div class="sample-actions"><button class="button ' + (!modified && index === 0 ? 'button-primary' : '') + '" type="button" data-action="open-sample" data-id="' + sample.id + '">이 파일 분석하기 <span aria-hidden="true">→</span></button><a class="text-link" href="/api?action=sample&amp;id=' + encodeURIComponent(sample.id) + '" download>CSV 내려받기</a></div></article>';
    };
    $("#sample-list").innerHTML = measured.map(card).join("");
    $("#fault-list").innerHTML = faults.map(card).join("");
    $("#fault-count").textContent = faults.length + "개 사례";
  }
  function loading(name) {
    state.chart?.destroy(); state.chart = null; state.result = null; $("#review").classList.add("is-hidden");
    $("#result-panel").setAttribute("aria-busy", "true");
    $("#result-panel").innerHTML = `<div class="empty-state"><h3><span class="loading-dots" aria-hidden="true"></span>측정값과 파일 정보를 살펴보고 있어요</h3><p>${escape(name)}</p></div>`;
    step(2);
  }
  async function post(payload, signal) {
    const response = await fetch("/api?action=analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal });
    const result = await response.json();
    if (!response.ok && !result.status) throw new Error("analysis_failed");
    return result;
  }
  function acceptResult(result) {
    state.result = result; state.reference = null; state.compareOpen = false; state.selected = 0; state.reason = 0; state.plotMode = "tauc";
    const saved = window.ReviewState.get(result, storage());
    const savedIndex = candidates().findIndex((c) => candidateKey(c) === saved?.candidate?.key);
    if (savedIndex >= 0) state.selected = savedIndex;
    state.note = saved?.note || "";
    renderResult(); step(2);
    $("#analysis").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }
  async function openSample(id) {
    const sample = state.samples.find((s) => s.id === id); if (!sample) return;
    const requestId = stopRequest(); state.controller = new AbortController();
    state.activeSample = id; state.fromUpload = false; resetFileInput(); $("#upload-box").open = false;
    renderSamples(); loading(sample.title);
    try { const result = await post({ sample_id: id }, state.controller.signal); if (requestId === state.requestId) acceptResult(result); }
    catch (error) { if (error.name !== "AbortError" && requestId === state.requestId) empty("분석 결과를 불러오지 못했어요", "서버가 실행 중인지 확인하고 다시 시도해 주세요."); }
    finally { if (requestId === state.requestId) state.controller = null; }
  }
  function base64(buffer) {
    const bytes = new Uint8Array(buffer); let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binary);
  }
  async function upload(file) {
    if (!file) return;
    if (!$("#condition-confirm").checked) { toast("계산에 쓸 측정 조건을 먼저 확인해 주세요."); return; }
    if (file.size > MAX_FILE_BYTES) { toast("파일은 3 MB 이하로 선택해 주세요."); return; }
    const requestId = stopRequest(); state.controller = new AbortController(); state.fromUpload = true; state.activeSample = "";
    renderSamples(); loading(file.name); $("#clear-file").disabled = false; $("#clear-file").textContent = "분석 취소"; $("#analyze-file").disabled = true; $("#upload-state").textContent = "분석 중이에요. 취소하면 선택한 파일과 결과를 비워요.";
    const config = state.domain === "tft" ? { material: $("#tft-material").value, width_um: Number($("#tft-width").value), length_um: Number($("#tft-length").value), polarity: $("#tft-polarity").value } : { material: $("#tauc-material").value };
    config.conditions_confirmed = $("#condition-confirm").checked;
    try {
      const buffer = await file.arrayBuffer(); if (requestId !== state.requestId) return;
      const result = await post({ domain: state.domain, filename: file.name, content_base64: base64(buffer), config }, state.controller.signal);
      if (requestId === state.requestId) acceptResult(result);
    } catch (error) { if (error.name !== "AbortError" && requestId === state.requestId) empty("파일을 분석하지 못했어요", "파일 형식과 측정 조건을 확인한 뒤 다시 분석해 주세요."); }
    finally { if (requestId === state.requestId) { state.controller = null; $("#clear-file").textContent = "선택 취소"; updateUploadConditions(); } }
  }
  function checks(result) {
    const findings = result.findings || [];
    const pointCount = result.data?.points?.length || result.data?.point_count || result.intake?.point_count || 0;
    const readable = result.status === "ready" || !!result.data?.points?.length;
    const material = result.intake?.material && result.intake.material !== "unknown" ? result.intake.material : "재료 확인 필요";
    const configured = result.conditions?.confirmed === true;
    const condition = result.domain === "tft" ? material + (result.intake?.width_um ? " · W/L " + result.intake.width_um + "/" + result.intake.length_um + " μm" : "") : material + " · 투과율 스펙트럼";
    const items = [
      [readable ? "pass" : "warning", "파일·열 확인", readable ? pointCount.toLocaleString() + "개 측정점을 읽었어요" : pointCount ? pointCount.toLocaleString() + "개 수치 · 구조 확인 필요" : "열 이름·측정 범위를 확인해 주세요"],
      [configured ? "pass" : "wait", "측정 조건 확인", condition],
      [findings.length ? "warning" : readable ? "pass" : "wait", "곡선·구간 점검", findings.length ? findings.length + "개 확인 의견이 있어요" : candidates().length ? candidates().length + "개 후보를 비교할 수 있어요" : "입력 정보를 확인한 뒤 진행해요"],
    ];
    const details = '<div class="check-strip">' + items.map(([status,title,detail]) => '<div class="check-item ' + status + '"><span>' + (status === "pass" ? "✓ 확인" : status === "warning" ? "! 확인 필요" : "· 대기") + '</span><strong>' + title + '</strong><p>' + escape(detail) + '</p></div>').join("") + '</div>';
    return result.status === "ready" && !findings.length ? '<details class="check-overview"><summary>✓ ' + pointCount.toLocaleString() + '점 · 측정 조건 확인 · 후보 ' + candidates().length + '개 <span>점검 내역</span></summary>' + details + '</details>' : details;
  }
  function findingList(result) {
    const findings = result.findings || [];
    if (!findings.length && result.status === "ready") return "";
    const list = findings.length ? findings : [{ title: result.message, detail: "분석에 필요한 정보를 더 확인해 주세요.", action: "파일 형식과 열 이름, 재료 설정을 확인한 뒤 다시 넣어주세요." }];
    const items = list.map((finding, index) => {
      const focusable = finding.ranges?.length || finding.voltages?.length;
      return '<article class="finding" data-finding="' + escape(finding.code || "input") + '"><div class="finding-title"><h4>' + escape(finding.title) + '</h4>' + (focusable ? '<button class="finding-focus" type="button" data-action="focus-finding" data-index="' + index + '">이 위치 확대 ↗</button>' : '') + '</div><p>' + escape(finding.detail) + '</p>' + (finding.voltages ? '<p class="finding-coordinate">확인할 전압 · ' + finding.voltages.map((value) => num(value, 2) + " V").join(", ") + '</p>' : '') + '<p class="next-action"><span aria-hidden="true">↳</span><span>' + escape(finding.action) + '</span></p></article>';
    }).join("");
    const sample = result.sample;
    const overlay = sample?.control_id && (result.domain === "tauc" || !result.preview?.table);
    return '<section class="findings"><div class="finding-intro"><h3>표시한 부분을 확인해 주세요</h3><p>위치 확인 → 원자료 대조 → 수정한 파일로 다시 분석</p></div>' + items + '<div class="finding-actions">' + (sample?.control_id ? '<button class="button" type="button" data-action="' + (overlay ? 'overlay-control' : 'open-sample') + '" data-id="' + sample.control_id + '">' + (overlay ? '대조 원본 겹쳐 보기' : '열 이름이 있는 원본 열기') + '</button>' : '') + '<button class="text-button" type="button" data-action="goto-upload">수정한 파일 넣기 →</button></div></section>';
  }
  function metrics(c) {
    if (!c) return "";
    const values = state.domain === "tft" ? [
      ["선택 구간 이동도 μsat", num(c.mu_sat_cm2_Vs, 2), "cm²/(V·s)", "mu"],
      ["선택 구간 문턱전압 Vth", num(c.vth_sat_raw_V, 3), "V", "vth"],
      ["직선 적합도 R²", num(c.r2 ?? c.fit?.r2, 4), "", "r2"],
    ] : [
      ["선택 구간 광학 밴드갭 Eg", num(c.eg_ev, 3), "eV", "eg"],
      ["직선 적합도 R²", num(c.r2, 4), "", "r2"],
      ["인접 구간의 Eg 최대 변화", num(c.eg_shift_max_ev, 3), "eV", "sensitivity"],
    ];
    return '<div class="metrics">' + values.map(([label, value, unit, term]) => '<div class="metric"><span>' + label + help(term, label) + '</span><strong>' + value + ' <small>' + unit + '</small></strong></div>').join("") + '</div>';
  }
  function intervalSummary() {
    if (state.domain !== "tft" || !chosen()) return "";
    const values = candidates(), c = chosen();
    const mu = values.map((item) => Number(item.mu_sat_cm2_Vs));
    const vth = values.map((item) => Number(item.vth_sat_raw_V));
    return '<section class="interval-summary"><div><span class="summary-kicker">' + (state.selected === 0 ? "기본 표시 구간" : "현재 선택 구간") + '</span><h3>' + num(c.start_raw_V, 2) + ' ~ ' + num(c.end_raw_V, 2) + ' V</h3>' + metrics(c) + '</div><div class="range-summary"><strong>주변 구간을 함께 계산하면' + help("sensitivity", "주변 구간의 결과 변화") + '</strong><dl><div><dt>이동도 μ</dt><dd>' + num(Math.min(...mu), 2) + ' ~ ' + num(Math.max(...mu), 2) + '<small>cm²/(V·s)</small></dd></div><div><dt>문턱전압 Vth</dt><dd>' + num(Math.min(...vth), 3) + ' ~ ' + num(Math.max(...vth), 3) + '<small>V</small></dd></div></dl><p>표시된 ' + values.length + '개 후보 구간의 계산 범위예요.</p></div></section>';
  }
  function delta(c, index) {
    const first = candidates()[0];
    const signed = (value, digits) => (value > 0 ? "+" : "") + num(value, digits);
    if (index === 0) return "처음 표시한 기준 후보";
    return state.domain === "tft" ? "기본 구간 대비 μ " + signed((c.mu_sat_cm2_Vs / first.mu_sat_cm2_Vs - 1) * 100, 1) + "% · Vth " + signed(c.vth_sat_raw_V - first.vth_sat_raw_V, 3) + " V" : "첫 후보 대비 Eg " + signed(c.eg_ev - first.eg_ev, 3) + " eV";
  }
  function conditionCaption(c) {
    const condition = state.result?.conditions, values = condition?.values;
    if (!values) return "";
    const text = state.domain === "tft" ? values.material + " · W" + values.width_um + "/L" + values.length_um + " μm · Ci 17.5 nF/cm² 적용" : values.material + " · " + (c ? modelName(c.transition_model) + " · " + modelName(c.alpha_model) + " · " : "") + num(values.thickness_nm, 0) + " nm · 굴절률 " + values.film_refractive_index + " · air / glass";
    return '<div class="current-conditions"><span>' + (condition.confirmed ? "이번 계산 조건" : "확인할 계산 조건") + '</span><p>' + escape(text) + '</p></div>';
  }
  function candidateCards() {
    return `<div class="candidate-grid ${state.domain === "tauc" ? "tauc" : ""}">${candidates().map((c, index) => {
      const selected = state.selected === index;
      const heading = state.domain === "tft" ? num(c.start_raw_V, 2) + " ~ " + num(c.end_raw_V, 2) + " V" : num(c.eg_ev, 3) + " eV";
      const description = state.domain === "tft" ? "측정점 " + (c.points || c.fit?.points) + "개 · 구간 폭 " + num(c.window_span_V, 1) + " V" : modelName(c.transition_model) + " · " + modelName(c.alpha_model);
      const detail = state.domain === "tft" ? "μ " + num(c.mu_sat_cm2_Vs, 2) + " · Vth " + num(c.vth_sat_raw_V, 3) + " V" : num(c.energy_min_ev, 2) + " ~ " + num(c.energy_max_ev, 2) + " eV · " + c.points + "점";
      const stable = state.domain === "tft" ? c.reliability_status === "statistically_reliable_candidate" : c.status === "stable";
      return `<button type="button" class="candidate ${selected ? "is-selected" : ""}" data-action="candidate" data-index="${index}" aria-pressed="${selected}"><span class="rank"><span>후보 ${index + 1}${index === 0 ? " · 먼저 확인" : ""}</span><em>${selected ? "✓ 선택됨" : "선택하기"}</em></span><strong>${heading}</strong><small>${escape(description)}</small><span class="candidate-values"><span>${detail}</span><span>R² ${num(c.r2 ?? c.fit?.r2, 4)}</span></span><span class="candidate-delta">${escape(delta(c, index))}</span><span class="candidate-chip">${stable ? "잔차·구간 변화 기준 충족" : "구간 변화도 함께 확인"}</span></button>`;
    }).join("")}</div>`;
  }
  function reasonData(c) {
    if (state.domain === "tft") {
      const r2 = Number(c.r2 ?? c.fit?.r2), error = Number(c.normalized_rmse), slope = Number(c.slope_stability);
      return [
        ["직선 적합도", "이 구간이 직선에 얼마나 가까운가요?", "R²는 선택한 측정점을 직선이 얼마나 잘 따라가는지 보여줘요. 현재 후보의 값은 원본 검토 기준인 0.995 " + (r2 >= .995 ? "이상에 들어와요." : "보다 낮아요. 원곡선 모양을 함께 확인해 주세요."), "R² " + num(r2, 6) + " · 기준 ≥ 0.995"],
        ["잔차와 기울기", "직선 주변의 흔들림도 함께 봤어요.", "정규화 잔차는 구간 내 값의 범위에 비해 오차가 얼마나 큰지 나타내요. 구간 앞뒤의 기울기 변화도 함께 비교합니다. 두 값이 작을수록 같은 구간에서 직선으로 해석하기 쉬워요.", "정규화 잔차 " + num(error * 100, 2) + "% (기준 ≤ 2%) · 기울기 변화 " + num(slope * 100, 2) + "% (기준 ≤ 20%)"],
        ["구간 이동", "구간을 조금 옮겨도 결과가 비슷한가요?", "후보 주변 구간을 다시 피팅해서 이동도와 문턱전압의 최대 변화를 계산했어요. 변화가 크면 현재 구간을 골랐다는 이유만으로 결과가 크게 달라질 수 있어요.", "이동도 최대 변화 " + num(c.mu_shift_max_pct, 2) + "% (기준 ≤ 15%) · Vth 최대 변화 " + num(c.vth_shift_max_V, 3) + " V (기준 ≤ 0.5 V)"],
        ["측정점과 범위", "실제로 측정한 범위 안에서 골랐어요.", "이 후보는 " + c.points + "개 측정점을 포함해요. 최소 20개 점이 있는 구간들에서 적합도·잔차·구간 민감도를 함께 비교한 순서입니다. 다른 후보를 누르면 같은 기준으로 차이를 볼 수 있어요.", "원본 전압 범위 " + num(Math.min(...state.result.data.points.map((p) => p.x)), 1) + " ~ " + num(Math.max(...state.result.data.points.map((p) => p.x)), 1) + " V · 후보 구간 폭 " + num(c.window_span_V, 1) + " V"],
      ];
    }
    return [
      ["직선 적합도", "Tauc 변환 뒤 직선에 가까운 부분을 찾았어요.", "선택한 전이 모델로 변환한 측정값에 직선을 맞췄어요. 그래프의 주황색 직선을 x축까지 연장하면 이 후보의 Eg를 볼 수 있어요.", "R² " + num(c.r2, 6) + " · Eg " + num(c.eg_ev, 3) + " eV"],
      ["잔차", "피팅 직선과 측정값의 차이를 확인했어요.", "선택한 구간에서 측정값과 직선의 차이를 구간 내 값의 범위로 정규화한 값이에요. 숫자와 함께 파란 곡선이 직선에서 벗어나는 부분을 살펴보세요.", "정규화 잔차 " + num(Number(c.normalized_rmse) * 100, 2) + "% · 측정점 " + c.points + "개"],
      ["구간 민감도", "구간·평활화에 따라 Eg가 얼마나 바뀌나요?", "주변 구간으로 옮겨 다시 계산한 Eg의 최대 차이와 평활화 설정에 따른 차이를 확인했어요. 다른 후보와 비교할 때도 같은 값을 볼 수 있어요.", "구간 이동 최대 변화 " + num(c.eg_shift_max_ev, 4) + " eV · 평활화 차이 " + num(c.eg_smoothing_delta_ev, 4) + " eV"],
      ["계산 조건", "선택한 모델의 가정을 확인해 주세요.", modelName(c.transition_model) + "와 " + modelName(c.alpha_model) + "를 사용한 후보예요. 반사 보정 모델은 입사면과 박막의 반사를 단순화한 조건이므로 모델별 Eg 차이를 비교해 보세요.", "박막 두께 " + num(state.result.data.input_metadata?.thickness_nm, 0) + " nm · 입력 재료 " + state.result.intake.material],
    ];
  }
  function updateReason() {
    const c = chosen(); if (!c) return;
    const data = reasonData(c), active = data[state.reason] || data[0];
    $("#reason-detail").innerHTML = `<strong>${escape(active[1])}</strong><p>${escape(active[2])}</p><p class="reason-reading">${escape(active[3])}</p>`;
    document.querySelectorAll("[data-action=reason]").forEach((node) => { const activeTab = Number(node.dataset.index) === state.reason; node.classList.toggle("is-active", activeTab); node.setAttribute("aria-pressed", String(activeTab)); });
  }
  function reasons() {
    const c = chosen(); if (!c) return "";
    return `<section class="reason-section" aria-label="후보별 추천 근거"><h4>후보 ${state.selected + 1} · 추천 근거</h4><div class="reason-tabs" role="group" aria-label="추천 근거 선택">${reasonData(c).map((r, i) => `<button type="button" data-action="reason" data-index="${i}" aria-pressed="${state.reason === i}" class="${state.reason === i ? "is-active" : ""}">${r[0]}</button>`).join("")}</div><div class="reason-detail" id="reason-detail" role="region" aria-live="polite"></div></section>`;
  }
  function chartConfig() {
    const result = state.result, c = chosen(); if (!result) return null;
    if (result.preview) {
      const preview = result.preview;
      const series = [{label:"읽어낸 원본 숫자", color:"#2459d3", points:preview.points, dots:true}];
      if (state.reference?.data?.spectrum) series.push({label:"오류를 넣기 전 실측 원본", color:"#526b65", dashed:true, width:2, points:state.reference.data.spectrum.map((p) => [p.wavelength_nm,p.transmittance_percent])});
      return {title:preview.title,xLabel:preview.x_label,yLabel:preview.y_label,series,xDomain:preview.x_domain,annotations:preview.annotations,markers:preview.markers,limits:preview.limits,gaps:preview.gaps};
    }
    if (!result.data) return null;
    if (result.domain === "tauc" && state.plotMode === "spectrum") return {
      title:"원본 투과율 스펙트럼",xLabel:"파장 λ (nm)",yLabel:"투과율 (%)",
      series:[{label:"실측 투과율",color:"#2459d3",points:(result.data.spectrum || []).map((p) => [Number(p.wavelength_nm),Number(p.transmittance_percent)]).sort((a,b) => a[0]-b[0])}]
    };
    const tft = result.domain === "tft";
    const points = tft ? (result.data.points || []).map((p) => [Number(p.x),Number(p.root_current_A)]) : (result.data.plots?.[c?.plot_id]?.points || []);
    if (!points.length) return null;
    const unlocated = (result.intake?.row_issues || []).some((issue) => issue.voltage == null);
    const series = [{label:result.sample?.kind === "modified" ? "오류를 넣은 측정값" : "실측 측정값",color:"#2459d3",points,dots:true,line:!unlocated}];
    if (state.reference?.data?.points) series.push({label:"오류를 넣기 전 실측 원본",color:"#526b65",dashed:true,width:2,points:state.reference.data.points.map((p) => [p.x,p.root_current_A])});
    const start = Number(tft ? c?.start_raw_V : c?.energy_min_ev), end = Number(tft ? c?.end_raw_V : c?.energy_max_ev);
    const slope = Number(tft ? c?.fit?.slope : c?.slope), intercept = Number(tft ? c?.fit?.intercept : c?.intercept), xIntercept = Number(tft ? c?.vth_sat_raw_V : c?.eg_ev);
    if (c && Number.isFinite(slope) && Number.isFinite(intercept)) {
      series.push({label:"선택 구간 피팅 직선",color:"#c35a14",width:3,points:[[start,slope*start+intercept],[end,slope*end+intercept]]});
      const nearest = Math.abs(start-xIntercept) < Math.abs(end-xIntercept) ? start : end;
      series.push({color:"#c35a14",dashed:true,width:2,points:[[xIntercept,0],[nearest,slope*nearest+intercept]]});
    }
    const findings = result.findings || [];
    const markers = findings.flatMap((finding) => finding.voltages || []).map((value) => points.find((point) => point[0] === value)).filter(Boolean);
    const annotations = findings.flatMap((finding) => (finding.ranges || (finding.voltages || []).map((x) => [x-.15,x+.15])).map((range) => ({range,label:finding.code === "measurement_gap" ? "측정 간격 확인" : finding.code === "invalid_numeric_rows" ? "읽지 못한 측정값" : "전류 튐 확인"})));
    return {title:tft ? (c ? "포화 특성 · 구간과 피팅 직선" : "포화 특성 · 원본 곡선 점검") : "Tauc 변환 · 직선 구간과 Eg",xLabel:tft ? "VGS = VDS (V)" : "광자 에너지 hν (eV)",yLabel:tft ? "√|IDS| (√A)" : (c?.transition_model?.startsWith("indirect") || c?.transition_model === "legacy_amorphous") ? "(αhν)½ (eV/cm)½" : "(αhν)² (eV/cm)²",series,window:c ? [start,end] : null,intercept:c ? xIntercept : undefined,markers,annotations,gaps:findings.filter((finding) => ["measurement_gap","invalid_numeric_rows"].includes(finding.code)).flatMap((finding) => finding.ranges || [])};
  }
  function mountChart(view) {
    state.chart?.destroy(); state.chart = null;
    const config = chartConfig(); if (config && $("#chart-host")) state.chart = window.MeasurementChart.mount($("#chart-host"), config);
    if (view) state.chart?.setView?.(view);
  }
  function renderResult(preserveView = false) {
    const result = state.result; if (!result) return;
    const view = preserveView ? state.chart?.getView?.() : null;
    const c = chosen(), issues = (result.findings || []).length, ready = result.status === "ready";
    $("#result-panel").setAttribute("aria-busy", "false");
    const preview = result.preview;
    const table = preview?.table ? '<div class="column-preview"><h3>파일에 적힌 열 이름</h3><div class="table-scroll"><table><thead><tr>' + preview.table.headers.map((header) => '<th class="' + (header === "UNKNOWN" ? "unknown-column" : "") + '">' + escape(header) + '</th>').join("") + '</tr></thead><tbody>' + preview.table.rows.map((row) => '<tr>' + row.map((cell) => '<td title="' + escape(cell) + '">' + escape(Number.isFinite(Number(cell)) ? Number(Number(cell).toPrecision(6)).toString() : cell) + '</td>').join("") + '</tr>').join("") + '</tbody></table></div></div>' : "";
    $("#result-panel").innerHTML = '<div class="result-heading"><div><p class="step-caption">STEP 2 · ANALYSIS</p><h2>' + escape(result.sample?.title || result.filename || "파일 분석") + '</h2><p>' + escape(result.sample?.source || "내가 선택한 파일 · " + result.filename) + '</p></div><span class="status-badge ' + (!ready || issues ? "warning" : "") + '">' + (!ready ? "계산 보류 · 확인 필요" : issues ? "확인 의견 " + issues + "개" : "입력 확인 완료") + '</span></div>' +
      (!ready || issues ? '<div class="result-guide"><strong>여기서는 이렇게 살펴보세요</strong>' + escape(result.sample?.lesson || "확인 의견과 그래프를 보고 원본을 점검한 뒤 파일을 다시 넣어주세요.") + '</div>' : '') +
      checks(result) + findingList(result) + table + (preview ? '<p class="preview-note">' + escape(preview.note) + '</p>' : "") + intervalSummary() + (result.domain === "tauc" ? metrics(c) : "") + conditionCaption(c) +
      (result.domain === "tauc" && c ? '<div class="plot-tabs" role="group" aria-label="그래프 종류"><button type="button" data-action="plot-mode" data-mode="tauc" class="' + (state.plotMode === "tauc" ? "is-active" : "") + '">Tauc 변환과 피팅</button><button type="button" data-action="plot-mode" data-mode="spectrum" class="' + (state.plotMode === "spectrum" ? "is-active" : "") + '">원본 투과율</button></div>' : "") +
      '<div id="chart-host"></div>' +
      (c ? '<details id="candidate-comparison" class="candidate-comparison" ' + (state.compareOpen || state.selected > 0 ? "open" : "") + '><summary><span><strong>' + (result.domain === "tft" ? "다른 구간과 비교하기" : "모델과 구간별 후보 비교") + '</strong><small>' + (result.domain === "tft" ? "구간 폭과 안정성을 함께 살핀 순서예요. 아래에서 기본 구간과의 차이를 비교해 보세요." : "전이 모델과 흡수계수 계산 조건을 함께 확인해 주세요.") + '</small></span><span>' + candidates().length + '개 후보</span></summary>' + candidateCards() + '<div class="comparison-outcome"><p role="status">후보 ' + (state.selected + 1) + '을 보고 있어요. ' + escape(delta(c, state.selected)) + '</p><button type="button" class="text-button" data-action="view-selected-chart">선택한 구간 그래프 보기 ↑</button></div></details>' + reasons() : "") +
      '<details class="source-detail"><summary>이 분석에 사용한 자료와 조건</summary><p>' + escape(result.sample?.modification || "선택한 파일의 측정값과 입력한 재료·조건으로 분석했습니다.") + '</p><p>파일: ' + escape(result.filename) + ' · 분석 버전: ' + escape(result.analysis_version) + '</p>' + (result.domain === "tauc" && ready ? '<p>박막 두께 ' + num(result.data.input_metadata?.thickness_nm, 0) + ' nm · 기준선 air · 기판 glass. 계산 조건은 원본 실험 프로파일을 따릅니다.</p>' : "") + '</details>';
    mountChart(view); if (c) updateReason(); renderReview();
  }
  async function overlayControl(button) {
    if (state.reference) { state.reference = null; button.textContent = "대조 원본 겹쳐 보기"; mountChart(); return; }
    const key = state.result?.decision_key, id = state.result?.sample?.control_id;
    if (!id) return;
    button.disabled = true; button.textContent = "원본을 불러오는 중";
    try {
      const reference = await post({sample_id:id});
      if (state.result?.decision_key === key) { state.reference = reference; mountChart(); button.textContent = "대조 원본 숨기기"; }
    } catch (_) { if (state.result?.decision_key === key) { button.textContent = "원본 다시 불러오기"; toast("원본을 불러오지 못했어요."); } }
    finally { button.disabled = false; }
  }
  function snapshot(c) {
    return c ? { key: candidateKey(c), index: state.selected, range: state.domain === "tft" ? [c.start_raw_V, c.end_raw_V] : [c.energy_min_ev, c.energy_max_ev], mu: c.mu_sat_cm2_Vs, vth: c.vth_sat_raw_V, eg: c.eg_ev, alphaModel: c.alpha_model, transitionModel: c.transition_model } : null;
  }
  function renderReview() {
    const result = state.result; if (!result) return;
    const c = chosen(), saved = window.ReviewState.get(result, storage());
    const range = c ? state.domain === "tft" ? num(c.start_raw_V, 2) + " ~ " + num(c.end_raw_V, 2) + " V" : "Eg " + num(c.eg_ev, 3) + " eV" : "입력 정보 확인이 필요한 파일";
    const savedText = saved ? "기록됨 · " + (saved.decision === "use" ? "사용" : "보류") + (saved.candidate ? " · 후보 " + (saved.candidate.index + 1) : "") : "아직 기록하지 않았어요";
    $("#review").classList.remove("is-hidden");
    $("#review-panel").innerHTML = `<div class="review-heading"><p class="step-caption">STEP 3 · REVIEW</p><h2>확인한 내용을 기록해 주세요</h2><p>선택한 구간과 메모를 남겨두면 같은 파일을 다시 열었을 때 이어볼 수 있어요.</p></div><div class="review-choice">현재 선택 · ${c ? "후보 " + (state.selected + 1) + " · " : ""}${range}</div>
      <label class="review-label" for="decision-note">검토 메모 <span>선택 · 최대 240자</span></label><textarea id="decision-note" maxlength="240" placeholder="예: 인접 구간에서도 결과 변화가 작아 이 후보를 선택했어요.">${escape(state.note)}</textarea>
      <div class="review-actions"><button type="button" class="button button-primary" data-action="use" ${!c ? "disabled" : ""}>이 구간 사용</button><button type="button" class="button button-warning" data-action="hold">검토 보류</button><span class="decision-status" role="status">${savedText}</span></div>
      <p class="review-save-hint">사용 또는 보류 버튼을 누르면 현재 선택과 메모를 기록해요.</p>
      <button type="button" class="text-button restore-review" data-action="restore-review" hidden>마지막 기록으로 돌아가기</button>
      <div class="review-export"><span>기록에는 계산 조건·선택한 후보·메모를 담아요. 업로드한 파일 내용은 담지 않아요.</span><button class="text-button" type="button" data-action="export">검토 기록 내려받기</button></div>`;
    updateSavedStatus();
  }
  function updateSavedStatus() {
    if (!state.result || !$(".decision-status")) return;
    const saved = window.ReviewState.get(state.result, storage());
    const dirty = Boolean(saved && ((saved.candidate?.key || "") !== candidateKey(chosen()) || (saved.note || "") !== state.note));
    const last = saved ? (saved.decision === "use" ? "사용" : "보류") + (saved.candidate ? " · 후보 " + (saved.candidate.index + 1) : "") : "";
    $(".decision-status").textContent = dirty ? "변경한 내용이 아직 기록되지 않았어요. 마지막 기록: " + last : saved ? "기록됨 · " + last : "아직 기록하지 않았어요";
    $(".decision-status").classList.toggle("is-dirty", dirty);
    const restore = $("[data-action=restore-review]"); if (restore) restore.hidden = !dirty;
  }
  function save(decision) {
    if (!state.result) return;
    state.note = $("#decision-note")?.value ?? state.note;
    const ok = window.ReviewState.remember(state.result, decision, state.note, storage(), snapshot(chosen()));
    if (!ok) { toast("브라우저에 기록할 수 없어요. 검토 기록 내려받기를 이용해 주세요."); return; }
    state.note = window.ReviewState.get(state.result, storage())?.note ?? state.note;
    renderReview(); $(decision === "use" ? "[data-action=use]" : "[data-action=hold]")?.focus({preventScroll:true}); step(3); toast(decision === "use" ? "선택한 구간을 사용으로 기록했어요." : "검토 보류로 기록했어요.");
  }
  function exportReview() {
    if (!state.result) return;
    const record = window.ReviewState.get(state.result, storage());
    const output = { filename: state.result.filename, domain: state.domain, sha256: state.result.sha256, analysisVersion: state.result.analysis_version, conditions: state.result.conditions, candidate: snapshot(chosen()), record, unsavedNote: $("#decision-note")?.value || "" };
    const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = state.result.filename.replace(/\.[^.]+$/, "") + "-review.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast("검토 기록 파일을 만들었어요.");
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]"); if (!button) return;
    const action = button.dataset.action;
    if (action === "open-sample") openSample(button.dataset.id);
    if (action === "material") {
      if (state.material !== button.dataset.material) { stopRequest(); state.material = button.dataset.material; state.activeSample = ""; resetFileInput(); state.fromUpload = false; renderSamples(); empty(); $("#fault-examples").open = false; }
    }
    if (action === "focus-finding") {
      const finding = state.result.findings[Number(button.dataset.index)];
      const ranges = finding.ranges || (finding.voltages || []).map((x) => [x-.15,x+.15]);
      state.chart?.focus(ranges); $("#chart-host").scrollIntoView({behavior:"smooth",block:"center"});
    }
    if (action === "overlay-control") overlayControl(button);
    if (action === "goto-upload") { $("#upload-box").open = true; $("#upload-box").scrollIntoView({behavior:"smooth",block:"center"}); }

    if (action === "candidate") { state.note = $("#decision-note")?.value ?? state.note; state.selected = Number(button.dataset.index); renderResult(true); $("[data-action=candidate][data-index='" + state.selected + "']")?.focus({preventScroll:true}); }
    if (action === "view-selected-chart") { $("#chart-host").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",block:"center"}); $("#chart-host svg")?.focus({preventScroll:true}); }
    if (action === "restore-review") {
      const saved = window.ReviewState.get(state.result, storage());
      if (saved) { const index = candidates().findIndex((c) => candidateKey(c) === saved.candidate?.key); if (index >= 0) state.selected = index; state.note = saved.note || ""; renderResult(true); $("#decision-note")?.focus({preventScroll:true}); toast("마지막으로 기록한 선택과 메모를 불러왔어요."); }
    }
    if (action === "reason") { state.reason = Number(button.dataset.index); updateReason(); }
    if (action === "plot-mode") { state.plotMode = button.dataset.mode; document.querySelectorAll("[data-action=plot-mode]").forEach((node) => node.classList.toggle("is-active", node.dataset.mode === state.plotMode)); mountChart(); }
    if (action === "use") save("use");
    if (action === "hold") save("hold");
    if (action === "export") exportReview();
  });
  document.querySelectorAll(".domain-tab").forEach((node) => node.addEventListener("click", () => setDomain(node.dataset.domain)));
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0]; if (!file) return;
    dismissToast();
    stopRequest(); state.activeSample = ""; state.fromUpload = true; state.note = ""; renderSamples();
    empty("파일을 선택했어요. 측정 조건을 확인해 주세요.", "선택한 파일 분석을 누르면 이 자료로 계산을 시작해요.");
    $("#file-label").textContent = file.name + " · " + Math.max(1, Math.round(file.size / 1024)) + " KB";
    const hint = state.domain === "tft" ? filenameHint(file.name) : null;
    if (hint) { $("#tft-material").value = hint.material; $("#tft-width").value = hint.width; $("#tft-length").value = hint.length; }
    if (state.domain === "tauc") { const material = Object.keys(opticalProfiles).find((m) => m.toLowerCase() + ".csv" === file.name.toLowerCase()); if (material) $("#tauc-material").value = material; }
    $("#condition-confirm").checked = false;
    $("#clear-file").disabled = false; updateUploadConditions();
  });
  $("#clear-file").addEventListener("click", clearFile);
  form.addEventListener("submit", (event) => { event.preventDefault(); upload(fileInput.files?.[0]); });
  form.querySelectorAll("select, input[type=number]").forEach((node) => node.addEventListener("change", () => { $("#condition-confirm").checked = false; if (state.fromUpload && state.result) { stopRequest(); empty("측정 조건이 바뀌었어요", "새 조건을 확인한 뒤 다시 분석해 주세요."); } updateUploadConditions(); }));
  $("#condition-confirm").addEventListener("change", updateUploadConditions);
  document.addEventListener("input", (event) => { if (event.target.id === "decision-note") { state.note = event.target.value; updateSavedStatus(); } });
  $("#clear-decisions").addEventListener("click", () => { const ok = window.ReviewState.clear(storage()); if (ok) { state.note = ""; if (state.result) renderReview(); toast("이 브라우저의 검토 기록을 지웠어요."); } else toast("기록을 지우지 못했어요. 브라우저 저장 설정을 확인해 주세요."); });
  document.addEventListener("toggle", (event) => { if (event.target.id === "candidate-comparison") state.compareOpen = event.target.open; }, true);
  empty(); updateUploadConditions();
  fetch("/api?action=samples").then((response) => { if (!response.ok) throw new Error("sample_catalog"); return response.json(); }).then((samples) => { state.samples = samples; renderSamples(); }).catch(() => { $("#sample-count").textContent = "예제를 불러오지 못했어요"; $("#sample-list").innerHTML = '<p>로컬 서버가 실행 중인지 확인하고 새로고침해 주세요.</p>'; });
})();
