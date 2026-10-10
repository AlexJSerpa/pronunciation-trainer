import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from app import asr, compare

DATA = Path("data")

cards = []
config = {"target_field": "Word", "answer_field": "Definition"}
CARDS = {}

if (DATA / "cards.json").exists():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    CARDS = {c["id"]: c for c in cards}

if (DATA / "config.json").exists():
    config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))

app = FastAPI(title="Pronunciation Trainer")


@app.get("/api/cards")
def list_cards():
    result = []
    for c in cards:
        f = c.get("fields", {})
        audios = c.get("audio", [])
        word_audio = audios[0] if len(audios) > 0 else None
        example_audio = audios[1] if len(audios) > 1 else word_audio

        result.append({
            "id": c["id"],
            "word": f.get("Word", ""),
            "definition": f.get("Definition", ""),
            "example": f.get("Example", ""),
            "example_cloze": f.get("Example Cloze", ""),
            "transcription": f.get("Transcription", ""),
            "part_of_speech": f.get("Part of Speech", ""),
            "text": f.get(config["target_field"], ""),
            "answer": f.get(config.get("answer_field", ""), ""),
            "word_audio": word_audio,
            "example_audio": example_audio,
            "audio": audios,
        })
    return result


# Use plain `def` (not `async def`) so the blocking Whisper call does not freeze the server.
@app.post("/api/check")
def check(
    card_id: int = Form(...),
    audio: UploadFile = File(...),
    target_text: str = Form(None),
):
    card = CARDS.get(card_id)
    if card is None:
        raise HTTPException(404, "Unknown card")
    target = target_text.strip() if target_text and target_text.strip() else card["fields"].get(config["target_field"], "")


    content = audio.file.read()
    if not content or len(content) < 100:
        raise HTTPException(422, "No speech detected. Audio recording is too short or empty.")

    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        path = f.name
    try:
        heard = asr.transcribe(path)
    except Exception as exc:
        raise HTTPException(500, f"Speech recognition failed: {exc}") from exc
    finally:
        if os.path.exists(path):
            os.unlink(path)

    if not heard.get("words"):
        raise HTTPException(422, "No speech detected. Try again.")
    result = compare.compare(target, heard["text"])
    result["whisper"] = heard
    return result


# Mount static files LAST so the API routes above take priority.
media_path = DATA / "media"
media_path.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_path), name="media")

static_path = Path("app/static")
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
