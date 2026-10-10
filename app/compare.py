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
