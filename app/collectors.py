import io, re
from datetime import date
from urllib.parse import urljoin
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from .normalize import rows_from_table

UA={"User-Agent":"Mozilla/5.0 (compatible; OpCapacityDashboard/1.0)"}

def tables_from_html(html):
    try: return pd.read_html(io.StringIO(html))
    except Exception: return []

def rows_from_html(html):
    rows=[]
    for t in tables_from_html(html): rows.extend(rows_from_table(t))
    return rows

def choose_latest_timely(rows):
    timely=[r for r in rows if "TIM" in (r.get("cycle") or "TIMELY").upper()]
    rows=timely or rows
    dated=[r for r in rows if r.get("gas_day")]
    if dated:
        latest=max(r["gas_day"] for r in dated)
        rows=[r for r in rows if r.get("gas_day")==latest]
    return rows

async def direct_collect(url):
    async with httpx.AsyncClient(headers=UA, follow_redirects=True, timeout=35) as c:
        r=await c.get(url)
        r.raise_for_status()
        rows=rows_from_html(r.text)
        if rows: return choose_latest_timely(rows)
        soup=BeautifulSoup(r.text,"html.parser")
        links=[]
        for a in soup.find_all("a", href=True):
            txt=(a.get_text(" ",strip=True)+" "+a["href"]).lower()
            if any(k in txt for k in ["operationally available","operationally-available","oac","capacity"]):
                links.append(urljoin(str(r.url),a["href"]))
        for link in links[:8]:
            try:
                rr=await c.get(link)
                rows=rows_from_html(rr.text)
                if rows: return choose_latest_timely(rows)
                if any(x in rr.headers.get("content-type","").lower() for x in ["csv","excel","spreadsheet"]):
                    try:
                        df=pd.read_csv(io.BytesIO(rr.content))
                    except Exception:
                        df=pd.read_excel(io.BytesIO(rr.content))
                    rows=rows_from_table(df)
                    if rows: return choose_latest_timely(rows)
            except Exception:
                pass
    return []

async def browser_collect(url):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        ctx=await browser.new_context(user_agent=UA["User-Agent"], accept_downloads=True)
        page=await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        rows=rows_from_html(await page.content())
        if rows:
            await browser.close(); return choose_latest_timely(rows)
        for pat in [r"Operationally Available Capacity", r"Operationally Available", r"Available Capacity"]:
            try:
                loc=page.get_by_text(re.compile(pat,re.I)).first
                if await loc.count():
                    await loc.click(timeout=8000)
                    await page.wait_for_timeout(2500)
                    rows=rows_from_html(await page.content())
                    if rows:
                        await browser.close(); return choose_latest_timely(rows)
            except Exception:
                pass
        for a in await page.locator("a").all():
            try:
                txt=((await a.inner_text()) or "").lower()
                href=await a.get_attribute("href") or ""
                if any(k in (txt+" "+href.lower()) for k in ["operationally available","download","csv","excel"]):
                    target=urljoin(page.url,href)
                    rr=await ctx.request.get(target, timeout=30000)
                    body=await rr.body()
                    text=body.decode("utf-8",errors="ignore")
                    rows=rows_from_html(text)
                    if rows:
                        await browser.close(); return choose_latest_timely(rows)
            except Exception:
                pass
        await browser.close()
    return []

async def collect_pipeline(pipeline):
    url=pipeline["source_url"]
    try:
        rows=await direct_collect(url)
    except Exception:
        rows=[]
    if not rows:
        try: rows=await browser_collect(url)
        except Exception: rows=[]
    return filter_configured(rows,pipeline)

def norm(s): return re.sub(r"[^A-Z0-9]+","",str(s or "").upper())

def filter_configured(rows,pipeline):
    output=[]
    for section in pipeline.get("sections",[]):
        ids={norm(x) for x in section.get("points",[])}
        names=[norm(x) for x in section.get("names",[])]
        for r in rows:
            pid=norm(r.get("point_id")); pname=norm(r.get("point_name"))
            idmatch=bool(ids and pid in ids)
            namematch=any(n and (n in pname or pname in n) for n in names)
            if idmatch or namematch:
                rr=dict(r); rr["section"]=section["name"]; output.append(rr)
    return output
