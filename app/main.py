import asyncio, yaml
from datetime import datetime, timezone, date
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func
from .db import SessionLocal, CapacityPoint, RefreshRun
from .collectors import collect_pipeline
from .seed import seed_if_empty

CFG=yaml.safe_load(Path("config.yaml").read_text())
app=FastAPI(title="Daily Operational Capacity")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates=Jinja2Templates(directory="app/templates")
scheduler=AsyncIOScheduler(timezone=CFG["timezone"])

def fmt(v):
    if v is None: return "—"
    return f"{v:,.0f}"
templates.env.filters["num"]=fmt

def point_key(r):
    return (r.pipeline, r.section, r.point_id or "", r.point_name or "", r.direction or "")

def group_for(section, point_id):
    for g in CFG.get("display_groups", []):
        if g["section"]==section and (point_id or "") in g.get("points", []): return g
    return None

def build_sections(rows, prior_rows):
    prior_map={point_key(r):r for r in prior_rows}
    by_section={}
    for r in rows: by_section.setdefault(r.section,[]).append(r)
    result={}
    for section, srows in by_section.items():
        srows=sorted(srows,key=lambda r:(r.pipeline,r.point_name or "",r.direction or ""))
        view=[]; handled=set(); total_op=total_sched=total_open=total_prior_open=0.0
        has_op=has_sched=has_open=has_prior=False
        mixed=len({r.pipeline for r in srows})>1
        for r in srows:
            g=group_for(section,r.point_id)
            if g:
                gid=(section,g["label"])
                members=[x for x in srows if (x.point_id or "") in g["points"]]
                if gid not in handled:
                    cur_op=max([x.operating_capacity for x in members if x.operating_capacity is not None] or [None])
                    cur_sched=sum(x.scheduled or 0 for x in members)
                    cur_open=(cur_op-cur_sched) if cur_op is not None else None
                    pm=[prior_map.get(point_key(x)) for x in members]
                    prev_op=max([x.operating_capacity for x in pm if x is not None and x.operating_capacity is not None] or [None])
                    prev_sched=sum((x.scheduled or 0) for x in pm if x is not None)
                    prev_open=(prev_op-prev_sched) if prev_op is not None and pm else None
                    delta=(cur_open-prev_open) if cur_open is not None and prev_open is not None else None
                    first=True
                    for m in members:
                        view.append({"r":m,"prior":prior_map.get(point_key(m)),"group":g,"group_first":first,"rowspan":len(members),"display_op":cur_op if first else None,"display_open":cur_open if first else None,"prior_open":prev_open if first else None,"delta_open":delta if first else None})
                        first=False
                    handled.add(gid)
                    if cur_op is not None: total_op+=cur_op; has_op=True
                    total_sched+=cur_sched; has_sched=True
                    if cur_open is not None: total_open+=cur_open; has_open=True
                    if prev_open is not None: total_prior_open+=prev_open; has_prior=True
                continue
            p=prior_map.get(point_key(r)); prev_open=p.available if p else None
            delta=(r.available-prev_open) if r.available is not None and prev_open is not None else None
            view.append({"r":r,"prior":p,"group":None,"group_first":False,"rowspan":1,"display_op":r.operating_capacity,"display_open":r.available,"prior_open":prev_open,"delta_open":delta})
            if r.operating_capacity is not None: total_op+=r.operating_capacity; has_op=True
            if r.scheduled is not None: total_sched+=r.scheduled; has_sched=True
            if r.available is not None: total_open+=r.available; has_open=True
            if prev_open is not None: total_prior_open+=prev_open; has_prior=True
        total_delta=(total_open-total_prior_open) if has_open and has_prior else None
        result[section]={"rows":view,"mixed_pipeline":mixed,"total_op":total_op if has_op else None,"total_sched":total_sched if has_sched else None,"total_open":total_open if has_open else None,"total_prior_open":total_prior_open if has_prior else None,"total_delta":total_delta}
    return result

