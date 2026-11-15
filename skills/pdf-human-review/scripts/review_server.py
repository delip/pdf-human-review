#!/usr/bin/env python3
"""Serve a review page on localhost and hand the reviewer's feedback to the agent.

  review_server.py serve FILE.pdf [--out DIR] [--port N] [--no-open]
      Builds the review page for the PDF, serves it at http://127.0.0.1:PORT/
      and blocks until the reviewer presses "Submit comments". Then it prints
      the feedback markdown on stdout and exits 0. The URL goes to stderr as
      soon as the server is listening.

      Working files go in DIR, which defaults to a folder for this PDF under
      the system temporary folder, so nothing is written into the project.
      Each review of the same PDF empties that folder first. After Submit it
      holds only feedback.md, feedback.json and one region-N.png per boxed
      area. Folders of other reviews untouched for a week are removed.

  review_server.py collect FILE.pdf
      Prints the feedback if it has arrived: feedback.md if the server
      received it, otherwise the system clipboard if it holds feedback (the
      page copies it there when it cannot reach the server). Exits 1 if there
      is no feedback yet.

  review_server.py clean [FILE.pdf]
      Removes the working files of that PDF's review, or of every review.

Standard library only.
"""
import argparse
import base64
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True   # no __pycache__ left in the plugin folder
from build_review import build, empty_dir, prune_stale, temp_root, work_dir

DEFAULT_PORT = 47800
MAX_BODY = 64 * 1024 * 1024
HEADER_START, HEADER_END = "Feedback for ", " from human reviewer"


def looks_like_feedback(text: str) -> bool:
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    return first.startswith(HEADER_START) and first.rstrip().endswith(HEADER_END)


def stop_previous(out_dir: Path) -> None:
    """A new review of the same PDF replaces one that is still being served."""
    try:
        pid = int(json.loads((out_dir / "server.json").read_text())["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return
    if pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.4)
    except OSError:
        pass


def serve(args) -> int:
    if not args.pdf.is_file():
        sys.exit(f"no such file: {args.pdf}")
    out_dir = args.out or work_dir(str(args.pdf))
    prune_stale()
    stop_previous(out_dir)
    empty_dir(out_dir)          # every review of this PDF starts from an empty folder
    page_path = out_dir / "review.html"
    build(str(args.pdf), page_path)
    feedback_path = out_dir / "feedback.md"
    token = secrets.token_urlsafe(24)
    page = page_path.read_text(encoding="utf-8").replace("__PHR_TOKEN__", token).encode("utf-8")
    received = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002 - keep the request log out of the agent's output
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"forbidden")
            if self.path.split("?")[0] in ("/", "/index.html", "/review.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            self._send(404, b"not found")

        def do_POST(self):
            if not self._host_ok() or self.path != "/submit":
                return self._send(403, b"forbidden")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY:
                return self._send(400, b"bad length")
            try:
                data = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send(400, b"bad json")
            if not isinstance(data, dict) or not secrets.compare_digest(str(data.get("token", "")), token):
                return self._send(403, b"bad token")
            markdown = data.get("markdown")
            if not isinstance(markdown, str) or not looks_like_feedback(markdown):
                return self._send(400, b"bad feedback")
            if done.is_set():
                return self._send(409, b"already submitted")
            details = []
            for item in data.get("comments") or []:
                if not isinstance(item, dict):
                    continue
                entry = {k: item.get(k) for k in ("page", "kind", "quote", "comment", "rects")}
                name, image = str(item.get("image_name") or ""), str(item.get("image") or "")
                prefix = "data:image/png;base64,"
                if re.fullmatch(r"region-\d+\.png", name) and image.startswith(prefix):
                    try:
                        (out_dir / name).write_bytes(base64.b64decode(image[len(prefix):]))
                        entry["image"] = str(out_dir / name)
                    except (ValueError, OSError):
                        pass
                details.append(entry)
            received["markdown"] = markdown
            feedback_path.write_text(markdown, encoding="utf-8")
            (out_dir / "feedback.json").write_text(json.dumps({"comments": details}, indent=2), encoding="utf-8")
            self._send(200, b"ok")
            done.set()

    server = None
    ports = [args.port] if args.port else list(range(DEFAULT_PORT, DEFAULT_PORT + 20)) + [0]
    for port in ports:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("could not open a local port for the review page")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    (out_dir / "server.json").write_text(json.dumps({"url": url, "pid": os.getpid()}))
    print(f"Review page: {url}\nWaiting for the reviewer to press Submit comments...", file=sys.stderr, flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)  # so a killed server still removes server.json
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - the URL was printed; the user can open it
            pass
    try:
        done.wait()
    except KeyboardInterrupt:
        print("stopped before any feedback was submitted", file=sys.stderr)
        empty_dir(out_dir)      # nothing was submitted, so leave nothing behind
        return 130
    for name in ("server.json", "review.html"):   # the page is no longer needed once feedback is in
        try:
            (out_dir / name).unlink()
        except OSError:
            pass
    threading.Event().wait(0.3)  # let the response reach the browser
    server.shutdown()
    sys.stdout.write(received["markdown"])
    sys.stdout.flush()
    return 0


def read_clipboard() -> "str | None":
    candidates = [
        ["pbpaste"],
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
        ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
    ]
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return result.stdout
    return None


def collect(args) -> int:
    folder = args.pdf if args.pdf.is_dir() else work_dir(str(args.pdf))
    feedback_path = folder / "feedback.md"
    if feedback_path.is_file():
        sys.stdout.write(feedback_path.read_text(encoding="utf-8"))
        return 0
    clip = read_clipboard()
    if clip is None:
        print("No feedback.md yet, and no clipboard tool was found. Ask the reviewer to paste the feedback into the chat.", file=sys.stderr)
        return 1
    if looks_like_feedback(clip):
        text = clip.replace("\r\n", "\n")
        print("(feedback read from the clipboard)", file=sys.stderr)
        sys.stdout.write(text)
        return 0
    print("No feedback yet: feedback.md does not exist and the clipboard does not hold review feedback.", file=sys.stderr)
    return 1


def clean(args) -> int:
    if args.pdf:
        empty_dir(work_dir(str(args.pdf)))
    elif temp_root().is_dir():
        for folder in temp_root().iterdir():
            empty_dir(folder)
        try:
            temp_root().rmdir()
        except OSError:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve")
    p.add_argument("pdf", type=Path, help="the PDF to review")
    p.add_argument("--out", type=Path, help="working folder (default: a folder for this PDF under the system temporary folder)")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=serve)
    p = sub.add_parser("collect")
    p.add_argument("pdf", type=Path, help="the PDF under review")
    p.set_defaults(fn=collect)
    p = sub.add_parser("clean")
    p.add_argument("pdf", type=Path, nargs="?", help="the PDF whose review files to remove (default: all reviews)")
    p.set_defaults(fn=clean)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
