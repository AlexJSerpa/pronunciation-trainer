---
name: english-pronunciation-trainer
description: Build a local web app that imports an Anki .apkg deck (words, answers, audio), lets the user record themselves speaking, transcribes it with a local Whisper model, compares the transcript with the target text, and shows the words that do not match in red. Use when implementing or extending this project.
---

# English Pronunciation Trainer: Implementation Spec

## 0. Rules for the implementing model (read first)

1. Work **phase by phase** (section 5). Finish and test one phase before starting the next.
2. Everything runs **locally**. Do not add cloud APIs.
3. **Never guess the deck's field names.** Run the inspect step in Phase 1, show the output to the user, and ask which field is the target text and which is the answer.
4. Keep it simple: Python + FastAPI backend, plain HTML/JS frontend, **no build step**.
5. Write and run the tests listed in each phase.
6. If this document disagrees with the real files you see, trust the real files and tell the user.
7. Pin dependency versions in `requirements.txt` only after checking the latest stable versions on PyPI.

## 1. Goal

1. Import `1000 Basic English Words.apkg`: text fields, answers, and audio files.
2. In the web app, show a card, play its audio, and let the user record their voice.
3. Transcribe the recording locally with Whisper.
4. Compare what the user **should** say with what Whisper **heard**.
5. Show the target sentence with each word coloured: green = OK, yellow = close, **red = wrong or missing**.

## 2. Skills this project needs

| Skill | Used for |
|---|---|
| Reading zip + SQLite files | Parsing the `.apkg` |
| FastAPI file upload | Receiving the recorded audio |
| faster-whisper usage | Local speech-to-text with word timestamps |
| Text normalization + sequence alignment | Comparing target vs heard words |
| Browser audio capture (MediaRecorder) | Recording the microphone |
| Basic DOM rendering + CSS | Coloured words |

## 3. Recommended stack and why

| Part | Choice | Why |
|---|---|---|
| Deck import | Python standard library (`zipfile`, `sqlite3`, `json`) | An `.apkg` is just a zip containing a SQLite database and media files. No extra dependency. |
| Backend | **FastAPI** + uvicorn | Small, easy file upload, automatic docs at `/docs`. |
| Speech-to-text | **faster-whisper** | Runs Whisper through CTranslate2: faster and lighter than the original `openai-whisper`, supports int8 on CPU, and gives word timestamps and per-word probability. |
| Whisper model | `small.en` (default), `base.en` (weak PC), `large-v3-turbo` (NVIDIA GPU) | English-only models are faster and more accurate for English. Set with env vars. |
| Frontend | HTML + vanilla JS | `MediaRecorder` and `fetch` are enough. Nothing to build or install. |
| Comparison | `difflib` + optional `pronouncing` (CMUdict) | `difflib` aligns two word lists. CMUdict lets us accept homophones (to/two/too) as equal. |
| Storage | `cards.json` + `media/` folder | Only ~1000 cards. No database needed yet. |
| Tests | pytest | Simple and standard. |

Environment variables for the model:

```
WHISPER_MODEL=small.en     # or base.en / large-v3-turbo
WHISPER_DEVICE=auto        # auto | cpu | cuda
WHISPER_COMPUTE=int8       # CPU: int8   |   NVIDIA GPU: float16
```

## 4. Honest limitation (tell the user)

Whisper is a language model. It tends to **guess the most likely word** even when the pronunciation is imperfect, so it is forgiving. This means:

- **Red = Whisper could not recognise that word.** This measures *intelligibility*, not a precise phoneme-level pronunciation score. It is a good MVP.
- Homophones cannot be told apart by sound (to/two/too, there/their), so they must be accepted as equal.
- On a very short recording (one word) or silence, Whisper can hallucinate text such as "Thank you.". Use `vad_filter=True`, reject recordings shorter than ~0.3 s, and ignore results with no words.
- **Do not** pass the target sentence as `initial_prompt`. That biases Whisper toward the correct text and hides the user's mistakes.
- For real pronunciation scoring, see Phase 5 (phoneme-level).

## 5. Architecture

```
.apkg ──import_apkg.py──▶ data/cards.json + data/media/*.mp3
                                   │
Browser ──GET /api/cards──────────▶│
Browser ──plays /media/xxx.mp3     │
Browser ──mic (MediaRecorder)──▶ POST /api/check (card_id + audio)
                                   │  faster-whisper → words + probabilities
                                   │  compare(target, heard)
Browser ◀── JSON: words[{word,status,heard}], extras, score
```

