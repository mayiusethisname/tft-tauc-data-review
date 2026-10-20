"""Run the portfolio locally with Python's standard library."""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from analysis_service import MAX_UPLOAD_BYTES, analyze_request, public_samples, sample_file  # noqa: E402


MAX_REQUEST_BYTES = 4_400_000


class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        route = urlparse(self.path)
        action = parse_qs(route.query).get("action", [""])[0]
        if route.path == "/api" and action == "samples":
            self._send_json(public_samples())
            return
        if route.path == "/api" and action == "sample":
            sample_id = parse_qs(route.query).get("id", [""])[0]
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
        if route.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        route = urlparse(self.path)
        if route.path != "/api" or parse_qs(route.query).get("action", [""])[0] != "analyze":
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
            status = 200 if result.get("status") != "rejected" else 400
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            result = {"status": "rejected", "message": "요청 내용을 확인해주세요."}
            status = 400
        self._send_json(result, status)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TFT · Tauc portfolio demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), partial(PortfolioHandler))
    print(f"Demo ready at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDemo stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
