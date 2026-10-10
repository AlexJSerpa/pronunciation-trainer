# English Pronunciation Trainer

A local web application that imports an Anki `.apkg` deck (words, answers, audio), lets you record your voice, transcribes it locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), compares the transcript with the target word or sentence, and highlights pronunciation mismatches in red.

## Features

- **100% Local**: Runs speech recognition on your machine without third-party cloud APIs.
- **Anki `.apkg` Importer**: Imports cards and extracts audio files directly from Anki decks (supports both legacy and modern zstd/protobuf decks).
- **2-Step Learning Workflow**:
  - **Step 1 (Recall & Typing)**: See the sentence with the missing word as a blank (e.g. *He _____ when he is sad.*) and definition hint, then type the word to verify your vocabulary.
  - **Step 2 (Sentence Pronunciation)**: Once verified, read the full sentence aloud into your microphone to practice pronunciation.
- **Fast Transcription**: Powered by `faster-whisper` (CTranslate2) with word timestamps and VAD filtering.
- **Smart Sequence Alignment & Homophone Handling**: Powered by `difflib` and CMUdict (`pronouncing`) so homophones (e.g. *to* / *two* / *too*) are accepted as correct.
- **Visual Feedback**:
  - Green: Correct
  - Yellow (dotted underline): Close match
  - Red (wavy underline): Wrong word
  - Red (dashed underline): Missing word
- **Audio Playback**: Listen to native sentence & word audio, plus replay your own recording.

---

## 1. Installation

### Prerequisites
- Python 3.10 – 3.13 recommended
- Microphone access in browser (via `http://localhost` or `https://`)

### Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
*(Or with `uv`: `uv venv --python 3.13 && uv pip install -r requirements.txt --python .venv/bin/python`)*

---

## 2. Importing an Anki Deck

Place your `.apkg` deck in the `decks/` folder (or anywhere in your project).

### Step 1: Inspect the Deck
Inspect the deck fields to confirm target and answer fields:
```bash
python tools/import_apkg.py "decks/1000 Basic English Words.apkg" data --inspect
```

### Step 2: Extract Cards and Media
Extract the deck notes to `data/cards.json` and audio files to `data/media/`:
```bash
python tools/import_apkg.py "decks/1000 Basic English Words.apkg" data
```

### Step 3: Configure Target Fields
Create or update `data/config.json` with the fields you want to use:
```json
{
  "target_field": "Word",
  "answer_field": "Definition"
}
```

---

## 3. Environment Variables

You can configure Whisper model size, hardware device, and quantization computation type:

| Variable | Default | Description / Options |
|---|---|---|
| `WHISPER_MODEL` | `small.en` | `tiny.en`, `base.en`, `small.en`, `medium.en`, `large-v3-turbo` |
| `WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `WHISPER_COMPUTE` | `int8` | `int8` (CPU), `float16` (NVIDIA GPU) |

Example:
```bash
export WHISPER_MODEL=base.en
export WHISPER_DEVICE=cpu
export WHISPER_COMPUTE=int8
```

---

## 4. Running the Web App

Start the FastAPI application with Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

Open your browser at:
```
http://localhost:8000
```

Interactive API documentation is also available at:
```
http://localhost:8000/docs
```

---

## 5. Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Toggle Record / Stop recording |
| `P` | Play reference card audio |
| `Left Arrow` | Previous card |
| `Right Arrow` | Next card |
| `R` | Random card |

---

## 6. Running Tests

Run the test suite using pytest:

```bash
pytest
```