## 6. Project layout

```
pronunciation-trainer/
  data/                 # generated: cards.json, config.json, media/
  decks/                # put the .apkg here
  tools/import_apkg.py
  app/__init__.py
  app/main.py
  app/asr.py
  app/compare.py
  app/static/index.html
  app/static/app.js
  app/static/style.css
  tests/test_compare.py
  tests/test_import.py
  requirements.txt
```

`requirements.txt` (add versions after checking PyPI):

```
fastapi
uvicorn[standard]
python-multipart
faster-whisper
pronouncing
pytest
```

Run with: `uvicorn app.main:app --reload` from the project root.

## 7. Phases

### Phase 1: Import the Anki deck

Facts about the `.apkg` format:

- It is a zip file. Inside: a SQLite database, a `media` file, and media files named `0`, `1`, `2`, ...
- The `media` file is JSON mapping number → real filename, e.g. `{"0": "hello.mp3"}`.
- In the database, table `notes` has a `flds` column: all fields joined by the character `\x1f`. Field names are in the JSON column `col.models`.
- Audio appears inside fields as `[sound:filename.mp3]`.
- Database file priority: `collection.anki21b` > `collection.anki21` > `collection.anki2`.
- **Newer Anki exports** (`collection.anki21b`, compressed with zstd) are harder to read. The simple fix: in Anki desktop, export the deck again with **"Support older Anki versions" ticked**. The script below stops with a clear message in that case.

`tools/import_apkg.py`:

```python
"""Usage:
  python tools/import_apkg.py decks/deck.apkg data --inspect   # print first cards only
  python tools/import_apkg.py decks/deck.apkg data             # write cards.json + media/
"""
import html
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
TAG_RE = re.compile(r"<[^>]+>")
COLLECTION_PRIORITY = ["collection.anki21b", "collection.anki21", "collection.anki2"]


def clean(text: str) -> str:
    text = SOUND_RE.sub("", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def main(apkg: str, out_dir: str, inspect_only: bool = False) -> None:
    out = Path(out_dir)
    with zipfile.ZipFile(apkg) as z:
        names = set(z.namelist())
        print("Zip contains:", sorted(n for n in names if not n.isdigit())[:20])

        coll = next((n for n in COLLECTION_PRIORITY if n in names), None)
        if coll is None:
            sys.exit("No collection file found inside the .apkg.")
        if coll.endswith("anki21b"):
            sys.exit(
                "This deck uses Anki's new compressed format. Re-export it from Anki "
                "desktop with 'Support older Anki versions' ticked, then run again."
            )
        try:
            media_map = json.loads(z.read("media"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            sys.exit("Could not read the 'media' file as JSON. Re-export with legacy support.")

        cards = []
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "col.sqlite"
            db_file.write_bytes(z.read(coll))
            con = sqlite3.connect(db_file)
            models = json.loads(con.execute("SELECT models FROM col").fetchone()[0])
            for nid, mid, flds, tags in con.execute(
                "SELECT id, mid, flds, tags FROM notes ORDER BY id"
            ):
                model = models[str(mid)]
                field_names = [f["name"] for f in sorted(model["flds"], key=lambda f: f["ord"])]
                values = flds.split("\x1f")
                audio = [a for v in values for a in SOUND_RE.findall(v)]
                cards.append({
                    "id": nid,
                    "note_type": model["name"],
                    "fields": {k: clean(v) for k, v in zip(field_names, values)},
                    "audio": audio,
                    "tags": tags.strip(),
                })
            con.close()

        print(f"Found {len(cards)} notes.")
        if inspect_only:
            print(json.dumps(cards[:3], indent=2, ensure_ascii=False))
            return

        media_dir = out / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        needed = {a for c in cards for a in c["audio"]}
        for key, name in media_map.items():
            if name in needed:
                (media_dir / name).write_bytes(z.read(key))

    (out / "cards.json").write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out/'cards.json'} and {len(needed)} audio files.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1], "--inspect" in sys.argv)
```

**Then ask the user** which field is the text to say, and create `data/config.json`:

```json
{ "target_field": "Front", "answer_field": "Back" }
```

(Replace `Front`/`Back` with the real field names printed by `--inspect`.)

**Done when:** `cards.json` has about 1000 cards, every filename in `audio` exists in `data/media/`, and the user confirmed the field names.

### Phase 2: Backend and speech-to-text

`app/asr.py`:

