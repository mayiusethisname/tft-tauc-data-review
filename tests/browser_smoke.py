"""Meaningful end-to-end checks in an isolated local browser (no extension access needed)."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def contrast(foreground, background):
    def channels(value):
        numbers = [float(v) / 255 for v in re.findall(r"[0-9.]+", value)[:3]]
        return [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in numbers]
    def luminance(value):
        r, g, b = channels(value)
        return .2126 * r + .7152 * g + .0722 * b
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def main():
    program_dirs = [Path(os.environ.get(key, "")) for key in ("PROGRAMFILES(X86)", "PROGRAMFILES")]
    executables = [os.environ.get("PORTFOLIO_BROWSER", ""), *[str(base / suffix) for base in program_dirs for suffix in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe")]]
    executable = next((value for value in executables if value and Path(value).is_file()), None)
    if not executable:
        raise SystemExit("Set PORTFOLIO_BROWSER to Chrome/Edge, or install a Playwright browser.")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = os.environ.get('PORTFOLIO_BASE_URL', f"http://127.0.0.1:{port}").rstrip('/')
    process = None if os.environ.get('PORTFOLIO_BASE_URL') else subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--port", str(port)], cwd=ROOT, stdout=subprocess.DEVNULL)
    artifacts = Path(tempfile.mkdtemp(prefix="tft-workspace-review-"))
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api?action=samples", timeout=1).read()
                break
            except OSError:
                if process is not None and process.poll() is not None:
                    raise RuntimeError("Preview server exited")
                time.sleep(.1)
        else:
            raise RuntimeError("Preview did not become ready")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True, args=["--disable-gpu"])
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True, reduced_motion="reduce")
            page = context.new_page()
            expect.set_options(timeout=15000)
            errors = []
            svg_exports = {}
            api_events = []
            page.on("request", lambda request: api_events.append(("start", time.monotonic(), request.post_data_json.get("sample_id", "upload"))) if request.method == "POST" else None)
            page.on("response", lambda response: api_events.append(("response", time.monotonic(), response.status)) if response.request.method == "POST" else None)
            page.on("requestfailed", lambda request: api_events.append(("failed", time.monotonic(), request.failure)))
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#sample-list .sample-card")).to_have_count(3)
            expect(page.locator("#chart-host svg")).to_be_visible()
            assert page.locator("#chart-host svg").bounding_box()["y"] < 700
            assert page.evaluate("scrollY") == 0
            expect(page.locator(".sensitivity-panel tbody tr")).to_have_count(3)
            page.screenshot(path=str(artifacts / "input-desktop.png"), full_page=True)
            for material, expected_name in [("a-Si","aSi"),("LTPS","LTPS"),("a-IGZO","aIGZO")]:
                page.locator('[data-action="material"][data-material="' + material + '"]').click()
                expect(page.locator("#sample-list .sample-card")).to_have_count(3)
                expect(page.locator("#sample-list .sample-card h3").first).to_contain_text(expected_name)
                for helper in page.locator('#sample-list [data-help="geometry"]').all():
                    helper.focus()
                    expect(page.locator('#term-tooltip svg')).to_be_visible()
                    w, l = float(helper.get_attribute('data-w')), float(helper.get_attribute('data-l'))
                    dimensions = page.locator('#term-tooltip svg').evaluate('''svg => {
                        const r = [...svg.querySelectorAll('rect')];
                        const n = (el, key) => Number(el.getAttribute(key));
                        const boxes = [...svg.querySelectorAll('text')].map(el => ({text:el.textContent, b:el.getBoundingClientRect().toJSON()}));
                        const overlaps = boxes.flatMap((a,i) => boxes.slice(i+1).filter(c => a.b.x<c.b.right && a.b.right>c.b.x && a.b.y<c.b.bottom && a.b.bottom>c.b.y).map(c => [a.text,c.text]));
                        return {ratio:n(r[1],'height')/(n(r[3],'x')-n(r[2],'x')-n(r[2],'width')), overlaps};
                    }''')
                    assert math.isclose(dimensions['ratio'], w/l), dimensions
                    assert not dimensions['overlaps'], dimensions
                    expect(page.locator('#term-tooltip')).to_contain_text('Gate')
                    expect(page.locator('#term-tooltip')).to_contain_text('절연막')
                    helper.press('Escape')
            geometry = page.locator("#sample-list .help-trigger").first
            geometry.hover()
            expect(page.locator("#term-tooltip")).to_be_visible()
            expect(page.locator("#term-tooltip")).to_contain_text("W20/L4")
            page.mouse.move(0,0)
            expect(page.locator("#term-tooltip")).to_be_hidden()
            geometry.focus()
            expect(page.locator("#term-tooltip")).to_be_visible()
            geometry.press("Escape")
            expect(page.locator("#term-tooltip")).to_be_hidden()


            page.locator('[data-id="tft-clear"]').click()
            expect(page.locator(".candidate")).to_have_count(3)
            expect(page.locator(".finding")).to_have_count(0)
            expect(page.locator("#reason-detail")).to_contain_text("R²")
            page.get_by_role("button", name="구간 이동", exact=True).click()
            expect(page.locator("#reason-detail")).to_contain_text("이동도 최대 변화")
            first_metrics = page.locator(".metrics").inner_text()
            page.locator("#candidate-comparison summary").click()
            page.get_by_role("button", name="그래프 확대", exact=True).click()
            preserved_span = float(page.locator("#chart-host svg").get_attribute("data-x-span"))
            page.locator(".candidate").nth(1).click()
            expect(page.locator(".candidate").nth(1)).to_have_attribute("aria-pressed", "true")
            assert page.locator(".candidate").nth(1).evaluate("(el) => el === document.activeElement")
            assert math.isclose(float(page.locator("#chart-host svg").get_attribute("data-x-span")), preserved_span)
            expect(page.locator(".candidate-delta").nth(1)).to_contain_text("-7.8%")
            page.get_by_role("button", name="전체 보기", exact=True).click()
            assert page.locator(".metrics").inner_text() != first_metrics
            expect(page.locator(".reason-section h4")).to_contain_text("후보 2")

            svg = page.locator("#chart-host svg")
            initial = float(svg.get_attribute("data-x-span"))
            ticks = svg.locator("text").all_text_contents()
            assert svg.locator('[data-axis="x"]').all_text_contents() == ['0', '5', '10', '15']
            assert any("e-" in value for value in ticks), ticks
            expect(svg).to_have_attribute("aria-label", re.compile("√A"))
            page.get_by_role("button", name="그래프 확대", exact=True).click()
            assert float(svg.get_attribute("data-x-span")) < initial
            before_pan = float(svg.get_attribute("data-x-min"))
            box = svg.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .55, box["y"] + box["height"] * .45)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .45, steps=5)
            page.mouse.up()
            assert float(svg.get_attribute("data-x-min")) != before_pan
            page.get_by_role("button", name="전체 보기", exact=True).click()
            assert math.isclose(float(svg.get_attribute("data-x-span")), initial)
            page.locator("#analysis").screenshot(path=str(artifacts / "analysis-desktop.png"))
            expect(page.locator(".sensitivity-panel")).to_contain_text("±0.5 V")
            svg_exports["normal"] = svg.evaluate("(el) => el.outerHTML")

            colors = page.locator(".sample-section-heading p").first.evaluate("(el) => {let parent=el;while(parent && getComputedStyle(parent).backgroundColor==='rgba(0, 0, 0, 0)') parent=parent.parentElement;return {fg:getComputedStyle(el).color,bg:parent?getComputedStyle(parent).backgroundColor:'rgb(255,255,255)'}}")
            assert contrast(colors["fg"], colors["bg"]) >= 4.5, colors

            page.locator("#decision-note").fill("인접 구간 변화와 잔차를 비교해 두 번째 후보를 선택")
            page.get_by_role("button", name="이 구간 사용", exact=True).click()
            expect(page.locator(".decision-status")).to_contain_text("후보 2")
            page.locator("#decision-note").fill("")
            expect(page.locator(".decision-status")).to_contain_text("아직 기록되지")
            page.get_by_role("button", name="마지막 기록으로 돌아가기", exact=True).click()
            expect(page.locator("#decision-note")).to_have_value(re.compile("두 번째 후보"))
            page.locator(".candidate").nth(2).click()
            expect(page.locator(".decision-status")).to_contain_text("아직 기록되지")
            page.get_by_role("button", name="마지막 기록으로 돌아가기", exact=True).click()
            expect(page.locator(".candidate").nth(1)).to_have_attribute("aria-pressed", "true")
            page.reload()
            expect(page.locator("#sample-list .sample-card")).to_have_count(3)
            page.locator('[data-id="tft-clear"]').click()
            expect(page.locator(".candidate").nth(1)).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#decision-note")).to_have_value(re.compile("두 번째 후보"))

            page.locator('#fault-examples summary').click()
            page.locator('[data-id="tft-spike"]').click()
            expect(page.locator('[data-finding="isolated_spike"]')).to_be_visible()
            expect(page.locator(".next-action")).to_contain_text("원자료")
            expect(page.locator('#chart-host circle[stroke="#bb3442"]')).to_have_count(1)
            svg_exports["spike"] = page.locator("#chart-host svg").evaluate("(el) => el.outerHTML")
            page.locator("#analysis").screenshot(path=str(artifacts / "spike-desktop.png"))
            before_focus = float(page.locator("#chart-host svg").get_attribute("data-x-span"))
            page.get_by_role("button",name="이 위치 확대 ↗").click()
            assert float(page.locator("#chart-host svg").get_attribute("data-x-span")) < before_focus
            page.get_by_role("button",name="대조 원본 겹쳐 보기",exact=True).click()
            expect(page.get_by_role("button",name="대조 원본 숨기기",exact=True)).to_be_visible()
            expect(page.locator(".chart-legend")).to_contain_text("오류를 넣기 전 실측 원본")
            page.locator('[data-id="tft-igzo-gap"]').click()
            expect(page.locator('[data-finding="measurement_gap"]')).to_be_visible()
            expect(page.locator("#chart-host [data-annotation]")).to_have_count(1)
            path = page.locator('#chart-host path[stroke="#2459d3"]').get_attribute("d")
            assert path.count("M") == 2, path
            expect(page.get_by_role("button",name="이 구간 사용",exact=True)).to_be_disabled()
            page.locator("#analysis").screenshot(path=str(artifacts / "gap-desktop.png"))

            page.locator('[data-id="tft-hold"]').click()
            expect(page.locator(".findings")).to_contain_text("전류")
            expect(page.locator(".column-preview")).to_contain_text("UNKNOWN")
            expect(page.locator("#chart-host svg")).to_have_attribute("aria-label", re.compile("단위 미확정"))
            page.locator("#analysis").screenshot(path=str(artifacts / "unknown-column-desktop.png"))

            expect(page.get_by_role("button", name="이 구간 사용", exact=True)).to_be_disabled()
            page.get_by_role("button", name="검토 보류", exact=True).click()
            expect(page.locator(".decision-status")).to_contain_text("보류")

            for sample_id, finding_code, image_key in [('tft-igzo-range_step','current_step','range-step'), ('tft-igzo-high_drive_rolloff','high_drive_rolloff','high-drive-rolloff')]:
                page.locator('[data-id="'+sample_id+'"]').click()
                expect(page.locator('[data-finding="'+finding_code+'"]')).to_be_visible()
                page.locator('[data-finding="'+finding_code+'"] [data-action="focus-finding"]').click()
                page.locator('[data-action="overlay-control"]').click()
                expect(page.locator('.chart-legend')).to_contain_text('오류를 넣기 전 실측 원본')
                svg_exports[image_key] = page.locator('#chart-host svg').evaluate('(el) => el.outerHTML')
                page.locator('#analysis').screenshot(path=str(artifacts / (image_key+'.png')))
            page.get_by_role("tab", name=re.compile("Tauc 광학")).click()
            expect(page.locator("#sample-list .sample-card")).to_have_count(1)
            page.locator('[data-id="tauc-clear"]').click()
            try:
                expect(page.locator(".candidate")).to_have_count(4)
            except AssertionError:
                print("TAUC_VISIBLE_STATE", page.locator("#result-panel").inner_text(), errors, api_events)
                page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
                raise
            svg = page.locator("#chart-host svg")
            expect(svg).to_have_attribute("aria-label", re.compile("Tauc 변환"))
            expect(page.locator('#chart-host path[stroke="#c35a14"]')).to_have_count(3)
            tauc_span = float(svg.get_attribute("data-x-span"))
            page.get_by_role("button", name="그래프 확대", exact=True).click()
            assert float(svg.get_attribute("data-x-span")) < tauc_span
            before_pan = float(svg.get_attribute("data-x-min"))
            box = svg.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .55, box["y"] + box["height"] * .45)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .45, steps=5)
            page.mouse.up()
            assert float(svg.get_attribute("data-x-min")) != before_pan
            before_wheel = float(svg.get_attribute("data-x-span"))
            page.mouse.wheel(0, -180)
            expect(svg).not_to_have_attribute("data-x-span", str(before_wheel))
            assert float(svg.get_attribute("data-x-span")) < before_wheel
            page.get_by_role("button", name="전체 보기", exact=True).click()
            assert math.isclose(float(svg.get_attribute("data-x-span")), tauc_span)
            page.get_by_role("button", name="원본 투과율", exact=True).click()
            expect(svg).to_have_attribute("aria-label", re.compile("원본 투과율"))
            page.get_by_role("button", name="Tauc 변환과 피팅", exact=True).click()
            expect(page.locator("#toast")).not_to_have_class(re.compile("is-visible"))
            page.locator("#analysis").screenshot(path=str(artifacts / "tauc-desktop.png"))
            page.locator('[data-id="tauc-range"]').click()
            expect(page.locator(".findings")).to_contain_text("801")
            expect(page.locator("#chart-host [data-annotation]")).to_have_count(1)
            expect(page.locator("#chart-host svg")).to_have_attribute("aria-label",re.compile("투과율"))
            svg_exports["incomplete-spectrum"] = page.locator("#chart-host svg").evaluate("(el) => el.outerHTML")
            page.locator("#analysis").screenshot(path=str(artifacts / "incomplete-desktop.png"))
            page.locator('[data-id="tauc-clear-invalid_percent"]').click()
            expect(page.locator('[data-finding="transmittance_out_of_range"]')).to_contain_text("120%")
            expect(page.locator('#chart-host circle[stroke="#bb3442"]')).to_have_count(1)
            expect(page.locator("#chart-host svg")).to_contain_text("100% 기준선")
            page.locator("#analysis").screenshot(path=str(artifacts / "percent-desktop.png"))
            for material in ["a-IGZO","Poly-Si","a-Si"]:
                page.locator('[data-action="material"][data-material="' + material + '"]').click()
                expect(page.locator("#sample-list .sample-card")).to_have_count(1)


            page.get_by_role("tab", name=re.compile("TFT 전기")).click()
            with page.expect_download() as download_info:
                page.locator(".sample-card").first.get_by_role("link", name="CSV 받기").click()
            assert download_info.value.suggested_filename.endswith(".csv")

            page.locator("#upload-box summary").click()
            file_path = str(ROOT / "samples/igzo20_04.csv")
            page.locator("#file-input").set_input_files(file_path)
            expect(page.locator("#clear-file")).to_be_enabled()
            expect(page.locator("#analyze-file")).to_be_disabled()
            page.locator("#clear-file").click()
            assert page.locator("#file-input").evaluate("(el) => el.files.length") == 0
            expect(page.locator("#analyze-file")).to_be_disabled()
            page.locator("#file-input").set_input_files(file_path)
            page.locator("#condition-confirm").check()
            expect(page.locator("#toast")).not_to_have_class(re.compile("is-visible"))
            page.locator("#upload-box").screenshot(path=str(artifacts / "upload-desktop.png"))
            page.locator("#analyze-file").click()
            expect(page.locator(".candidate")).to_have_count(3)
            expect(page.locator(".result-heading h2")).to_contain_text("igzo20_04.csv")

            page.locator("#clear-file").click()
            held = []
            page.route("**/api**", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
            page.locator("#file-input").set_input_files(file_path)
            page.locator("#condition-confirm").check()
            with page.expect_request(lambda request: request.method == "POST" and "action=analyze" in request.url):
                page.locator("#analyze-file").click()
            expect(page.locator("#clear-file")).to_have_text("분석 취소")
            assert len(held) == 1, "The cancelled request must reach the delayed response handler"
            page.locator("#clear-file").click()
            for route in held:
                try:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({"status":"ready","filename":"stale.csv","domain":"tft","data":{}}))
                except Exception:
                    pass
            page.unroute("**/api**")
            expect(page.locator("#result-panel")).to_contain_text("파일 선택을 취소했어요")
            expect(page.locator(".candidate")).to_have_count(0)
            page.locator("#file-input").set_input_files(file_path)
            page.locator("#condition-confirm").check()
            page.locator("#analyze-file").click()
            expect(page.locator(".candidate")).to_have_count(3)

            page.set_viewport_size({"width":390,"height":844})
            page.locator("#data-drawer summary.drawer-summary").click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert page.locator("body").evaluate("(el) => parseFloat(getComputedStyle(el).fontSize)") >= 15
            expect(page.locator("#toast")).not_to_have_class(re.compile("is-visible"))
            page.locator("#analysis").screenshot(path=str(artifacts / "analysis-mobile.png"))
            page.locator("#choose").screenshot(path=str(artifacts / "input-mobile.png"))
            geometry = page.locator("#sample-list .help-trigger").first
            assert geometry.bounding_box()["width"] >= 44 and geometry.bounding_box()["height"] >= 44
            geometry.click()
            expect(page.locator("#term-tooltip")).to_be_visible()
            tooltip_box = page.locator("#term-tooltip").bounding_box()
            assert tooltip_box["x"] >= 0 and tooltip_box["x"] + tooltip_box["width"] <= 391
            page.locator("#sample-list h3").first.click()
            expect(page.locator("#term-tooltip")).to_be_hidden()
            page.locator("#sample-list .help-trigger").first.click()
            page.screenshot(path=str(artifacts / "tooltip-mobile.png"))
            page.locator("#clear-file").click()
            page.locator("#file-input").set_input_files(str(ROOT / "samples/asi20_06.csv"))
            expect(page.locator("#tft-material")).to_have_value("a-Si")
            expect(page.locator("#tft-length")).to_have_value("6")
            expect(page.locator("#condition-confirm")).not_to_be_checked()
            assert not errors, errors
            touch_context = browser.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True, reduced_motion="reduce")
            touch_page = touch_context.new_page()
            touch_page.goto(base)
            expect(touch_page.locator(".candidate")).to_have_count(3)
            assert touch_page.locator("#chart-host svg").bounding_box()["y"] < 800
            expect(touch_page.locator(".chart-heading")).to_contain_text("버튼으로 확대·축소")
            expect(touch_page.locator(".chart-readout")).to_contain_text("그래프를 누르면")
            touch_page.locator("#chart-host svg").tap()
            expect(touch_page.locator(".chart-readout")).not_to_contain_text("그래프를 누르면")
            touch_page.locator("#analysis").screenshot(path=str(artifacts / "analysis-touch.png"))
            touch_context.close()
            browser.close()
        if os.environ.get("PORTFOLIO_EXPORT_SVG") == "1":
            wanted = os.environ.get('PORTFOLIO_EXPORT_ONLY','').split(',')
            print("SVG_ARTIFACTS=" + json.dumps({k:v for k,v in svg_exports.items() if not wanted[0] or k in wanted}))
            print("API_EVENTS", api_events)
        print("WORKSPACE_BROWSER_FLOW_OK")
        print("Screenshots:", artifacts)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
