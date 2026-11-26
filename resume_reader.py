from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF


class ResumeReadError(Exception):
    """Raised when a resume can't be read or has no usable text."""


SUPPORTED_TEXT_EXT = {".txt", ".text", ".md"}

# Matches standalone page numbers: "1", "12", "Page 2", "Page 2 of 3", "- 3 -", "3/5"
PAGE_NUMBER_RE = re.compile(
    r"""^\s*
        (?:page\s*)?                # optional word 'page'
        [-–—~]?\s*                  # optional dash/tilde
        \d{1,3}                     # the page number
        (?:\s*(?:of|/)\s*\d{1,3})?  # optional 'of N' or '/N'
        \s*[-–—~]?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _normalize_line(line: str) -> str:
    """Remove control/zero-width chars and collapse runs of spaces/tabs."""
    line = CONTROL_CHARS_RE.sub("", line)
    line = line.replace("\u00a0", " ").replace("\u200b", "")
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def clean_pages(pages: list[str]) -> str:
    """
    Clean text extracted per page:
      - drop lines that repeat on 2+ pages (headers/footers)
      - drop standalone page-number lines
      - collapse extra whitespace and blank-line runs
    """
    norm_pages = []
    for page in pages:
        page = page.replace("\r\n", "\n").replace("\r", "\n")
        norm_pages.append([_normalize_line(l) for l in page.split("\n")])

    repeats: Counter = Counter()
    for lines in norm_pages:
        repeats.update({l.lower() for l in lines if l and len(l) <= 80})
    headers_footers = {l for l, c in repeats.items() if c >= 2}

    out: list[str] = []
    for lines in norm_pages:
        for line in lines:
            if not line:
                out.append("")                      # keep paragraph breaks
            elif line.lower() in headers_footers:
                continue                            # repeated header/footer
            elif PAGE_NUMBER_RE.match(line):
                continue                            # page number
            else:
                out.append(line)

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)          # collapse blank runs
    return text.strip()


def read_resume(path: str | Path) -> str:
    """Extract and clean resume text. PDF -> PyMuPDF, .txt/.md -> plain read."""
    path = Path(path)
    if not path.is_file():
        raise ResumeReadError(f"file not found: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in SUPPORTED_TEXT_EXT:
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = clean_pages([raw])
        if not text:
            raise ResumeReadError("file is empty")
        return text
    raise ResumeReadError(f"unsupported file type '{ext}' (use .pdf or .txt)")


def _read_pdf(path: Path) -> str:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ResumeReadError(f"could not open PDF ({exc})") from exc

    try:
        if doc.needs_pass:
            raise ResumeReadError("password-protected PDF")

        pages = [page.get_text("text") for page in doc]

        if not "".join(pages).strip():
            # No text layer: image-only (scanned) vs truly blank PDF
            if any(page.get_images(full=True) for page in doc):
                raise ResumeReadError("no text found (scanned file)")
            raise ResumeReadError("no text found (empty PDF)")

        text = clean_pages(pages)
        if not text:  # e.g. only page numbers/headers survived cleaning
            raise ResumeReadError("no text found (empty PDF)")
        return text
    finally:
        doc.close()


def count_tokens(text: str) -> int:
    """tiktoken (cl100k_base) if available, else word-count estimate."""
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(re.findall(r"\S+", text)) or 1


def summarize_resume(path: str | Path) -> dict:
    name = Path(path).name
    try:
        text = read_resume(path)
    except ResumeReadError as exc:
        return {"name": name, "chars": None, "tokens": None, "error": str(exc)}
    return {"name": name, "chars": len(text), "tokens": count_tokens(text), "error": None}