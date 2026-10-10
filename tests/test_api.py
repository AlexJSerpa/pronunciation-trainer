from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_cards():
    response = client.get("/api/cards")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    first = data[0]
    assert "id" in first
    assert "text" in first
    assert "answer" in first
    assert "audio" in first
    assert first["text"] == "cry"


def test_check_valid_audio():
    sample_audio = Path("data/media/1000BEW_B01_U01_001.word.mp3")
    if not sample_audio.exists():
        return

    with open(sample_audio, "rb") as f:
        response = client.post(
            "/api/check",
            data={"card_id": 1556033745938},
            files={"audio": ("sample.mp3", f, "audio/mpeg")},
        )
    assert response.status_code == 200
    res = response.json()
    assert "words" in res
    assert "score" in res
    assert "heard" in res
    assert "whisper" in res
    assert res["words"][0]["word"] == "cry"
    assert res["words"][0]["status"] == "correct"


def test_check_sentence_audio():
    sample_sentence_audio = Path("data/media/1000BEW_B01_U01_001.example.mp3")
    if not sample_sentence_audio.exists():
        return

    with open(sample_sentence_audio, "rb") as f:
        response = client.post(
            "/api/check",
            data={
                "card_id": 1556033745938,
                "target_text": "He cries when he is sad.",
            },
            files={"audio": ("sample_sentence.mp3", f, "audio/mpeg")},
        )
    assert response.status_code == 200
    res = response.json()
    assert "words" in res
    assert "score" in res
    assert res["score"] > 0.8



def test_check_unknown_card():
    response = client.post(
        "/api/check",
        data={"card_id": 999999999999},
        files={"audio": ("empty.webm", b"dummy content dummy content", "audio/webm")},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown card"


def test_check_empty_audio():
    response = client.post(
        "/api/check",
        data={"card_id": 1556033745938},
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )
    assert response.status_code == 422
    assert "No speech detected" in response.json()["detail"]


def test_static_routes():
    index_res = client.get("/")
    assert index_res.status_code == 200
    assert "Pronunciation Trainer" in index_res.text

    js_res = client.get("/app.js")
    assert js_res.status_code == 200

    css_res = client.get("/style.css")
    assert css_res.status_code == 200


def test_media_route():
    media_res = client.get("/media/1000BEW_B01_U01_001.word.mp3")
    assert media_res.status_code == 200

