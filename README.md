# pdf_to_mp3

Converts a PDF to a cleaned MP3 audiobook using [Piper TTS](https://github.com/rhasspy/piper). Before passing text to the voice synthesizer, the script analyzes each page and removes footnotes, page headers, page numbers, hyphenated line breaks, ligature artifacts, inline citation markers, and other common PDF extraction noise — without discarding content from pages that don't need cleaning.

---

## Dependencies

### Python

- **Python 3.8+**
- **PyMuPDF** (`pymupdf`) — PDF parsing and text extraction

```bash
pip install pymupdf
```

### System tools

| Tool | Purpose | Install |
|---|---|---|
| **Piper** | Text-to-speech engine | See below |
| **ffmpeg** | Encodes WAV output to MP3 | `sudo apt install ffmpeg` |

### Installing Piper

Download the pre-built binary for 64-bit Linux:

```bash
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz
tar -xzf piper_linux_x86_64.tar.gz
sudo mv piper/piper /usr/local/bin/
sudo mv piper/espeak-ng-data /usr/local/lib/
```

For ARM (Raspberry Pi etc.), use `piper_linux_aarch64.tar.gz` instead.

### Downloading a voice model

Piper voices come as a pair of files: a `.onnx` model and a `.onnx.json` config. Browse available voices at [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

```bash
mkdir -p ~/piper-voices && cd ~/piper-voices

wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Both files must be in the same directory. Pass the `.onnx` path to `--model`.

---

## Quick start

```bash
python3 pdf_to_mp3.py input.pdf --model ~/piper-voices/en_US-lessac-medium.onnx
```

Output is saved as `input.mp3` in the same directory as the PDF.

---

## Configuration file

Instead of supplying `--model` on every run, generate a config file once:

```bash
python3 pdf_to_mp3.py --save-example-config
```

This writes `~/.pdf_to_mp3.json` with all available settings. Edit it to set your model path and preferences, then run the script without any flags:

```bash
python3 pdf_to_mp3.py input.pdf
```

Example config:

```json
{
  "model": "~/piper-voices/en_US-lessac-medium.onnx",
  "piper": "piper",
  "ffmpeg": "ffmpeg",
  "clip_ratio": 0.85,
  "scan_ratio": 0.30,
  "min_footnote_lines": 2,
  "keep_headers": false,
  "speed": 1.0
}
```

Command-line flags always override config file values.

---

## All options

| Flag | Default | Description |
|---|---|---|
| `input` | *(required)* | Path to the input PDF |
| `--model PATH` | from config | Path to Piper `.onnx` voice model |
| `--output PATH` | `<input>.mp3` | Output MP3 file path |
| `--config PATH` | `~/.pdf_to_mp3.json` | Path to JSON config file |
| `--clip-ratio FLOAT` | `0.85` | Fraction of page height to keep on pages where footnotes are detected. Only applied to those pages; pages without footnotes are always extracted in full. |
| `--scan-ratio FLOAT` | `0.30` | Fraction of the page bottom to scan when detecting footnotes. Increase if footnotes are being missed. |
| `--min-footnote-lines INT` | `2` | Minimum consecutive footnote-like lines needed to trigger block removal in the text cleaning pass. |
| `--keep-headers` | off | Pass this flag to disable stripping of page headers and running titles. |
| `--preview` | off | Print the cleaned text to stdout without generating any audio. Useful for checking cleaning quality before a long conversion. |
| `--piper PATH` | `piper` | Path to the Piper binary, if not on your `$PATH`. |
| `--ffmpeg PATH` | `ffmpeg` | Path to the ffmpeg binary, if not on your `$PATH`. |
| `--speed FLOAT` | `1.0` | Narration speed. Values above 1.0 are faster, below 1.0 are slower. |
| `--save-example-config` | — | Write an example config to `~/.pdf_to_mp3.json` and exit. |

---

## How the cleaning works

The script applies a multi-stage pipeline to each page before any audio is generated.

**1. Per-page footnote detection**
Each page is individually analyzed before extraction. Two signals are checked in the bottom `scan-ratio` of the page:
- A drawn horizontal separator line (the rule typeset PDFs use to divide body from footnotes)
- Footnote marker patterns: `1.` `1)` `[1]` `*` `†` `‡` `§` etc.

Pages where neither signal is found are extracted in full — no content is lost. Only pages where footnotes are detected are clipped to `clip-ratio` of their height.

**2. Text cleaning passes** (applied to every page after extraction)
- Page numbers and standalone roman numerals are removed
- Running headers (short all-caps or title-case lines at the top of a page) are removed unless `--keep-headers` is set
- Remaining footnote blocks in the extracted text are stripped by pattern matching
- Words hyphenated across line breaks (`some-\nthing`) are rejoined
- Ligatures (`ﬁ`, `ﬂ`, `ﬀ` etc.) are replaced with their ASCII equivalents
- Separator lines (`---`, `===`, `...........`) are removed
- Inline citation markers (`[1]`, `[2,3]`) are stripped
- Whitespace is normalized

**3. Audio generation**
The cleaned text is piped to Piper, which generates a WAV file. ffmpeg then encodes it to MP3 at VBR quality 2 (~190 kbps).

---

## Troubleshooting

**Footnotes are not being removed**
Try increasing `--scan-ratio` (e.g. `0.40`) to scan more of the page, or decreasing `--clip-ratio` (e.g. `0.80`) to cut more aggressively when footnotes are detected.

**Content is missing from pages**
Run with `--preview` to inspect the cleaned text. If pages without footnotes are losing content, check that `--scan-ratio` isn't set unusually high. The script prints `Footnotes detected on X of Y pages` — if that number is unexpectedly high, try lowering `--scan-ratio`.

**Piper or ffmpeg not found**
Pass explicit paths with `--piper /path/to/piper` and `--ffmpeg /path/to/ffmpeg`, or add them to your `$PATH`.

**Voice model not found**
Make sure both the `.onnx` and `.onnx.json` files are present in the same directory and that the path you pass to `--model` points to the `.onnx` file.

---

## License

This script is provided as-is with no warranty. Piper is licensed under the MIT License. PyMuPDF is licensed under AGPL-3.0. ffmpeg is licensed under LGPL/GPL depending on build configuration.
