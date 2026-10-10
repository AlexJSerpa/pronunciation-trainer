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
