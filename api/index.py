"""Single Vercel function for sample listing, download, and analysis."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis_service import analyze_request, public_samples, sample_file  # noqa: E402


MAX_REQUEST_BYTES = 4_400_000


class handler(BaseHTTPRequestHandler):  # Vercel Python runtime entry point
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        query = parse_qs(urlparse(self.path).query)
        action = query.get("action", [""])[0]
        if action == "samples":
            self._send_json(public_samples())
            return
        if action == "sample":
            sample_id = query.get("id", [""])[0]
            try:
                filename, body = sample_file(sample_id)
            except KeyError:
                self._send_json({"message": "샘플을 찾지 못했어요."}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json({"message": "요청 경로를 확인해주세요."}, 404)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if parse_qs(urlparse(self.path).query).get("action", [""])[0] != "analyze":
            self._send_json({"status": "rejected", "message": "요청 경로를 확인해주세요."}, 404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"status": "rejected", "message": "요청 크기를 확인해주세요."}, 400)
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json({"status": "rejected", "message": "파일은 3 MB 이하로 올려주세요."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("request_object_required")
            result = analyze_request(payload)
            status_code = 200 if result.get("status") != "rejected" else 400
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            result = {"status": "rejected", "message": "요청 내용을 확인해주세요."}
            status_code = 400
        self._send_json(result, status_code)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return
