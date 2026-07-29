#!/usr/bin/env python3
"""Local dashboard server and launcher for cc-grammar-coach.

Serves the dashboard UI (index.html, duo.css from this file's own directory) and JSON data from $GRAMMAR_HOME on 127.0.0.1 only. Running it is the launcher: if the port already answers with our health marker it opens the browser and exits; if the port is held by something else it exits with a message naming $GRAMMAR_DASHBOARD_PORT. Stdlib only.

Usage: python3 server.py [--no-open] [--url-path "#progress"]
"""

import argparse
import json
import os
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote
from urllib.request import urlopen

APP = "cc-grammar-coach"
VERSION = "0.6.0"
APP_DIR = Path(__file__).resolve().parent
GRAMMAR_HOME = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$")


def read_jsonl(path: Path) -> list:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def drill_summaries() -> list:
    out = []
    for p in sorted((GRAMMAR_HOME / "drills").glob("*.json"), key=lambda p: p.name, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        topics = data.get("topics") if isinstance(data.get("topics"), list) else []
        out.append({
            "file": p.name,
            "kind": data.get("kind"),
            "date": data.get("date"),
            "topics": [{"label": t.get("label"), "count": t.get("count")} for t in topics if isinstance(t, dict)],
        })
    return out


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def valid_result(obj) -> bool:
    if not isinstance(obj, dict) or set(obj) != {"ts", "drill", "total", "correct", "byTopic"}:
        return False
    if not isinstance(obj["ts"], str):
        return False
    drill = obj["drill"]
    if not isinstance(drill, str) or drill != os.path.basename(drill) or not drill.endswith(".json"):
        return False
    if not (GRAMMAR_HOME / "drills" / drill).is_file():
        return False
    if not is_int(obj["total"]) or not is_int(obj["correct"]):
        return False
    if not isinstance(obj["byTopic"], dict):
        return False
    for v in obj["byTopic"].values():
        if not isinstance(v, dict) or set(v) != {"good", "total"}:
            return False
        if not is_int(v["good"]) or not is_int(v["total"]):
            return False
    return True


class Handler(BaseHTTPRequestHandler):
    def send_json(self, obj, status=200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_app_file(self, name: str, ctype: str) -> None:
        try:
            body = (APP_DIR / name).read_bytes()
        except OSError:
            return self.send_json({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self) -> bool:
        return bool(HOST_RE.match(self.headers.get("Host", "")))

    def do_GET(self) -> None:
        if not self.host_ok():
            return self.send_json({"error": "forbidden host"}, 403)
        path = unquote(self.path.split("?", 1)[0])
        if path == "/":
            return self.send_app_file("index.html", "text/html; charset=utf-8")
        if path == "/duo.css":
            return self.send_app_file("duo.css", "text/css; charset=utf-8")
        if path == "/api/health":
            return self.send_json({"app": APP, "version": VERSION})
        if path == "/api/history":
            return self.send_json(read_jsonl(GRAMMAR_HOME / "history.jsonl"))
        if path == "/api/results":
            return self.send_json(read_jsonl(GRAMMAR_HOME / "results.jsonl"))
        if path == "/api/drills":
            return self.send_json(drill_summaries())
        if path.startswith("/api/drills/"):
            name = path[len("/api/drills/"):]
            if name == os.path.basename(name) and name.endswith(".json"):
                p = GRAMMAR_HOME / "drills" / name
                try:
                    return self.send_json(json.loads(p.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    pass
            return self.send_json({"error": "not found"}, 404)
        return self.send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if not self.host_ok():
            return self.send_json({"error": "forbidden host"}, 403)
        if self.path.split("?", 1)[0] != "/api/results":
            return self.send_json({"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", ""))
            obj = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self.send_json({"error": "malformed body"}, 400)
        if not valid_result(obj):
            return self.send_json({"error": "invalid result"}, 400)
        with open(GRAMMAR_HOME / "results.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return self.send_json({"ok": True})

    def log_message(self, fmt, *args) -> None:
        pass


def probe(port: int):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        return info if isinstance(info, dict) and info.get("app") == APP else "foreign"
    except URLError as exc:
        return None if isinstance(getattr(exc, "reason", None), ConnectionRefusedError) else "foreign"
    except (OSError, ValueError):
        return "foreign"


def main() -> None:
    parser = argparse.ArgumentParser(description="cc-grammar-coach dashboard server/launcher")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--url-path", default="", metavar="HASH", help='hash route to open, e.g. "#progress"')
    args = parser.parse_args()

    port = int(os.environ.get("GRAMMAR_DASHBOARD_PORT", "8437"))
    url = f"http://127.0.0.1:{port}/{args.url_path}"
    running = probe(port)
    if isinstance(running, dict):
        if running.get("version") != VERSION:
            print(f"dashboard already running at {url} with version {running.get('version')} (local copy is {VERSION}); stop it with Ctrl+C and relaunch to pick up the update")
        else:
            print(f"dashboard already running at {url}")
        if not args.no_open:
            webbrowser.open(url)
        sys.exit(0)
    if running == "foreign":
        print(f"port {port} is in use by another program; set GRAMMAR_DASHBOARD_PORT to a free port and relaunch", file=sys.stderr)
        sys.exit(1)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        print(f"cannot bind 127.0.0.1:{port} ({exc}); set GRAMMAR_DASHBOARD_PORT to a free port", file=sys.stderr)
        sys.exit(1)
    print(f"serving the {APP} dashboard at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
