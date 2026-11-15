#!/usr/bin/env python3
"""Build the review page for one PDF.

  build_review.py PATH/TO/FILE.pdf [--out DIR/review.html]

The page shows the PDF itself, drawn by PDF.js, with selectable text. The PDF
is embedded in the page, so review.html is one self-contained file that works
both from the local review server and when opened directly. Without --out the
page goes in this PDF's working folder under the system temporary folder, so
nothing is written into the project. Standard library only. PDF.js is loaded
from a CDN when the page opens.
"""
import argparse
import base64
import hashlib
import html
import json
import secrets
import sys
import tempfile
import time
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "review_template.html"
OUR_FILES = ("review.html", "feedback.md", "feedback.json", "server.json", "region-*.png")
STALE_AFTER_DAYS = 7


def temp_root() -> Path:
    return Path(tempfile.gettempdir()) / "pdf-human-review"


def work_dir(pdf: str) -> Path:
    """The working folder for one PDF: stable per file, outside the project."""
    path = Path(pdf).expanduser().resolve()
    tag = hashlib.sha1(str(path).encode()).hexdigest()[:8]
    return temp_root() / f"{path.stem}-{tag}"


def empty_dir(folder: Path) -> None:
    """Remove the files this plugin writes, and the folder if nothing else is in it."""
    if not folder.is_dir():
        return
    for pattern in OUR_FILES:
        for f in folder.glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass
    try:
        folder.rmdir()
        if folder.parent == temp_root():
            folder.parent.rmdir()     # succeeds only when no other review is left
    except OSError:
        pass


def prune_stale() -> None:
    """Drop working folders of other reviews that have not been touched for a week."""
    root = temp_root()
    if not root.is_dir():
        return
    cutoff = time.time() - STALE_AFTER_DAYS * 86400
    for folder in root.iterdir():
        try:
            if folder.is_dir() and folder.stat().st_mtime < cutoff:
                empty_dir(folder)
        except OSError:
            pass


def build(pdf: str, out: Path) -> dict:
    pdf_path = Path(pdf).expanduser()
    if not pdf_path.is_file():
        sys.exit(f"no such file: {pdf}")
    data = pdf_path.read_bytes()
    if data.lstrip()[:5] != b"%PDF-":
        sys.exit(f"not a PDF: {pdf}")
    meta = {"pdf": pdf, "docId": hashlib.sha1(data).hexdigest()[:16], "outDir": str(out.parent)}
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("{{NONCE}}", secrets.token_urlsafe(16))
    page = page.replace("{{TITLE}}", html.escape(pdf_path.name))
    page = page.replace("{{META_JSON}}", json.dumps(meta).replace("</", "<\\/"))
    page = page.replace("{{PDF_BASE64}}", base64.b64encode(data).decode("ascii"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return {"review_page": str(out), "pdf_bytes": len(data)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="the PDF to review; the path is quoted in the feedback as given here")
    ap.add_argument("--out", type=Path, help="where to write review.html (default: the PDF's temporary working folder)")
    args = ap.parse_args()
    if args.out:
        out = args.out
    else:
        folder = work_dir(args.pdf)
        empty_dir(folder)
        out = folder / "review.html"
    print(json.dumps(build(args.pdf, out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
