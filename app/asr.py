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
                "start": round(float(w.start), 2),
                "end": round(float(w.end), 2),
                "prob": round(float(w.probability), 3),
            })
    return {"text": " ".join(w["word"] for w in words), "words": words}
