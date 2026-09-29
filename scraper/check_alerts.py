from __future__ import annotations

from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/tournaments.json"
CONFIG=ROOT/"config/alerts.json"
STATE=ROOT/"data/alert-state.json"
PENDING=ROOT/"data/pending-alerts.json"
NEXT=ROOT/"data/alert-state-next.json"

def load(path, default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")

def fmt_date(s):
    if not s:return "—"
    try:return datetime.fromisoformat(s).strftime("%d/%m/%Y %H:%M")
    except Exception:
        try:return date.fromisoformat(s).strftime("%d/%m/%Y")
        except Exception:return s

def event_markdown(e, kind, extra=""):
    cats=", ".join(e.get("categories") or [])
    place=" · ".join(x for x in [e.get("venue"),e.get("city")] if x)
    links=[]
    if e.get("registration_url"):links.append(f"[Δηλώσεις]({e['registration_url']})")
    if e.get("proclamation_url"):links.append(f"[Προκήρυξη]({e['proclamation_url']})")
    if e.get("source_url"):links.append(f"[Πηγή]({e['source_url']})")
    return "\n".join([
        f"### {kind}",
        f"**{e.get('title','Τουρνουά')}**",
        f"- Επίπεδο: **{e.get('level','—')}**",
        f"- Κατηγορίες: **{cats or 'προς επιβεβαίωση'}**",
        f"- Αγώνες: **{fmt_date(e.get('start'))} – {fmt_date(e.get('end'))}**",
        f"- Έδρα: **{place or 'προς ανακοίνωση'}**",
        *( [f"- Deadline: **{fmt_date(e.get('deadline'))}**"] if e.get("deadline") else [] ),
        *( [f"- {extra}"] if extra else [] ),
        "",
        " · ".join(links)
    ])

def main():
    cfg=load(CONFIG,{})
    data=load(DATA,{"tournaments":[]})
    tz=ZoneInfo(cfg.get("timezone","Europe/Athens"))
    now=datetime.now(tz)
    cats=set(cfg.get("categories") or [])
    levels=set(cfg.get("levels") or ["E1","E2","E3"])
    thresholds=sorted({int(x) for x in (cfg.get("deadline_hours") or [72,24])}, reverse=True)

    relevant=[]
    for e in data.get("tournaments",[]):
        if e.get("level") not in levels:continue
        if not cats.intersection(e.get("categories") or []):continue
        try:
            if date.fromisoformat(e.get("end","1900-01-01")) < now.date():continue
        except Exception:continue
        relevant.append(e)

    state=load(STATE,{})
    bootstrap=not bool(state)
    known=set(state.get("known_events") or [])
    deadlines=dict(state.get("deadlines") or {})
    sent={k:set(v) for k,v in (state.get("sent_thresholds") or {}).items()}
    alerts=[]

    # On first run, existing tournaments are baseline; don't flood with "new" alerts.
    if bootstrap:
        known.update(e["id"] for e in relevant)

    for e in relevant:
        eid=e["id"]
        if not bootstrap and eid not in known:
            alerts.append({
                "key":f"new:{eid}",
                "title":f"🎾 Νέο {e.get('level','')} για {', '.join(sorted(cats.intersection(e.get('categories') or [])))}",
                "markdown":event_markdown(e,"Νέο τουρνουά στις κατηγορίες σου")
            })
        known.add(eid)

        dl=e.get("deadline")
        old_dl=deadlines.get(eid)
        if dl and old_dl and dl != old_dl:
            alerts.append({
                "key":f"deadline-change:{eid}:{dl}",
                "title":f"⏰ Αλλαγή deadline · {e.get('title','ΕΦΟΑ')}",
                "markdown":event_markdown(e,"Άλλαξε η προθεσμία δηλώσεων",f"Προηγούμενο deadline: {fmt_date(old_dl)}")
            })
            sent[eid]=set()
        elif dl and not old_dl and not bootstrap:
            alerts.append({
                "key":f"deadline-new:{eid}:{dl}",
                "title":f"⏰ Νέο deadline · {e.get('title','ΕΦΟΑ')}",
                "markdown":event_markdown(e,"Δημοσιεύτηκε προθεσμία δηλώσεων")
            })
        if dl:
            deadlines[eid]=dl
            try:h=(datetime.fromisoformat(dl).astimezone(tz)-now).total_seconds()/3600
            except Exception:h=None
            if h is not None and h >= 0:
                eligible=sorted([t for t in thresholds if h <= t])
                # Send only the most urgent threshold currently crossed.
                if eligible:
                    threshold=min(eligible)
                    already=sent.setdefault(eid,set())
                    if threshold not in already:
                        label=f"Λήξη δηλώσεων σε ≤{threshold} ώρες"
                        alerts.append({
                            "key":f"threshold:{eid}:{threshold}:{dl}",
                            "title":f"🚨 {label} · {e.get('title','ΕΦΟΑ')}",
                            "markdown":event_markdown(e,label)
                        })
                        already.add(threshold)

    next_state={
        "known_events":sorted(known),
        "deadlines":deadlines,
        "sent_thresholds":{k:sorted(v) for k,v in sent.items()},
        "categories":sorted(cats)
    }
    save(PENDING,{"generated_at":now.isoformat(timespec="seconds"),"alerts":alerts})
    save(NEXT,next_state)
    print(json.dumps({"alerts":len(alerts),"bootstrap":bootstrap,"relevant":len(relevant)},ensure_ascii=False))

if __name__=="__main__":
    main()
