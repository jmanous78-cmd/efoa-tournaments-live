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

DEADLINE_TYPES={
    "registration":{
        "field":"registration_deadline",
        "label":"εγγραφής / δήλωσης",
        "title":"Εγγραφή / δήλωση"
    },
    "payment":{
        "field":"payment_deadline",
        "label":"πληρωμής",
        "title":"Πληρωμή"
    }
}

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
    if e.get("registration_url"):links.append(f"[e-ΕΦΟΑ]({e['registration_url']})")
    if e.get("proclamation_url"):links.append(f"[Προκήρυξη]({e['proclamation_url']})")
    if e.get("source_url"):links.append(f"[Πηγή]({e['source_url']})")
    rows=[
        f"### {kind}",
        f"**{e.get('title','Τουρνουά')}**",
        f"- Επίπεδο: **{e.get('level','—')}**",
        f"- Κατηγορίες: **{cats or 'προς επιβεβαίωση'}**",
        f"- Αγώνες: **{fmt_date(e.get('start'))} – {fmt_date(e.get('end'))}**",
        f"- Έδρα: **{place or 'προς ανακοίνωση'}**",
    ]
    if e.get("registration_deadline"):
        rows.append(f"- 📝 Λήξη εγγραφής / δήλωσης: **{fmt_date(e['registration_deadline'])}**")
    if e.get("payment_deadline"):
        rows.append(f"- 💳 Λήξη πληρωμής: **{fmt_date(e['payment_deadline'])}**")
    if extra:rows.append(f"- {extra}")
    rows += [""," · ".join(links)]
    return "\n".join(rows)

def main():
    cfg=load(CONFIG,{})
    data=load(DATA,{"tournaments":[]})
    tz=ZoneInfo(cfg.get("timezone","Europe/Athens"))
    now=datetime.now(tz)
    cats=set(cfg.get("categories") or [])
    levels=set(cfg.get("levels") or ["E1","E2","E3"])
    types=[t for t in (cfg.get("deadline_types") or ["registration","payment"]) if t in DEADLINE_TYPES]
    thresholds=sorted({int(x) for x in (cfg.get("deadline_hours") or [72,24])}, reverse=True)

    relevant=[]
    for e in data.get("tournaments",[]):
        if e.get("level") not in levels:continue
        if not cats.intersection(e.get("categories") or []):continue
        try:
            if date.fromisoformat(e.get("end","1900-01-01")) < now.date():continue
        except Exception:continue
        relevant.append(e)

    old_state=load(STATE,{})
    known=set(old_state.get("known_events") or [])
    # Schema v2 separates registration/payment. Legacy generic deadline state is
    # deliberately not reused because it could represent the wrong deadline type.
    state_v2=old_state.get("schema_version")==2
    stored_deadlines=old_state.get("deadlines") if state_v2 else {}
    stored_sent=old_state.get("sent_thresholds") if state_v2 else {}
    deadlines={t:dict((stored_deadlines or {}).get(t) or {}) for t in types}
    sent={t:{k:set(v) for k,v in ((stored_sent or {}).get(t) or {}).items()} for t in types}
    bootstrap=not bool(old_state)

    alerts=[]
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

        for dtype in types:
            meta=DEADLINE_TYPES[dtype]
            dl=e.get(meta["field"])
            if not dl:continue
            old_dl=deadlines[dtype].get(eid)
            try:h=(datetime.fromisoformat(dl).astimezone(tz)-now).total_seconds()/3600
            except Exception:h=None

            changed=bool(old_dl and old_dl!=dl)
            new_typed=not old_dl

            # Only notify a newly separated deadline if it is still actionable.
            if changed and h is not None and h>=0:
                alerts.append({
                    "key":f"{dtype}-change:{eid}:{dl}",
                    "title":f"⏰ Αλλαγή προθεσμίας {meta['label']} · {e.get('title','ΕΦΟΑ')}",
                    "markdown":event_markdown(e,f"Άλλαξε η προθεσμία {meta['label']}",f"Προηγούμενη: {fmt_date(old_dl)}")
                })
                sent[dtype][eid]=set()

            deadlines[dtype][eid]=dl
            if h is None or h<0:
                continue

            eligible=sorted([t for t in thresholds if h<=t])
            threshold=min(eligible) if eligible else None
            already=sent[dtype].setdefault(eid,set())

            if threshold is not None and threshold not in already:
                label=f"Λήξη {meta['label']} σε ≤{threshold} ώρες"
                alerts.append({
                    "key":f"{dtype}-threshold:{eid}:{threshold}:{dl}",
                    "title":f"🚨 {meta['title']} σε ≤{threshold} ώρες · {e.get('title','ΕΦΟΑ')}",
                    "markdown":event_markdown(e,label)
                })
                already.add(threshold)
            elif new_typed and state_v2 and not bootstrap:
                alerts.append({
                    "key":f"{dtype}-new:{eid}:{dl}",
                    "title":f"⏰ Νέα προθεσμία {meta['label']} · {e.get('title','ΕΦΟΑ')}",
                    "markdown":event_markdown(e,f"Δημοσιεύτηκε προθεσμία {meta['label']}")
                })

    next_state={
        "schema_version":2,
        "known_events":sorted(known),
        "deadlines":deadlines,
        "sent_thresholds":{t:{k:sorted(v) for k,v in sent[t].items()} for t in types},
        "categories":sorted(cats)
    }
    save(PENDING,{"generated_at":now.isoformat(timespec="seconds"),"alerts":alerts})
    save(NEXT,next_state)
    print(json.dumps({"alerts":len(alerts),"bootstrap":bootstrap,"state_migrated":not state_v2,"relevant":len(relevant)},ensure_ascii=False))

if __name__=="__main__":
    main()
