import re
import math
import pandas as pd

ALIASES = {
    "gas_day": ["eff gas day", "effective date", "effgasday", "eff_gas_day", "gas day"],
    "cycle": ["cycle", "cycledesc", "cycle_desc"],
    "point_id": ["loc", "location", "meter #", "meter", "location id"],
    "point_name": ["loc name", "locationname", "loc_name", "location name", "loc name filter"],
    "direction": ["direction", "flow ind desc", "flow_ind_desc", "loc purp desc", "loc_purp_desc"],
    "operating_capacity": ["operating capacity", "operatingcapacity", "operating_capacity", "opc"],
    "scheduled": ["total scheduled qty", "total scheduled quantity", "totalscheduledquantity", "total_scheduled_quantity", "tsq"],
    "available": ["operationally available capacity", "operationallyavailablecapacity", "operationally_available_capacity", "oac", "avail"],
    "primary_scheduled": ["scheduled primary", "primary scheduled"],
    "secondary_prime": ["scheduled secondary prime", "secondary prime"],
    "secondary_scheduled": ["scheduled secondary", "secondary scheduled"],
    "interruptible_scheduled": ["scheduled interruptible", "interruptible scheduled"],
}

def clean(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).strip().lower()).strip()

def match_columns(df):
    cols={clean(c):c for c in df.columns}
    result={}
    for target, aliases in ALIASES.items():
        for a in aliases:
            a=clean(a)
            if a in cols:
                result[target]=cols[a]; break
    return result

def num(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except Exception: pass
    s=str(v).replace(",","").strip()
    if s in {"", "-", "N/A", "nan", "None"}: return None
    try: return float(s)
    except Exception: return None

def rows_from_table(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns=[" ".join(str(x) for x in c if str(x)!="nan") for c in df.columns]
    m=match_columns(df)
    if not ({"point_id","point_name"} & set(m)): return []
    out=[]
    for _,r in df.iterrows():
        cyc=str(r[m["cycle"]]).upper() if "cycle" in m and not pd.isna(r[m["cycle"]]) else ""
        if cyc and "TIM" not in cyc: continue
        gd=None
        if "gas_day" in m:
            try: gd=pd.to_datetime(r[m["gas_day"]]).date()
            except Exception: gd=None
        out.append({
            "gas_day": gd,
            "cycle": cyc or "TIMELY",
            "point_id": str(r[m["point_id"]]).strip() if "point_id" in m and not pd.isna(r[m["point_id"]]) else None,
            "point_name": str(r[m["point_name"]]).strip() if "point_name" in m and not pd.isna(r[m["point_name"]]) else None,
            "direction": str(r[m["direction"]]).strip() if "direction" in m and not pd.isna(r[m["direction"]]) else None,
            "operating_capacity": num(r[m["operating_capacity"]]) if "operating_capacity" in m else None,
            "scheduled": num(r[m["scheduled"]]) if "scheduled" in m else None,
            "available": num(r[m["available"]]) if "available" in m else None,
            "primary_scheduled": num(r[m["primary_scheduled"]]) if "primary_scheduled" in m else None,
            "secondary_prime": num(r[m["secondary_prime"]]) if "secondary_prime" in m else None,
            "secondary_scheduled": num(r[m["secondary_scheduled"]]) if "secondary_scheduled" in m else None,
            "interruptible_scheduled": num(r[m["interruptible_scheduled"]]) if "interruptible_scheduled" in m else None,
        })
    return out
