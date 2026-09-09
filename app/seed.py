import base64
import gzip
import json
from datetime import datetime
from pathlib import Path
from .db import SessionLocal, CapacityPoint


def _load_seed_rows():
    json_path = Path("data/seed_snapshot.json")
    if json_path.exists():
        return json.loads(json_path.read_text())

    packed_path = Path("data/seed_snapshot.json.gz.b64")
    if packed_path.exists():
        packed = base64.b64decode(packed_path.read_text().strip())
        return json.loads(gzip.decompress(packed).decode("utf-8"))

    return []


def seed_if_empty():
    db = SessionLocal()
    try:
        if db.query(CapacityPoint).count():
            return
        rows = _load_seed_rows()
        for r in rows:
            r["gas_day"] = datetime.fromisoformat(r["gas_day"]).date()
            r["retrieved_at"] = datetime.fromisoformat(r["retrieved_at"])
            db.add(CapacityPoint(**r))
        db.commit()
        print(f"Seeded {len(rows)} capacity rows.", flush=True)
    finally:
        db.close()
