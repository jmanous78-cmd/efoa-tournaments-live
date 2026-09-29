from __future__ import annotations

from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import io
import json
import re
import time
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/tournaments.json"
ICS = ROOT / "data/efoa-tournaments.ics"
CACHE = ROOT / "data/geocode-cache.json"
TZ = ZoneInfo("Europe/Athens")
EEFOA = "https://e-efoa.gr/admin/tournamentsview/list"
NEWS = "https://efoa.gr/ta-athlemata-mas/tenis/teleutaia-nea-tennis"
UA = "EFOA-Tournament-Explorer/2.0 (+https://github.com/jmanous78-cmd/efoa-tournaments-live)"

MONTHS = {
    "ΙΑΝΟΥΑΡΙΟΥ": 1, "ΦΕΒΡΟΥΑΡΙΟΥ": 2, "ΜΑΡΤΙΟΥ": 3, "ΑΠΡΙΛΙΟΥ": 4,
    "ΜΑΙΟΥ": 5, "ΜΑΪΟΥ": 5, "ΙΟΥΝΙΟΥ": 6, "ΙΟΥΛΙΟΥ": 7, "ΑΥΓΟΥΣΤΟΥ": 8,
    "ΣΕΠΤΕΜΒΡΙΟΥ": 9, "ΟΚΤΩΒΡΙΟΥ": 10, "ΝΟΕΜΒΡΙΟΥ": 11, "ΔΕΚΕΜΒΡΙΟΥ": 12,
}
UNION_ROMAN = {"Α":"A","Β":"B","Γ":"G","Δ":"D","Ε":"E","ΣΤ":"ST","Ζ":"Z","Η":"H","Θ":"TH","ΙΑ":"IA"}

