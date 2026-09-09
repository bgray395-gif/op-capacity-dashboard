import json
from datetime import datetime
from pathlib import Path
from .db import SessionLocal, CapacityPoint

def seed_if_empty():
    db=SessionLocal()
    try:
        if db.query(CapacityPoint).count(): return
        p=Path("data/seed_snapshot.json")
        if not p.exists(): return
        rows=json.loads(p.read_text())
        for r in rows:
            r["gas_day"]=datetime.fromisoformat(r["gas_day"]).date()
            r["retrieved_at"]=datetime.fromisoformat(r["retrieved_at"])
            db.add(CapacityPoint(**r))
        db.commit()
    finally: db.close()
