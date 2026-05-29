#!/usr/bin/env python3
"""
pdf_to_mp3.py — Convert a PDF to a cleaned MP3 using Piper TTS.

Usage:
    python3 pdf_to_mp3.py input.pdf [options]

Options:
    --model PATH          Path to Piper .onnx voice model (required or set in config)
    --output PATH         Output MP3 file path (default: <input_basename>.mp3)
    --config PATH         Path to JSON config file (default: ~/.pdf_to_mp3.json)
    --clip-ratio FLOAT    Fraction of page height to keep when footnotes ARE detected
                          (default: 0.85). Pages without footnotes are never clipped.
    --scan-ratio FLOAT    Fraction of page height to scan for footnote detection
                          (default: 0.30, i.e. bottom 30% of page)
    --min-footnote-lines INT
                          Minimum consecutive short lines to treat as a footnote
                          block (default: 2)
    --keep-headers        Do NOT strip page headers/numbers (default: strip them)
    --preview             Print cleaned text to stdout instead of generating audio
    --piper PATH          Path to piper binary (default: piper)
    --ffmpeg PATH         Path to ffmpeg binary (default: ffmpeg)
    --speed FLOAT         Speaking speed factor (default: 1.0)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    print("ERROR: pymupdf is not installed. Run: pip install pymupdf")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path.home() / ".pdf_to_mp3.json"

def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

def save_example_config(path: Path):
    example = {
        "model": "~/piper-voices/en_US-lessac-medium.onnx",
        "piper": "piper",
        "ffmpeg": "ffmpeg",
        "clip_ratio": 0.85,
        "scan_ratio": 0.30,
        "min_footnote_lines": 2,
        "keep_headers": False,
        "speed": 1.0
    }
    with open(path, "w") as f:
        json.dump(example, f, indent=2)
    print(f"Example config written to {path}")

# ---------------------------------------------------------------------------
# Footnote detection
# ---------------------------------------------------------------------------

FOOTNOTE_MARKER = re.compile(
    r'^\s*(\d{1,3}[\.\):]?|[\*†‡§¶#]|\[[\d\w]+\])\s+\S',
    re.MULTILINE
)

def _page_has_footnotes(page, scan_ratio: float) -> bool:
    """
    Return True if this page appears to contain footnotes, using two signals:
    1. A drawn horizontal separator line in the lower portion of the page.
    2. Footnote marker patterns (1. [1] * † etc.) in the bottom scan_ratio of the page.
    """
    rect = page.rect
    scan_top = rect.y1 * (1.0 - scan_ratio)
    bottom_region = fitz.Rect(rect.x0, scan_top, rect.x1, rect.y1)

    # Signal 1: drawn separator line (short horizontal rule)
    try:
        for drawing in page.get_drawings():
            r = drawing.get('rect')
            if r and r[1] > scan_top:           # in the bottom region
                width  = r[2] - r[0]
                height = r[3] - r[1]
                # A separator is wide relative to height
                if width > rect.width * 0.2 and height < 4:
                    return True
    except Exception:
        pass

    # Signal 2: footnote marker text patterns
    bottom_text = page.get_text(clip=bottom_region)
    if FOOTNOTE_MARKER.search(bottom_text):
        return True

    return False

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(pdf_path: str, clip_ratio: float, scan_ratio: float) -> list:
    """
    Extract text page by page.
    Pages where footnotes are detected are clipped to clip_ratio of their height.
    Pages without footnotes are extracted in full.
    """
    doc = fitz.open(pdf_path)
    pages = []
    footnote_pages = 0
    for page in doc:
        rect = page.rect
        if _page_has_footnotes(page, scan_ratio):
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1 * clip_ratio)
            footnote_pages += 1
        else:
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)  # full page
        text = page.get_text(clip=clip)
        pages.append(text)
    doc.close()
    print(f"  Footnotes detected on {footnote_pages} of {len(pages)} pages")
    return pages

# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def clean_text(pages: list, keep_headers: bool, min_footnote_lines: int) -> str:
    """Apply a series of cleaning passes to extracted page text."""
    cleaned_pages = []
    for text in pages:
        lines = text.splitlines()
        lines = _remove_page_numbers(lines)
        if not keep_headers:
            lines = _remove_headers(lines)
        lines = _remove_footnote_blocks(lines, min_footnote_lines)
        text = "\n".join(lines)
        text = _fix_hyphenation(text)
        text = _clean_artifacts(text)
        cleaned_pages.append(text.strip())

    full_text = "\n\n".join(p for p in cleaned_pages if p)
    full_text = _collapse_whitespace(full_text)
    return full_text

def _remove_page_numbers(lines: list) -> list:
    """Remove lines that are solely a page number (digits, maybe roman numerals)."""
    result = []
    for line in lines:
        stripped = line.strip()
        # Matches: standalone digits, or roman numerals, optionally with dashes
        if re.fullmatch(r'[-–—]?\s*[ivxlcdmIVXLCDM\d]+\s*[-–—]?', stripped):
            continue
        result.append(line)
    return result

def _remove_headers(lines: list) -> list:
    """
    Heuristically remove page headers: short lines at the very top of a page
    that look like a title or chapter label (all caps, or short repeated text).
    We remove the first 1-2 lines if they are short and not sentence-like.
    """
    if not lines:
        return lines
    result = list(lines)
    for i in range(min(2, len(result))):
        stripped = result[i].strip()
        if 0 < len(stripped) <= 80 and not stripped.endswith(('.', ',', ';', ':')):
            if stripped.isupper() or re.fullmatch(r'[A-Z][^\.\?!]{0,60}', stripped):
                result[i] = ''
    return result

def _remove_footnote_blocks(lines: list, min_lines: int) -> list:
    """
    Remove blocks of lines that look like footnotes:
    - Lines starting with a superscript-style number or symbol (1, ², *, †, etc.)
    - Clusters of short lines near the end of the page text
    """
    result = []
    footnote_pattern = re.compile(
        r'^\s*(\d{1,3}[\.\):]?|[\*†‡§¶#]|\[[\d\w]+\])\s+\S'
    )
    skip_remaining = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Once we detect a footnote block, skip to end of page
        if skip_remaining:
            continue

        if footnote_pattern.match(stripped):
            # Check if followed by more footnote-like lines
            following = [l.strip() for l in lines[i+1:i+1+min_lines]]
            if len(following) >= min_lines - 1:
                skip_remaining = True
                continue

        result.append(line)

    return result

def _fix_hyphenation(text: str) -> str:
    """Join words hyphenated across line breaks: 'some- \nthing' → 'something'."""
    # Hard hyphen at end of line followed by newline
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    return text

def _clean_artifacts(text: str) -> str:
    """Remove common PDF text extraction artifacts."""
    # Remove form feed characters
    text = text.replace('\f', '\n')
    # Remove null bytes
    text = text.replace('\x00', '')
    # Ligature replacements
    ligatures = {'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st'}
    for lig, rep in ligatures.items():
        text = text.replace(lig, rep)
    # Remove lines that are just punctuation/symbols (table rules, etc.)
    text = re.sub(r'^\s*[=\-_*~•·]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Collapse runs of dots (e.g. table of contents leaders)
    text = re.sub(r'\.{4,}', ' ', text)
    # Remove bracketed citation numbers like [1], [23], [1,2,3]
    text = re.sub(r'\[[\d,\s]+\]', '', text)
    # Remove superscript-style inline footnote markers (digits right after words)
    text = re.sub(r'(\w)\d{1,3}(?=\s)', r'\1', text)
    return text

def _collapse_whitespace(text: str) -> str:
    """Normalize whitespace: collapse blank lines, trim edges."""
    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse multiple spaces
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()

# ---------------------------------------------------------------------------
# TTS + encoding
# ---------------------------------------------------------------------------

def text_to_mp3(text: str, model: str, output: str, piper_bin: str,
                ffmpeg_bin: str, speed: float):
    """Pipe cleaned text through Piper TTS then encode to MP3 with ffmpeg."""
    model = str(Path(model).expanduser())
    if not Path(model).exists():
        print(f"ERROR: Voice model not found: {model}")
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        print(f"▶ Running Piper TTS → {wav_path}")
        piper_cmd = [
            piper_bin,
            "--model", model,
            "--output_file", wav_path,
            "--length_scale", str(1.0 / speed),  # length_scale is inverse of speed
        ]
        result = subprocess.run(
            piper_cmd,
            input=text.encode("utf-8"),
            capture_output=True
        )
        if result.returncode != 0:
            print("ERROR: Piper failed:")
            print(result.stderr.decode())
            sys.exit(1)

        print(f"▶ Encoding to MP3 → {output}")
        ffmpeg_cmd = [
            ffmpeg_bin,
            "-y",           # overwrite output
            "-i", wav_path,
            "-q:a", "2",    # VBR quality (2 ≈ ~190kbps, good quality)
            output
        ]
        result = subprocess.run(ffmpeg_cmd, capture_output=True)
        if result.returncode != 0:
            print("ERROR: ffmpeg failed:")
            print(result.stderr.decode())
            sys.exit(1)

        print(f"✓ Done! Output: {output}")

    finally:
        if Path(wav_path).exists():
            os.unlink(wav_path)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a PDF to MP3 using Piper TTS with smart cleaning."
    )
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("--model", help="Path to Piper .onnx voice model")
    parser.add_argument("--output", help="Output MP3 path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--clip-ratio", type=float,
                        help="Page height fraction to keep when footnotes detected (default: 0.85)")
    parser.add_argument("--scan-ratio", type=float,
                        help="Bottom fraction of page to scan for footnotes (default: 0.30)")
    parser.add_argument("--min-footnote-lines", type=int,
                        help="Min lines to trigger footnote block removal (default: 2)")
    parser.add_argument("--keep-headers", action="store_true",
                        help="Disable header/page-number stripping")
    parser.add_argument("--preview", action="store_true",
                        help="Print cleaned text only, do not generate audio")
    parser.add_argument("--piper", help="Path to piper binary (default: piper)")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg binary (default: ffmpeg)")
    parser.add_argument("--speed", type=float, help="Speaking speed (default: 1.0)")
    parser.add_argument("--save-example-config", action="store_true",
                        help="Write an example config to ~/.pdf_to_mp3.json and exit")
    return parser.parse_args()

def main():
    args = parse_args()

    if args.save_example_config:
        save_example_config(DEFAULT_CONFIG_PATH)
        return

    # Merge config file → CLI args (CLI wins)
    cfg = load_config(Path(args.config))
    def get(arg_val, cfg_key, default):
        return arg_val if arg_val is not None else cfg.get(cfg_key, default)

    model        = get(args.model,              "model",              None)
    output       = get(args.output,             "output",             None)
    clip_ratio   = get(args.clip_ratio,         "clip_ratio",         0.85)
    scan_ratio   = get(args.scan_ratio,         "scan_ratio",         0.30)
    min_fn_lines = get(args.min_footnote_lines, "min_footnote_lines", 2)
    keep_headers = args.keep_headers or cfg.get("keep_headers", False)
    piper_bin    = get(args.piper,              "piper",              "piper")
    ffmpeg_bin   = get(args.ffmpeg,             "ffmpeg",             "ffmpeg")
    speed        = get(args.speed,              "speed",              1.0)

    if not args.preview and not model:
        print("ERROR: --model is required (or set 'model' in config file).")
        print("       Run with --save-example-config to generate a starter config.")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    if output is None:
        output = str(input_path.with_suffix(".mp3"))

    print(f"▶ Extracting text from {input_path} (clip_ratio={clip_ratio}, scan_ratio={scan_ratio})")
    pages = extract_text(str(input_path), clip_ratio, scan_ratio)

    print(f"▶ Cleaning text ({len(pages)} pages)")
    text = clean_text(pages, keep_headers=keep_headers,
                      min_footnote_lines=min_fn_lines)

    word_count = len(text.split())
    print(f"  {word_count} words after cleaning")

    if args.preview:
        print("\n" + "="*60)
        print(text)
        return

    text_to_mp3(text, model=model, output=output, piper_bin=piper_bin,
                ffmpeg_bin=ffmpeg_bin, speed=speed)

if __name__ == "__main__":
    main()