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

try:
    import zstandard
except ImportError:
    zstandard = None

SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
TAG_RE = re.compile(r"<[^>]+>")
COLLECTION_PRIORITY = ["collection.anki21b", "collection.anki21", "collection.anki2"]


def clean(text: str) -> str:
    text = SOUND_RE.sub("", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def decompress_zstd(data: bytes) -> bytes:
    if zstandard is None:
        sys.exit(
            "The deck uses zstandard compression. Please install 'zstandard' (e.g. via pip install zstandard)."
        )
    d = zstandard.ZstdDecompressor()
    return d.decompress(data, max_output_size=100 * 1024 * 1024)


def parse_media_map(z: zipfile.ZipFile) -> dict[str, str]:
    """Parse media mapping from .apkg zip file (supporting both legacy JSON and modern protobuf format)."""
    try:
        raw = z.read("media")
    except KeyError:
        return {}

    # Legacy format: uncompressed JSON
    try:
        decoded = raw.decode("utf-8")
        return json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    # Modern format: zstd-compressed protobuf
    if raw.startswith(b"\x28\xb5\x2f\xfd"):
        decomp = decompress_zstd(raw)
        media_map = {}
        pos = 0
        idx = 0
        while pos < len(decomp):
            if decomp[pos] != 0x0A:
                break
            pos += 1
            length = 0
            shift = 0
            while True:
                b = decomp[pos]
                pos += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            sub = decomp[pos : pos + length]
            pos += length

            sub_pos = 0
            name = None
            while sub_pos < len(sub):
                tag = sub[sub_pos]
                sub_pos += 1
                field_num = tag >> 3
                wire_type = tag & 0x07
                if field_num == 1 and wire_type == 2:
                    slen = sub[sub_pos]
                    sub_pos += 1
                    name = sub[sub_pos : sub_pos + slen].decode("utf-8", errors="replace")
                    sub_pos += slen
                elif wire_type == 0:
                    while sub[sub_pos] & 0x80:
                        sub_pos += 1
                    sub_pos += 1
                elif wire_type == 2:
                    slen = sub[sub_pos]
                    sub_pos += 1
                    sub_pos += slen
                else:
                    break
            if name:
                media_map[str(idx)] = name
            idx += 1
        return media_map

    sys.exit("Could not parse the 'media' file in the deck.")


def get_collection_sqlite_bytes(z: zipfile.ZipFile) -> bytes:
    names = set(z.namelist())
    coll = next((n for n in COLLECTION_PRIORITY if n in names), None)
    if coll is None:
        sys.exit("No collection file found inside the .apkg.")

    data = z.read(coll)
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        return decompress_zstd(data)
    return data


def parse_models(con: sqlite3.Connection) -> dict[int, dict]:
    models = {}
    col_row = con.execute("SELECT models FROM col").fetchone()
    col_models = col_row[0] if col_row else ""
    if col_models:
        try:
            m_json = json.loads(col_models)
            for mid, m in m_json.items():
                field_names = [f["name"] for f in sorted(m["flds"], key=lambda f: f["ord"])]
                models[int(mid)] = {"name": m["name"], "fields": field_names}
            return models
        except json.JSONDecodeError:
            pass

    # Newer schema: 'notetypes' and 'fields' tables
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "notetypes" in tables and "fields" in tables:
        nt_rows = con.execute("SELECT id, name FROM notetypes").fetchall()
        for ntid, name in nt_rows:
            fld_rows = con.execute(
                "SELECT ord, name FROM fields WHERE ntid = ? ORDER BY ord", (ntid,)
            ).fetchall()
            models[ntid] = {"name": name, "fields": [r[1] for r in fld_rows]}
        return models

    return models


def read_media_file(z: zipfile.ZipFile, key: str) -> bytes:
    data = z.read(key)
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        return decompress_zstd(data)
    return data


def main(apkg: str, out_dir: str, inspect_only: bool = False) -> None:
    out = Path(out_dir)
    with zipfile.ZipFile(apkg) as z:
        names = set(z.namelist())
        print("Zip contains:", sorted(n for n in names if not n.isdigit())[:20])

        db_bytes = get_collection_sqlite_bytes(z)
        media_map = parse_media_map(z)

        cards = []
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "col.sqlite"
            db_file.write_bytes(db_bytes)
            con = sqlite3.connect(db_file)
            models = parse_models(con)

            for nid, mid, flds, tags in con.execute(
                "SELECT id, mid, flds, tags FROM notes ORDER BY id"
            ):
                model = models.get(mid, {"name": "Unknown", "fields": []})
                field_names = model["fields"]
                values = flds.split("\x1f")
                if len(field_names) < len(values):
                    field_names = field_names + [f"Field_{i}" for i in range(len(field_names), len(values))]
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
        extracted_count = 0
        for key, name in media_map.items():
            if name in needed:
                content = read_media_file(z, key)
                (media_dir / name).write_bytes(content)
                extracted_count += 1

    out.mkdir(parents=True, exist_ok=True)
    (out / "cards.json").write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out / 'cards.json'} and {extracted_count} audio files.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("Usage: python tools/import_apkg.py <deck.apkg> <out_dir> [--inspect]")
        sys.exit(1)
    main(args[0], args[1], "--inspect" in sys.argv)
