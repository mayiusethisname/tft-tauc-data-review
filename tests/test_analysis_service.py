"""Checks tied to measured controls, independently recomputed fits and injected faults."""
from __future__ import annotations

import csv
import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis_service import analyze_bytes, analyze_request, MAX_UPLOAD_BYTES
from examples import get_sample, SAMPLES


class PublicAnalysisTests(unittest.TestCase):
    def test_half_volt_sensitivity_matches_independent_regression(self):
        for sample_id, sample in SAMPLES.items():
            if sample['domain'] != 'tft' or sample['kind'] != 'measured':
                continue
            result = analyze_request({'sample_id':sample_id})
            for candidate in result['data']['candidates']:
                for shifted in candidate['sensitivity']['rows']:
                    if shifted['status'] != 'calculated':
                        continue
                    points = [(p['x'], math.sqrt(abs(p['current_A']))) for p in result['data']['points']
                              if shifted['start_raw_V']-1e-8 <= p['x'] <= shifted['end_raw_V']+1e-8]
                    mx = math.fsum(x for x,y in points)/len(points)
                    my = math.fsum(y for x,y in points)/len(points)
                    slope = math.fsum((x-mx)*(y-my) for x,y in points)/math.fsum((x-mx)**2 for x,y in points)
                    intercept = my-slope*mx
                    expected_mu = 2*slope*slope/(17.5e-9*sample['width_um']/sample['length_um'])
                    self.assertAlmostEqual(shifted['mu_cm2_Vs'], expected_mu, places=7)
                    self.assertAlmostEqual(shifted['vth_V'], -intercept/slope, places=8)
                    self.assertAlmostEqual(shifted['delta_mu_pct'], (expected_mu/candidate['mu_sat_cm2_Vs']-1)*100, places=7)

    def test_perfect_r2_does_not_pass_inconsistent_saturation_bias(self):
        rows = ['VGS,VDS,IDS']+[f'{i/10},{i/10},{((i/10)+2)**2*1e-6}' for i in range(201)]
        result = analyze_bytes('tft','aIGZO_W20_L04_Mobility.csv','\n'.join(rows).encode(),
                               {'material':'a-IGZO','width_um':20,'length_um':4,'conditions_confirmed':True})
        candidate = result['data']['candidates'][0]
        self.assertGreater(candidate['r2'], .999999)
        self.assertFalse(candidate['model_check']['passed'])
        self.assertAlmostEqual(candidate['model_check']['saturation_margin_min_V'], -2, places=6)
        self.assertIn('bias_condition', [f['code'] for f in result['findings']])

    def test_measured_asset_integrity(self):
        manifest = json.loads((ROOT / "samples/manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            raw = (ROOT / "samples" / item["asset"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
            self.assertEqual(item["numeric_changes"], "none")

    def test_measured_tft_fit_matches_independent_regression(self):
        for sample_id in (key for key, value in SAMPLES.items() if value["domain"] == "tft" and value["kind"] == "measured"):
            sample, raw = get_sample(sample_id)
            result = analyze_request({"sample_id": sample_id})
            self.assertEqual(result["status"], "ready")
            self.assertEqual([f['code'] for f in result['findings']], ['endpoint_discontinuity'] if sample_id == 'tft-window' else [])
            self.assertEqual(len(result["data"]["points"]), 201)
            c = result["data"]["candidates"][0]
            rows = list(csv.DictReader(io.StringIO(raw.decode())))
            selected = [(float(r["VGS"]), math.sqrt(abs(float(r["IDS"])))) for r in rows if c["start_raw_V"] <= float(r["VGS"]) <= c["end_raw_V"]]
            n = len(selected)
            mx = math.fsum(x for x, _ in selected) / n
            my = math.fsum(y for _, y in selected) / n
            slope = math.fsum((x - mx) * (y - my) for x, y in selected) / math.fsum((x - mx) ** 2 for x, _ in selected)
            intercept = my - slope * mx
            expected_mu = 2 * sample["profile"]["length_um"] * slope ** 2 / (sample["profile"]["width_um"] * 1.75e-8)
            self.assertAlmostEqual(c["mu_sat_cm2_Vs"], expected_mu, places=6)
            self.assertAlmostEqual(c["vth_sat_raw_V"], -intercept / slope, places=7)
            self.assertGreater(c["r2"], .995)
            self.assertIn("mu_shift_max_pct", c)
            self.assertIn("slope_stability", c)

    def test_spike_copy_changes_one_value_and_is_detected(self):
        _, control = get_sample("tft-clear")
        _, changed = get_sample("tft-spike")
        normal_rows, changed_rows = control.decode().splitlines(), changed.decode().splitlines()
        self.assertEqual(sum(a != b for a, b in zip(normal_rows, changed_rows)), 1)
        result = analyze_request({"sample_id": "tft-spike"})
        self.assertEqual(result["status"], "ready")
        finding = next(f for f in result["findings"] if f["code"] == "isolated_spike")
        self.assertEqual(len(finding["voltages"]), 1)
        self.assertTrue(finding["action"])
        self.assertTrue(result["data"]["candidates"])

    def test_missing_current_header_stops_calculation(self):
        result = analyze_request({"sample_id": "tft-hold"})
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertFalse(result["data"]["candidates"])
        self.assertIn("VGS/VDS/IDS", result["intake"]["hold_reasons"][0])
        self.assertIn("전류", result["findings"][0]["title"])

    def test_measured_tauc_has_transformed_points_and_correct_intercepts(self):
        result = analyze_request({"sample_id": "tauc-clear"})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["data"]["point_count"], 4001)
        self.assertFalse(result["findings"])
        self.assertTrue(result["data"]["candidates"][0]["plot_id"].startswith("beer_lambert"))
        for c in result["data"]["candidates"]:
            self.assertAlmostEqual(c["eg_ev"], -c["intercept"] / c["slope"], places=10)
            points = result["data"]["plots"][c["plot_id"]]["points"]
            self.assertGreater(len(points), 100)
            self.assertTrue(all(math.isfinite(v) for p in points for v in p))
            self.assertGreater(c["points"], 20)

    def test_truncated_measured_spectrum_is_held(self):
        result = analyze_request({"sample_id": "tauc-range"})
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("point_count_mismatch", result["intake"]["hold_reasons"])
        self.assertFalse(result["data"])
        self.assertIn("4,001", result["findings"][0]["action"])

    def test_sample_and_downloaded_upload_use_the_same_path(self):
        sample, raw = get_sample("tft-clear")
        from_sample = analyze_request({"sample_id": "tft-clear"})
        from_file = analyze_bytes("tft", sample["filename"], raw, {**sample["profile"], "polarity": "auto"})
        self.assertEqual(from_sample["decision_key"], from_file["decision_key"])
        self.assertEqual(from_sample["data"], from_file["data"])

    def test_same_filename_with_changed_content_gets_a_new_review_identity(self):
        sample, raw = get_sample("tft-clear")
        first = analyze_bytes("tft", sample["filename"], raw, sample["profile"])
        second = analyze_bytes("tft", sample["filename"], raw + b"\n", sample["profile"])
        self.assertEqual(first["filename"], second["filename"])
        self.assertNotEqual(first["decision_key"], second["decision_key"])

    def test_upload_limit_and_empty_input(self):
        large = analyze_bytes("tft", "IGZO2004.csv", b"x" * (MAX_UPLOAD_BYTES + 1))
        empty = analyze_bytes("tft", "IGZO2004.csv", b"")
        self.assertEqual(large["status"], "rejected")
        self.assertEqual(empty["status"], "rejected")

    def test_catalog_has_real_files_for_each_material_and_separate_faults(self):
        measured = Counter((s['domain'], s['material']) for s in SAMPLES.values() if s['kind'] == 'measured')
        self.assertEqual(measured, {('tft','a-Si'):3, ('tft','a-IGZO'):3, ('tft','LTPS'):3, ('tauc','a-Si'):1, ('tauc','a-IGZO'):1, ('tauc','Poly-Si'):1})
        self.assertEqual(sum(s['kind'] == 'modified' for s in SAMPLES.values()), 21)

    def test_all_advertised_faults_work_without_sample_metadata(self):
        codes = {'spike':'isolated_spike', 'gap':'measurement_gap', 'missing_current':'VGS/VDS/IDS 열을 확정할 수 없습니다.', 'short_spectrum':'spectrum_incomplete', 'invalid_percent':'transmittance_out_of_range', 'range_step':'current_step', 'high_drive_rolloff':'high_drive_rolloff'}
        for key, item in SAMPLES.items():
            sample, raw = get_sample(key)
            uploaded = analyze_request({'domain':sample['domain'], 'filename':sample['filename'], 'config':sample['profile'], 'content_base64':base64.b64encode(raw).decode()})
            from_demo = analyze_request({'sample_id':key})
            self.assertEqual(uploaded['data'], from_demo['data'], key)
            self.assertEqual(uploaded['findings'], from_demo['findings'], key)
            if item['kind'] == 'measured':
                self.assertEqual(uploaded['status'], 'ready', key)
                self.assertEqual([f['code'] for f in uploaded['findings']], ['endpoint_discontinuity'] if key == 'tft-window' else [], key)
                continue
            self.assertIn(codes[item['fault']], [f['code'] for f in uploaded['findings']], key)
            if item['fault'] in {'gap', 'missing_current', 'short_spectrum', 'invalid_percent'}:
                self.assertEqual(uploaded['status'], 'needs_confirmation', key)
                self.assertFalse(uploaded.get('data', {}).get('candidates'), key)

    def test_blocked_inputs_keep_only_honest_drawable_evidence(self):
        unknown = analyze_request({'sample_id':'tft-hold'})
        self.assertIn('UNKNOWN', unknown['preview']['y_label'])
        self.assertIn('단위 미확정', unknown['preview']['y_label'])
        self.assertEqual(len(unknown['preview']['points']), 201)
        self.assertEqual(unknown['preview']['table']['headers'], ['VGS','VDS','UNKNOWN'])
        short = analyze_request({'sample_id':'tauc-range'})
        self.assertEqual(short['preview']['point_count'], 801)
        self.assertEqual(short['preview']['x_domain'], [300,700])
        self.assertLessEqual(max(x for x, y in short['preview']['points']), 380)
        self.assertEqual(short['findings'][0]['ranges'], [[380,700]])
        invalid = analyze_request({'sample_id':'tauc-clear-invalid_percent'})
        self.assertIn([400,120], invalid['preview']['markers'])
        self.assertIn([400,120], invalid['preview']['points'])
        self.assertEqual(invalid['preview']['limits'], [100])


if __name__ == "__main__":
    unittest.main()