def http_get(url, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", UA)
    return requests.get(url, headers=headers, timeout=35, **kwargs)

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def clean(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\xa0", " ")).strip()

def ascii_key(s):
    s = unicodedata.normalize("NFD", clean(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def stable_id(*parts):
    raw = "|".join(ascii_key(x) for x in parts if x is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

def iso_week_range(year, week):
    mon = date.fromisocalendar(year, week, 1)
    return mon, mon + timedelta(days=6)

def normalize_union(s):
    t = clean(s).upper().replace("Έ", "Ε").replace("΄", "").replace("’", "").replace("'", "")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"\b(ΙΑ|ΣΤ|[Α-Θ])\s*ΕΝΩΣ", t)
    if not m:
        return clean(s)
    return f"{m.group(1)}΄ Ένωση"

def categories_from_text(s):
    t = clean(s).upper()
    explicit = sorted(set(re.findall(r"\b[ΑΚΜ](?:10|12|14|16|18)\b", t)))
    if explicit:
        return explicit
    ages = [int(x) for x in re.findall(r"(?<!\d)(10|12|14|16|18)(?!\d)", t)]
    out = []
    for age in ages:
        out += [f"Α{age}", f"Κ{age}"]
    return list(dict.fromkeys(out))

def parse_level(s):
    # EFOA uses the Greek epsilon (Ε/ε), while some sources use Latin E.
    t = ascii_key(s).replace(" ", "").replace("Ε", "E")
    for lev in ("E1", "E2", "E3"):
        if lev in t:
            return lev
    return None

def greek_range(text, fallback_year):
    t = clean(text).upper().replace("–", "-").replace("—", "-")
    month_names = "|".join(map(re.escape, MONTHS))
    p = rf"(?<!\d)(\d{{1,2}})\s*(?:-|ΕΩΣ|ΕΩΣ ΚΑΙ|ΚΑΙ|&)\s*(\d{{1,2}})\s+({month_names})(?:\s+(\d{{4}}))?"
    m = re.search(p, t)
    if m:
        y = int(m.group(4) or fallback_year); mo = MONTHS[m.group(3)]
        try: return date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))
        except ValueError: pass
    m = re.search(r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?", t)
    if m:
        y = int(m.group(4) or fallback_year); y = 2000+y if y < 100 else y
        try: return date(y, int(m.group(3)), int(m.group(1))), date(y, int(m.group(3)), int(m.group(2)))
        except ValueError: pass
    return None

def numeric_dates(text, fallback_year):
    t = clean(text)
    vals = []
    for d,m,y in re.findall(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", t):
        yy = int(y or fallback_year); yy = 2000+yy if yy < 100 else yy
        try: vals.append(date(yy, int(m), int(d)))
        except ValueError: pass
    return vals

def deadline_from_text(text, event_start=None):
    upper = clean(text).upper()
    snippets = []
    for m in re.finditer(r"ΔΗΛΩ|ΛΗΞΗ|ΕΓΓΡΑΦ|SIGN.?IN|ENTRY", upper):
        snippets.append(upper[max(0,m.start()-80):m.start()+260])
    candidates = []
    for sn in snippets:
        ds = numeric_dates(sn, (event_start or date.today()).year)
        for d in ds:
            tm = re.search(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)", sn)
            hh, mm = (int(tm.group(1)), int(tm.group(2))) if tm else (23, 59)
            dt = datetime(d.year,d.month,d.day,hh,mm,tzinfo=TZ)
            if not event_start or d <= event_start:
                candidates.append(dt)
    if not candidates:
        return None
    return max(candidates).isoformat(timespec="minutes")

def gdrive_download(url):
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url)
    if not m:
        m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    if not m:
        return None
    r = http_get(f"https://drive.google.com/uc?export=download&id={m.group(1)}")
    if r.ok and (r.content[:4] == b"%PDF" or "pdf" in r.headers.get("content-type","").lower()):
        return r.content
    return None

def pdf_text(url):
    try:
        blob = gdrive_download(url) if "drive.google.com" in url else http_get(url).content
        if not blob or blob[:4] != b"%PDF": return ""
        rd = PdfReader(io.BytesIO(blob))
        return "\n".join((p.extract_text() or "") for p in rd.pages[:8])
    except Exception:
        return ""

def proclamation_details(url, year, fallback_start=None):
    txt = pdf_text(url)
    if not txt:
        return {}
    rng = greek_range(txt, year)
    start, end = rng if rng else (fallback_start, None)
    return {
        "pdf_text_ok": True,
        "date_found": bool(rng),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "deadline": deadline_from_text(txt, start),
        "categories_pdf": categories_from_text(txt),
    }

def parse_e3_page(year):
    url = f"https://efoa.gr/prokirykseis-enoseon-{year}-e3-open-klp"
    r = http_get(url); r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    now = datetime.now(TZ).date()
    current_week = now.isocalendar().week
    items = []

    for table in soup.find_all("table"):
        week = None
        for prev in table.find_all_previous(["h1","h2","h3","h4","p","div"], limit=25):
            txt = clean(prev.get_text(" ", strip=True)).upper()
            m = re.search(r"(\d{1,2})\s*(?:Η|ΗΣ)?\s*ΕΒΔΟΜΑΔ", txt)
            if m:
                week = int(m.group(1)); break
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td","th"])
            vals = [clean(c.get_text(" ", strip=True)) for c in cells]
            row_text = " | ".join(vals)
            wm = re.search(r"(\d{1,2})\s*(?:Η|ΗΣ)?\s*ΕΒΔΟΜΑΔ", row_text.upper())
            if wm and len(vals) <= 2:
                week = int(wm.group(1)); continue
            if len(vals) < 4 or not week:
                continue
            union_raw, proclamation_text, cat_text, venue = vals[:4]
            level = parse_level(proclamation_text)
            if level != "E3":
                continue
            # Keep current/recent/future weeks. Old rows are not needed on the live map.
            if week < current_week - 1:
                continue
            union = normalize_union(union_raw)
            cats = categories_from_text(cat_text)
            links = [urljoin(url, a.get("href")) for a in cells[1].find_all("a", href=True)]
            purl = links[0] if links else None
            wstart, wend = iso_week_range(year, week)
            details = proclamation_details(purl, year, wstart) if purl else {}
            start = details.get("start") or wstart.isoformat()
            end = details.get("end") or wend.isoformat()
            pdfcats = details.get("categories_pdf") or []
            if pdfcats: cats = sorted(set(cats) | set(pdfcats))
            items.append({
                "id": f"e3-{year}-w{week}-{stable_id(union, venue)}",
                "level": "E3",
                "title": f"Ε3 {week}ης εβδομάδας – {union}",
                "categories": cats,
                "union": union,
                "unions": [union],
                "week": week,
                "start": start,
                "end": end,
                "date_precision": "proclamation" if details.get("date_found") else "week",
                "venue": venue,
                "city": "",
                "lat": None, "lon": None,
                "deadline": details.get("deadline"),
                "status": "confirmed",
                "source_url": url,
                "proclamation_url": purl,
                "registration_url": EEFOA,
                "source": "efoa-union-page",
            })
    return items, url

def article_links():
    found = {}
    for start in range(0, 91, 15):
        url = NEWS if start == 0 else f"{NEWS}?start={start}"
        try:
            r=http_get(url); r.raise_for_status()
            soup=BeautifulSoup(r.text,"lxml")
        except Exception:
            continue
        for a in soup.find_all("a", href=True):
            title=clean(a.get_text(" ",strip=True))
            if re.search(r"ΠΡΟΚΗΡΥΞ", title.upper()) and re.search(r"\bΕ[12]\b|\bE[12]\b", title.upper()):
                href=urljoin(url,a["href"])
                found[href]=title
    return found

def parse_e1e2_articles(year):
    out=[]
    for url, list_title in article_links().items():
        try:
            r=http_get(url); r.raise_for_status()
            soup=BeautifulSoup(r.text,"lxml")
            title=list_title
            article=soup.find("article") or soup.select_one(".item-page") or soup.select_one("main")
            scope=article or soup
            body=clean(scope.get_text(" ",strip=True))
        except Exception:
            continue
        if str(year) not in body and str(year) not in title:
            continue
        level=parse_level(title+" "+body[:500])
        if level not in {"E1","E2"}: continue
        wm=re.search(r"(\d{1,2})\s*(?:Η|ΗΣ)?\s*ΕΒΔΟΜΑΔ", title.upper()+" "+body[:1200].upper())
        week=int(wm.group(1)) if wm else None
        rng=greek_range(body[:3000], year)
        if rng: start_d,end_d=rng
        elif week: start_d,end_d=iso_week_range(year,week)
        else: continue
        if end_d < datetime.now(TZ).date()-timedelta(days=14):
            continue
        links=[urljoin(url,a["href"]) for a in scope.find_all("a",href=True) if "drive.google.com" in a["href"] or a["href"].lower().endswith(".pdf")]
        pdf_details=[proclamation_details(x,year,start_d) for x in links[:6]]
        cats=set()
        deadlines=[]
        dates=[]
        for d in pdf_details:
            cats.update(d.get("categories_pdf") or [])
            if d.get("deadline"): deadlines.append(d["deadline"])
            if d.get("start") and d.get("end"): dates.append((d["start"],d["end"]))
        if dates:
            # For multi-venue E2, use the widest confirmed date range.
            start_s=min(x[0] for x in dates); end_s=max(x[1] for x in dates)
        else:
            start_s,end_s=start_d.isoformat(),end_d.isoformat()
        unions=[]
        for roman in re.findall(r"\b(ΙΑ|ΣΤ|[Α-Θ])\s*[΄']?\s*ΕΝΩΣ", body.upper()):
            u=f"{roman}΄ Ένωση"
            if u not in unions: unions.append(u)
        title_num=re.search(r"(\d+)(?:ΟΥ|Ο|ΟY)?\s*Ε[12]", title.upper())
        num=title_num.group(1) if title_num else ""
        out.append({
            "id": f"{level.lower()}-{year}-{num or week or stable_id(title)}",
            "level": level,
            "title": title,
            "categories": sorted(cats),
            "union": " & ".join(unions),
            "unions": unions,
            "week": week,
            "start": start_s, "end": end_s,
            "date_precision": "proclamation" if dates or rng else "week",
            "venue": "Δείτε την προκήρυξη" if links else "",
            "city": "", "lat": None, "lon": None,
            "deadline": min(deadlines) if deadlines else deadline_from_text(body, start_d),
            "status": "confirmed",
            "source_url": url,
            "proclamation_url": links[0] if links else None,
            "registration_url": EEFOA,
            "source": "efoa-news",
        })
    return out

def date_from_row(cells, year):
    txt=" | ".join(cells)
    rng=greek_range(txt,year)
    if rng:return rng
    ds=numeric_dates(txt,year)
    if ds:
        return min(ds),max(ds)
    return None

def parse_eefoa_api(year):
    """Read the public OData-style endpoint discovered from the e-EFOA grid."""
    base="https://e-efoa.gr/api/v1/tournamentsview"
    diagnostics={"queries":[]}
    payload=None
    chosen=None
    # Probe variants once; null normally gives the broadest public year view.
    for current in ("null","1","0"):
        url=f"{base}(year={year},current={current},grade=null,organizer=null,group=null,club=null)"
        try:
            r=http_get(url,params={"$top":500,"$count":"true"})
            obj=r.json() if r.ok else {}
            count=obj.get("@odata.count", len(obj.get("value",[]))) if isinstance(obj,dict) else 0
            diagnostics["queries"].append({"current":current,"status":r.status_code,"count":count})
            if isinstance(obj,dict) and obj.get("value") and (payload is None or count > len(payload.get("value",[]))):
                payload=obj;chosen=current
        except Exception as ex:
            diagnostics["queries"].append({"current":current,"error":str(ex)})
    diagnostics["chosen_current"]=chosen
    if not payload:
        return [],diagnostics

    grouped={}
    for row in payload.get("value",[]):
        title=clean(row.get("TournamentTitle"))
        organizer=clean(row.get("OrganizerName"))
        level=parse_level(title+" "+organizer)
        if level not in {"E1","E2","E3"}:
            continue
        tid=str(row.get("TournamentId") or stable_id(title,row.get("TournamentDetailsMStartDate")))
        g=grouped.setdefault(tid,{
            "rows":[],"title":title,"level":level,"club":clean(row.get("Club")),
            "start_raw":row.get("TournamentDetailsMStartDate"),"categories":set(),
            "links":[],"qsign":[],"msign":[]
        })
        g["categories"].update(categories_from_text(row.get("Group","")))
        g["rows"].append(row)
        g["qsign"].append(clean(row.get("QSignIn")))
        g["msign"].append(clean(row.get("MSignIn")))
        for link in row.get("Links") or []:
            txt=clean(link.get("Text"))
            if txt:g["links"].append((clean(link.get("Key")),txt))

    out=[]
    for tid,g in grouped.items():
        try:
            start_dt=datetime.fromisoformat(str(g["start_raw"]))
            start_d=start_dt.date()
        except Exception:
            continue
        if start_d < datetime.now(TZ).date()-timedelta(days=14):
            continue
        if not g["categories"]:
            continue
        registration=None; proclamation=None
        for key,txt in g["links"]:
            if txt.startswith("/"):
                full="https://e-efoa.gr/admin"+txt
            else:
                full=urljoin("https://e-efoa.gr/admin/",txt)
            if "ΔΗΛΩΣ" in key.upper(): registration=full
            if "ΠΡΟΚΗΡ" in key.upper(): proclamation=full
        sign_text=" ".join(g["qsign"]+g["msign"])
        tm=re.search(r"(\d{1,2})\s*(?:Η|ΗΣ)?(?:\s*ΕΒΔΟΜΑΔ)?\s*\((ΙΑ|ΣΤ|[Α-Θ])\)", g["title"].upper())
        week=int(tm.group(1)) if tm else None
        union=f"{tm.group(2)}΄ Ένωση" if tm else ""
        if week:
            _, week_end=iso_week_range(year,week)
            end_d=max(start_d,week_end)
        else:
            end_d=start_d
        out.append({
            "id":f"eefoa-{tid}",
            "level":g["level"],"title":g["title"],
            "categories":sorted(g["categories"]),
            "union":union,"unions":[union] if union else [],
            "week":week,
            "start":start_d.isoformat(),"end":end_d.isoformat(),
            "date_precision":"eefoa-start/week-end" if week else "eefoa-start",
            "venue":g["club"],"city":"","lat":None,"lon":None,
            "deadline":deadline_from_text(sign_text,start_d),
            "status":"confirmed","source_url":EEFOA,
            "proclamation_url":proclamation,
            "registration_url":registration or EEFOA,
            "source":"e-efoa-api"
        })
    diagnostics["domestic_records"]=len(out)
    diagnostics["sample_titles"]=[x["title"] for x in out[:10]]
    return out,diagnostics

def parse_eefoa_with_playwright(year):
    """Render the public JS grid. Returns conservative records plus diagnostics."""
    diagnostics={"rows":0,"samples":[],"json_urls":[]}
    records=[]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={"width":1600,"height":1200})
            json_payloads=[]
            def on_response(resp):
                try:
                    ct=(resp.headers or {}).get("content-type","").lower()
                    if "json" in ct:
                        diagnostics["json_urls"].append(resp.url)
                        if len(json_payloads)<20:
                            json_payloads.append(resp.json())
                except Exception: pass
            page.on("response",on_response)
            page.goto(EEFOA,wait_until="domcontentloaded",timeout=60000)
            try: page.wait_for_load_state("networkidle",timeout=25000)
            except Exception: pass
            page.wait_for_timeout(5000)
            rows=page.locator("table tbody tr").evaluate_all("""els => els.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()).filter(Boolean)).filter(r=>r.length)""")
            diagnostics["rows"]=len(rows)
            diagnostics["samples"]=rows[:8]
            if json_payloads:
                def small_sample(obj):
                    if isinstance(obj, dict):
                        return {k: small_sample(v) for k,v in list(obj.items())[:12]}
                    if isinstance(obj, list):
                        return [small_sample(v) for v in obj[:3]]
                    if isinstance(obj, str):
                        return obj[:180]
                    return obj
                diagnostics["json_samples"]=[small_sample(x) for x in json_payloads[:3]]
            browser.close()
    except Exception as ex:
        diagnostics["error"]=str(ex)
        return [],diagnostics

    for cells in rows:
        joined=" | ".join(cells)
        level=parse_level(joined)
        cats=categories_from_text(joined)
        if not level or not cats: continue
        dr=date_from_row(cells,year)
        if not dr: continue
        start_d,end_d=dr
        # Only public upcoming/recent tournaments.
        if end_d < datetime.now(TZ).date()-timedelta(days=14): continue
        records.append({
            "id": f"eefoa-{stable_id(level, joined)}",
            "level": level,
            "title": next((x for x in cells if level in ascii_key(x).replace(' ','')), f"{level}"),
            "categories": cats,
            "union": "",
            "unions": [],
            "start": start_d.isoformat(), "end": end_d.isoformat(),
            "date_precision": "eefoa",
            "venue": cells[-1] if cells else "",
            "city": "", "lat": None, "lon": None,
            "deadline": deadline_from_text(joined,start_d),
            "status":"confirmed",
            "source_url":EEFOA,
            "proclamation_url":None,
            "registration_url":EEFOA,
            "source":"e-efoa",
            "raw_row":cells,
        })
    return records,diagnostics

def same_event(a,b):
    if a.get("level") != b.get("level"): return False
    try:
        a1=date.fromisoformat(a["start"]); a2=date.fromisoformat(a["end"])
        b1=date.fromisoformat(b["start"]); b2=date.fromisoformat(b["end"])
        overlap = not (a2 < b1-timedelta(days=3) or b2 < a1-timedelta(days=3))
    except Exception:
        overlap=False
    if not overlap:return False
    va=ascii_key(a.get("venue","")); vb=ascii_key(b.get("venue",""))
    if va and vb and (va in vb or vb in va):return True
    ua=set(a.get("unions") or []); ub=set(b.get("unions") or [])
    return bool(ua & ub) or not ua or not ub

def merge_records(primary, enrichers, old):
    result=[dict(x) for x in primary]
    for e in enrichers:
        match=next((x for x in result if same_event(x,e)),None)
        if match:
            match["categories"]=sorted(set(match.get("categories",[]))|set(e.get("categories",[])))
            if not match.get("deadline") and e.get("deadline"):match["deadline"]=e["deadline"]
            if e.get("source")=="e-efoa-api":
                if e.get("venue"): match["venue"]=e["venue"]
                if e.get("registration_url"): match["registration_url"]=e["registration_url"]
                if match.get("date_precision")=="week" and e.get("start"):
                    try:
                        es=date.fromisoformat(e["start"])
                        ms=date.fromisoformat(match["start"]); me=date.fromisoformat(match["end"])
                        if ms <= es <= me:
                            match["start"]=e["start"]
                            match["date_precision"]="eefoa-start/week-end"
                    except Exception: pass
            elif not match.get("venue") and e.get("venue"):
                match["venue"]=e["venue"]
            match.setdefault("sources",[])
            if e.get("source_url") not in match["sources"]:match["sources"].append(e.get("source_url"))
        else:
            result.append(e)

    # Reuse previously verified metadata when a fresh source is less precise.
    for x in result:
        prev=next((o for o in old if same_event(o,x)),None)
        if not prev:
            continue
        for fld in ("lat","lon","city"):
            if (x.get(fld) is None or x.get(fld)=="") and prev.get(fld) not in (None,""):
                x[fld]=prev[fld]
        if not x.get("deadline") and prev.get("deadline"):
            x["deadline"]=prev["deadline"]
        if x.get("source")=="e-efoa-api" and prev.get("status")=="planned" and prev.get("start") and prev.get("end"):
            try:
                ps=date.fromisoformat(prev["start"]); pe=date.fromisoformat(prev["end"])
                xs=date.fromisoformat(x["start"])
                if ps <= xs <= pe:
                    x["start"],x["end"]=prev["start"],prev["end"]
                    x["date_precision"]="annual-program+eefoa"
                    if prev.get("union") and not x.get("union"):
                        x["union"],x["unions"]=prev["union"],prev.get("unions",[])
            except Exception: pass
        if x.get("date_precision")=="week" and prev.get("start") and prev.get("end"):
            try:
                ps=date.fromisoformat(prev["start"]); pe=date.fromisoformat(prev["end"])
                xs=date.fromisoformat(x["start"]); xe=date.fromisoformat(x["end"])
                if xs <= ps <= pe <= xe:
                    x["start"],x["end"]=prev["start"],prev["end"]
                    x["date_precision"]="previous-confirmed"
            except Exception:
                pass

    # Preserve future manually/planned entries that live sources have not announced yet.
    today=datetime.now(TZ).date()
    for o in old:
        try: future=date.fromisoformat(o["end"]) >= today-timedelta(days=7)
        except Exception: future=False
        if future and not any(same_event(o,x) for x in result):
            oo=dict(o); oo["status"]="planned" if oo.get("status")=="planned" else oo.get("status","confirmed")
            result.append(oo)
    # Deduplicate by id and sort.
    ded={x["id"]:x for x in result}
    return sorted(ded.values(),key=lambda x:(x.get("start","9999"),x.get("level",""),x.get("title","")))

def geocode(events):
    cache=load_json(CACHE,{})
    changed=False
    for e in events:
        if e.get("lat") is not None and e.get("lon") is not None: continue
        q=clean(e.get("venue"))
        if not q or "ΑΝΑΚΟΙΝ" in q.upper() or "ΠΡΟΚΗΡΥΞ" in q.upper(): continue
        key=ascii_key(q)
        if key in cache:
            g=cache[key]
        else:
            try:
                time.sleep(1.05)
                r=http_get("https://nominatim.openstreetmap.org/search",params={"q":f"{q}, Ελλάδα","format":"jsonv2","limit":1,"addressdetails":1})
                arr=r.json() if r.ok else []
                g=arr[0] if arr else None
            except Exception:g=None
            cache[key]=g;changed=True
        if g:
            e["lat"]=float(g["lat"]);e["lon"]=float(g["lon"])
            addr=g.get("address") or {}
            e["city"]=e.get("city") or addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
    if changed:save_json(CACHE,cache)

def make_ics(events):
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//EFOA Tournament Explorer//EL","CALSCALE:GREGORIAN","X-WR-CALNAME:ΕΦΟΑ Tournament Deadlines"]
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in events:
        if not e.get("deadline"):continue
        try:dt=datetime.fromisoformat(e["deadline"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        except Exception:continue
        summary=f"Deadline δηλώσεων: {e.get('title','ΕΦΟΑ')}".replace("\n"," ")
        lines += ["BEGIN:VEVENT",f"UID:{e['id']}@efoa-live",f"DTSTAMP:{stamp}",f"DTSTART:{dt}",f"SUMMARY:{summary}",
                  f"URL:{e.get('registration_url') or e.get('source_url') or ''}",
                  "BEGIN:VALARM","TRIGGER:-PT72H","ACTION:DISPLAY","DESCRIPTION:Λήξη δηλώσεων σε 72 ώρες","END:VALARM",
                  "BEGIN:VALARM","TRIGGER:-PT24H","ACTION:DISPLAY","DESCRIPTION:Λήξη δηλώσεων σε 24 ώρες","END:VALARM","END:VEVENT"]
    lines.append("END:VCALENDAR")
    ICS.write_text("\r\n".join(lines)+"\r\n",encoding="utf-8")

def main():
    now=datetime.now(TZ);year=now.year
    olddata=load_json(OUT,{"tournaments":[]});old=olddata.get("tournaments",[])
    errors=[];sources=[]

    try:
        e3,e3url=parse_e3_page(year);sources.append(e3url)
    except Exception as ex:
        e3=[];errors.append(f"EFOA E3 page: {ex}")
    try:
        e12=parse_e1e2_articles(year);sources.append(NEWS)
    except Exception as ex:
        e12=[];errors.append(f"EFOA news: {ex}")
    ee,api_diag=parse_eefoa_api(year)
    diag={"api":api_diag}
    if not ee:
        errors.append("e-EFOA API returned no recent domestic junior E1/E2/E3 records")
    sources.append(EEFOA)

    primary=e3+e12
    events=merge_records(primary,ee,old)
    geocode(events)
    make_ics(events)
    data={
      "meta":{
        "updated_at":now.isoformat(timespec="seconds"),
        "source_status":"ok" if not errors else ("partial" if events else "error"),
        "errors":errors,
        "sources":sources,
        "schema_version":3,
        "counts":{"e3":len(e3),"e1e2":len(e12),"eefoa":len(ee),"total":len(events)},
        "eefoa_diagnostics":diag,
      },
      "tournaments":events,
    }
    save_json(OUT,data)
    print(json.dumps(data["meta"],ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