```python
import os
from faster_whisper import WhisperModel

_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            os.getenv("WHISPER_MODEL", "small.en"),
            device=os.getenv("WHISPER_DEVICE", "auto"),
            compute_type=os.getenv("WHISPER_COMPUTE", "int8"),
        )
    return _model


def transcribe(path: str) -> dict:
    segments, _info = get_model().transcribe(
        path,
        language="en",
        beam_size=5,
        temperature=0.0,                  # deterministic, fewer creative guesses
        word_timestamps=True,
        vad_filter=True,                  # ignore silence
        condition_on_previous_text=False,
        # NO initial_prompt with the target text (it hides mistakes)
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({
                "word": w.word.strip(),
                "start": round(w.start, 2),
                "end": round(w.end, 2),
                "prob": round(w.probability, 3),
            })
    return {"text": " ".join(w["word"] for w in words), "words": words}
```

`app/main.py`:

```python
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from app import asr, compare

DATA = Path("data")
cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
CARDS = {c["id"]: c for c in cards}

app = FastAPI()


@app.get("/api/cards")
def list_cards():
    return [
        {"id": c["id"],
         "text": c["fields"].get(config["target_field"], ""),
         "answer": c["fields"].get(config.get("answer_field", ""), ""),
         "audio": c["audio"][:1]}
        for c in cards
    ]


# Use plain `def` (not `async def`) so the blocking Whisper call does not freeze the server.
@app.post("/api/check")
def check(card_id: int = Form(...), audio: UploadFile = File(...)):
    card = CARDS.get(card_id)
    if card is None:
        raise HTTPException(404, "Unknown card")
    target = card["fields"][config["target_field"]]

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio.file.read())
        path = f.name
    try:
        heard = asr.transcribe(path)
    finally:
        os.unlink(path)

    if not heard["words"]:
        raise HTTPException(422, "No speech detected. Try again.")
    result = compare.compare(target, heard["text"])
    result["whisper"] = heard
    return result


# Mount static files LAST so the API routes above take priority.
app.mount("/media", StaticFiles(directory=DATA / "media"), name="media")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
```

**Done when:** `uvicorn app.main:app` starts, `/docs` shows the endpoints, and a test `.webm`/`.wav` posted to `/api/check` returns JSON. (faster-whisper decodes audio itself, so system ffmpeg is usually not required.)

### Phase 3: Comparison logic

Normalise both texts, align the word lists, and label each **target** word.

`app/compare.py`:

```python
import difflib
import re

try:
    import pronouncing  # CMU dictionary; optional but recommended
except ImportError:
    pronouncing = None

CLOSE_THRESHOLD = 0.75


def normalize(text: str) -> list[str]:
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return text.split()


def same_sound(a: str, b: str) -> bool:
    """True if two words share at least one pronunciation (homophones)."""
    if pronouncing is None:
        return False
    return bool(set(pronouncing.phones_for_word(a)) & set(pronouncing.phones_for_word(b)))


def _item(word, status, heard):
    return {"word": word, "status": status, "heard": heard}


def _judge(target_word: str, heard_word: str) -> dict:
    if target_word == heard_word or same_sound(target_word, heard_word):
        return _item(target_word, "correct", heard_word)
    ratio = difflib.SequenceMatcher(None, target_word, heard_word).ratio()
    status = "close" if ratio >= CLOSE_THRESHOLD else "wrong"
    return _item(target_word, status, heard_word)


def compare(target: str, heard: str) -> dict:
    t, h = normalize(target), normalize(heard)
    sm = difflib.SequenceMatcher(a=t, b=h, autojunk=False)
    out = [None] * len(t)
    extras = []  # words the user said that are not in the target

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = _item(t[i1 + k], "correct", h[j1 + k])
        elif tag == "delete":
            for i in range(i1, i2):
                out[i] = _item(t[i], "missing", None)
        elif tag == "insert":
            extras.extend(h[j1:j2])
        else:  # replace
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                out[i1 + k] = _judge(t[i1 + k], h[j1 + k])
            for i in range(i1 + n, i2):
                out[i] = _item(t[i], "missing", None)
            extras.extend(h[j1 + n:j2])

    correct = sum(1 for w in out if w["status"] == "correct")
    return {
        "words": out,
        "extras": extras,
        "heard": " ".join(h),
        "score": round(correct / len(t), 3) if t else 0.0,
    }
```

Status meanings: `correct` (green), `close` (yellow), `wrong` and `missing` (**red**).