async def refresh_all():
    db=SessionLocal(); run=RefreshRun(started_at=datetime.now(timezone.utc),status="running"); db.add(run); db.commit(); db.refresh(run)
    inserted=0; failures=[]
    try:
        for p in CFG["pipelines"]:
            rows=await collect_pipeline(p)
            if not rows:
                failures.append(p["key"]); continue
            for r in rows:
                gd=r.get("gas_day")
                if not gd: continue
                obj=CapacityPoint(
                    pipeline=p["key"], section=r["section"], gas_day=gd, cycle=r.get("cycle") or "TIMELY",
                    point_id=r.get("point_id"), point_name=r.get("point_name"), direction=r.get("direction"),
                    operating_capacity=r.get("operating_capacity"), scheduled=r.get("scheduled"), available=r.get("available"),
                    primary_scheduled=r.get("primary_scheduled"), secondary_prime=r.get("secondary_prime"),
                    secondary_scheduled=r.get("secondary_scheduled"), interruptible_scheduled=r.get("interruptible_scheduled"),
                    source_url=p["source_url"], retrieved_at=datetime.now(timezone.utc), source_status="live")
                exists=db.query(CapacityPoint).filter_by(pipeline=obj.pipeline,section=obj.section,gas_day=obj.gas_day,cycle=obj.cycle,point_id=obj.point_id,point_name=obj.point_name,direction=obj.direction).first()
                if exists:
                    for k in ["operating_capacity","scheduled","available","primary_scheduled","secondary_prime","secondary_scheduled","interruptible_scheduled","retrieved_at","source_status"]: setattr(exists,k,getattr(obj,k))
                else: db.add(obj); inserted+=1
            db.commit()
        run.status="partial" if failures else "success"
        run.message=f"Inserted {inserted} rows." + (f" No data returned for: {', '.join(failures)}." if failures else "")
    except Exception as e:
        db.rollback(); run.status="error"; run.message=str(e)
    finally:
        run.finished_at=datetime.now(timezone.utc); db.add(run); db.commit(); db.close()

@app.on_event("startup")
async def startup():
    seed_if_empty()
    if not scheduler.running:
        scheduler.add_job(refresh_all, CronTrigger(hour=CFG["refresh_hour"], minute=CFG["refresh_minute"], timezone=CFG["timezone"]), id="daily_refresh", replace_existing=True)
        scheduler.start()

@app.get("/", response_class=HTMLResponse)
def dashboard(request:Request, target_date:str|None=None):
    db=SessionLocal()
    latest_day=db.query(func.max(CapacityPoint.gas_day)).scalar()
    selected=latest_day
    if target_date:
        try: selected=date.fromisoformat(target_date)
        except ValueError: selected=latest_day
    rows=db.query(CapacityPoint).filter(CapacityPoint.gas_day==selected).all() if selected else []
    previous_day=db.query(func.max(CapacityPoint.gas_day)).filter(CapacityPoint.gas_day < selected).scalar() if selected else None
    prior_rows=db.query(CapacityPoint).filter(CapacityPoint.gas_day==previous_day).all() if previous_day else []
    sections=build_sections(rows,prior_rows)
    last_run=db.query(RefreshRun).order_by(RefreshRun.id.desc()).first()
    min_day=db.query(func.min(CapacityPoint.gas_day)).scalar(); max_day=latest_day
    db.close()
    return templates.TemplateResponse("dashboard.html", {"request":request,"sections":sections,"selected_day":selected,"latest_day":latest_day,"previous_day":previous_day,"last_run":last_run,"min_day":min_day,"max_day":max_day})

@app.get("/history", response_class=HTMLResponse)
def history(request:Request, point_id:str|None=None, point_name:str|None=None):
    db=SessionLocal(); q=db.query(CapacityPoint)
    if point_id: q=q.filter(CapacityPoint.point_id==point_id)
    if point_name: q=q.filter(CapacityPoint.point_name==point_name)
    rows=q.order_by(CapacityPoint.gas_day.desc()).limit(120).all(); db.close()
    return templates.TemplateResponse("history.html", {"request":request,"rows":rows,"point_id":point_id,"point_name":point_name})

@app.post("/admin/refresh")
async def admin_refresh(background_tasks:BackgroundTasks):
    background_tasks.add_task(refresh_all)
    return RedirectResponse(url="/",status_code=303)

@app.get("/health")
def health(): return {"ok":True,"schedule":"06:00 America/New_York"}
