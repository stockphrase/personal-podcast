# pp (Personal Podcast)

Converts a PDF to a cleaned MP3 audiobook using [Piper TTS](https://github.com/rhasspy/piper). Before passing text to the voice synthesizer, the script analyzes each page and removes footnotes, page headers, page numbers, hyphenated line breaks, ligature artifacts, inline citation markers, and other common PDF extraction noise — without discarding content from pages that don't need cleaning.

---

## Dependencies

### Python

- **Python 3.8+**
- **PyMuPDF** (`pymupdf`) — PDF parsing and text extraction

On Ubuntu/Pop!_OS, install pymupdf into a virtual environment to avoid the externally-managed-environment restriction:

```bash
python3 -m venv ~/code/.venv/pp
source ~/code/.venv/pp/bin/activate
pip install pymupdf
```

Note the path to the venv Python — you will need it for the shebang step below:
```
~/code/.venv/pp/bin/python3
```

### System tools

| Tool | Purpose | Install |
|---|---|---|
| **Piper** | Text-to-speech engine | See below |
| **ffmpeg** | Encodes WAV output to MP3 | `sudo apt install ffmpeg` |
| **ocrmypdf** | OCR for scanned PDFs without a text layer | `sudo apt install ocrmypdf` |

---

### Installing Piper

Download the pre-built binary for 64-bit Linux:

```bash
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz
tar -xzf piper_linux_x86_64.tar.gz
```

Copy the binary and shared libraries to system locations:

```bash
sudo cp piper/piper /usr/local/bin/
sudo cp piper/*.so* /usr/local/lib/
sudo ldconfig
```

Piper expects espeak-ng data at `/usr/share/espeak-ng-data/`. On Ubuntu/Pop!_OS this data is
already installed but lives elsewhere. Symlink it:

```bash
sudo ln -s /usr/lib/x86_64-linux-gnu/espeak-ng-data /usr/share/espeak-ng-data
```

For ARM (Raspberry Pi etc.), use `piper_linux_aarch64.tar.gz` instead.

---

### Installing the script

Before copying, open the downloaded `pp` file and set the shebang on the first line to point
at your venv Python:

```
#!/home/YOUR_USERNAME/code/.venv/pp/bin/python3
```

Then make it executable and place it on your PATH:

```bash
chmod +x pp
sudo cp pp /usr/local/bin/pp
```

---

### Downloading a voice model

Piper voices come as a pair of files: a `.onnx` model and a `.onnx.json` config. Browse
available voices at [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

Store all voice files in `~/piper-voices/`:

```bash
mkdir -p ~/piper-voices && cd ~/piper-voices
```

Recommended voices (download both the `.onnx` and `.onnx.json` for each):

**libritts-high** — most natural sounding, best for long-form reading:
```bash
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/en_US-libritts-high.onnx.json
```

**ryan-high** — clear and natural:
```bash
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json
```

**lessac-medium** — lighter weight, faster:
```bash
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

To test a voice before committing to a full conversion:
```bash
echo "He walked in — and then stopped, waiting." | piper \
  --model ~/piper-voices/en_US-libritts-high.onnx \
  --output_file /tmp/test.wav && ffplay /tmp/test.wav
```

---

## Dealing with scanned PDFs

Many PDFs — especially older academic papers — are scanned images with no real text layer, or
have a corrupt/empty text layer that cannot be selected. These must be OCR'd before `pp` can
process them.

Check whether your PDF has selectable text by trying to select text in a viewer. If you can't
select anything, run it through `ocrmypdf` first:

```bash
ocrmypdf --force-ocr input.pdf input_ocr.pdf
```

`--force-ocr` is needed when the PDF already has a text layer (even a junk one) that would
otherwise cause ocrmypdf to abort. Once done, pass the OCR'd file to `pp`:

```bash
pp input_ocr.pdf
```

---

## Quick start

```bash
pp input.pdf
```

Output is saved as `input.mp3` in the same directory as the PDF.

Always run with `--preview` first on a new PDF to check the quality of the extracted and
cleaned text before committing to audio generation:

```bash
pp input.pdf --preview | less
```

---

## Configuration file

Generate a config file once so you don't need to pass `--model` on every run:

```bash
pp --save-example-config
```

This writes `~/.pp.json`. Edit it to set your preferred voice and any other defaults:

```bash
nano ~/.pp.json
```

Example config:

```json
{
  "model": "~/piper-voices/en_US-libritts-high.onnx",
  "piper": "piper",
  "ffmpeg": "ffmpeg",
  "clip_ratio": 0.85,
  "scan_ratio": 0.30,
  "min_footnote_lines": 2,
  "keep_headers": false,
  "speed": 1.0
}
```

Be careful editing JSON — every key-value pair needs exactly one `"key": value` with no
duplicate labels. A JSON syntax error will prevent `pp` from running.

Command-line flags always override config file values.

---

## All options

| Flag | Default | Description |
|---|---|---|
| `input` | *(required)* | Path to the input PDF |
| `--model PATH` | from config | Path to Piper `.onnx` voice model |
| `--output PATH` | `<input>.mp3` | Output MP3 file path |
| `--config PATH` | `~/.pp.json` | Path to JSON config file |
| `--clip-ratio FLOAT` | `0.85` | Fraction of page height to keep on pages where footnotes are detected. Only applied to those pages; pages without footnotes are always extracted in full. |
| `--scan-ratio FLOAT` | `0.30` | Fraction of the page bottom to scan when detecting footnotes. Increase if footnotes are being missed. |
| `--min-footnote-lines INT` | `2` | Minimum consecutive footnote-like lines needed to trigger block removal in the text cleaning pass. |
| `--keep-headers` | off | Pass this flag to disable stripping of page headers and running titles. |
| `--preview` | off | Print the cleaned text to stdout without generating any audio. Useful for checking cleaning quality before a long conversion. |
| `--piper PATH` | `piper` | Path to the Piper binary, if not on your `$PATH`. |
| `--ffmpeg PATH` | `ffmpeg` | Path to the ffmpeg binary, if not on your `$PATH`. |
| `--speed FLOAT` | `1.0` | Narration speed. Values above 1.0 are faster, below 1.0 are slower. |
| `--save-example-config` | — | Write an example config to `~/.pp.json` and exit. |

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

**`cannot execute: required file not found`**
The shebang at the top of the script points to a Python that doesn't exist. Open
`/usr/local/bin/pp` and make sure the first line points to your venv Python, e.g.:
```
#!/home/alan/code/.venv/pp/bin/python3
```

**`pymupdf is not installed`**
The shebang is pointing at a Python that doesn't have pymupdf. Make sure it points to the
venv where you installed it, and verify with:
```bash
/home/alan/code/.venv/pp/bin/python3 -c "import fitz; print('ok')"
```

**`libpiper_phonemize.so.1: cannot open shared object file`**
The Piper shared libraries weren't copied to a system library path. Run:
```bash
sudo cp ~/piper/*.so* /usr/local/lib/
sudo ldconfig
```

**`Error processing file '/usr/share/espeak-ng-data/phontab': No such file or directory`**
The espeak-ng data directory is missing or not symlinked correctly. Run:
```bash
sudo ln -s /usr/lib/x86_64-linux-gnu/espeak-ng-data /usr/share/espeak-ng-data
```

**`JSONDecodeError` when running pp**
There is a syntax error in `~/.pp.json`. Open it with `nano ~/.pp.json` and check for
duplicate key names or missing commas. Each entry should look like `"key": value,` with no
repeated labels on the same line.

**`PriorOcrFoundError` when running ocrmypdf**
The PDF already has a text layer (even if it's empty or unselectable). Use `--force-ocr`:
```bash
ocrmypdf --force-ocr input.pdf output.pdf
```

**Footnotes are not being removed**
Try increasing `--scan-ratio` (e.g. `0.40`) to scan more of the page, or decreasing
`--clip-ratio` (e.g. `0.80`) to cut more aggressively when footnotes are detected.

**Content is missing from pages**
Run with `--preview` to inspect the cleaned text. The script prints `Footnotes detected on X
of Y pages` — if that number seems too high, try lowering `--scan-ratio`.

**Piper or ffmpeg not found**
Pass explicit paths with `--piper /path/to/piper` and `--ffmpeg /path/to/ffmpeg`, or add them
to your `$PATH`.

**Voice model not found**
Make sure both the `.onnx` and `.onnx.json` files are present in the same directory and that
the path you pass to `--model` points to the `.onnx` file.

---

## License

This script is provided as-is with no warranty. Piper is licensed under the MIT License. PyMuPDF is licensed under AGPL-3.0. ffmpeg is licensed under LGPL/GPL depending on build configuration.