`tests/test_compare.py`:

```python
import pytest
from app.compare import compare


def statuses(r):
    return [w["status"] for w in r["words"]]


def test_exact_match_ignores_case_and_punctuation():
    assert statuses(compare("I have a red car", "I have a red car.")) == ["correct"] * 5


def test_wrong_word():
    assert statuses(compare("I have a red car", "I have a bed car"))[3] == "wrong"


def test_missing_words():
    r = compare("I have a red car", "I have car")
    assert statuses(r) == ["correct", "correct", "missing", "missing", "correct"]


def test_extra_words_are_reported():
    assert compare("red car", "the red car")["extras"] == ["the"]


def test_close_word():
    assert statuses(compare("beautiful", "beutiful")) == ["close"]


def test_homophone_is_accepted():
    pytest.importorskip("pronouncing")
    assert statuses(compare("two", "to")) == ["correct"]
```

**Done when:** all tests pass.

### Phase 4: Frontend

Files: `app/static/index.html`, `app.js`, `style.css`.

UI requirements:

- Card selector (previous / next / random) showing the target text.
- "Play" button for the Anki audio: `new Audio("/media/" + card.audio[0]).play()`.
- "Record" / "Stop" button, then a loading state while the server works.
- Result area: the target words, each in a `<span class="w-STATUS">`, plus the "heard" text and the score.
- Do not rely on colour alone (accessibility): add underline styles.

Recording and sending:

```js
let recorder, chunks = [];

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder = new MediaRecorder(stream);
  chunks = [];
  recorder.ondataavailable = e => chunks.push(e.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType });
    const fd = new FormData();
    fd.append("card_id", currentCard.id);
    fd.append("audio", blob, "recording.webm");
    const res = await fetch("/api/check", { method: "POST", body: fd });
    if (!res.ok) { showError((await res.json()).detail); return; }
    render(await res.json());
  };
  recorder.start();
}
const stopRecording = () => recorder && recorder.stop();

function render(result) {
  const box = document.getElementById("result");
  box.replaceChildren();
  for (const w of result.words) {
    const span = document.createElement("span");
    span.textContent = w.word + " ";
    span.className = "w-" + w.status;           // correct | close | wrong | missing
    if (w.heard) span.title = "heard: " + w.heard;
    box.appendChild(span);
  }
  // also show result.heard, result.extras and Math.round(result.score * 100) + "%"
}
```

`style.css` (minimum):

```css
.w-correct { color: #1a7f37; }
.w-close   { color: #9a6700; text-decoration: underline dotted; }
.w-wrong   { color: #d1242f; text-decoration: underline wavy; }
.w-missing { color: #d1242f; text-decoration: underline dashed; }
```

Gotchas:

- `getUserMedia` only works on `https://` or `http://localhost`. Opening the app from a phone over the local network needs HTTPS.
- Chrome/Firefox record `webm/opus`; Safari records `mp4`. Both are decoded by faster-whisper, so keep the file suffix generic.

**Done when:** the user can pick a card, hear the audio, record, and see red/yellow/green words.

### Phase 5: Optional improvements (ask the user before starting)

1. **Real pronunciation scoring (phoneme level).** Use a phoneme-recognition model such as `facebook/wav2vec2-xlsr-53-espeak-cv-ft` through the `transformers` library, and compare the recognised phonemes with the expected phonemes from `phonemizer` + `espeak-ng` (use the same phoneme set on both sides). This catches accent mistakes that Whisper forgives. It is harder, so keep it as a second score next to the Whisper one.
2. **Use Whisper word probability.** If a word is "correct" but `prob < 0.5`, show it as "unsure" (yellow).
3. **Numbers:** Whisper may write "3" for "three". Convert digits to words with `num2words` before comparing.
4. **Keep original punctuation and casing** when displaying the target words.
5. **Progress tracking:** store attempts in SQLite and add simple spaced repetition (repeat the red words more often).
6. **Slow playback** of the Anki audio and a "replay my recording" button.
7. **Packaging as an app:** make it a PWA, or wrap it with Tauri/Electron.

## 8. Final acceptance checklist

- [ ] `cards.json` and `media/` generated from the real deck; field names confirmed by the user
- [ ] `/api/check` returns word statuses for a real recording
- [ ] `pytest` passes
- [ ] Wrong and missing words appear in red in the browser
- [ ] Silence or an empty recording shows a friendly message instead of a crash
- [ ] README explains: install, import command, env vars, run command
