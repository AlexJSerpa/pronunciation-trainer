import json
from pathlib import Path
from tools.import_apkg import clean


def test_clean_removes_sound_and_html():
    raw = '<span style="color: red;">Hello</span> [sound:test.mp3] &amp; world!'
    assert clean(raw) == "Hello & world!"


def test_cards_json_structure():
    cards_path = Path("data/cards.json")
    if not cards_path.exists():
        return
    data = json.loads(cards_path.read_text(encoding="utf-8"))
    assert len(data) > 0
    first = data[0]
    assert "id" in first
    assert "fields" in first
    assert "audio" in first
    assert isinstance(first["audio"], list)
