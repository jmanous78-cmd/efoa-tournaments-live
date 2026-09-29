from pathlib import Path
from datetime import datetime, timezone
import json, requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/tournaments.json"
ICS=ROOT/"data/efoa-tournaments.ics"
SOURCES=[
 "https://e-efoa.gr/admin/tournamentsview/list",
 "https://efoa.gr/prokirykseis-enoseon-2026-e3-open-klp"
]

def load():
    try:return json.loads(OUT.read_text(encoding="utf-8"))
    except:return {"meta":{},"tournaments":[]}

def probe(url):
    r=requests.get(url,timeout=30,headers={"User-Agent":"EFOA-Tournament-Explorer/1.0"})
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"lxml")
    return " ".join(soup.stripped_strings)[:2000]

def make_ics(events):
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//EFOA Tournament Explorer//EL","CALSCALE:GREGORIAN"]
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in events:
        if not e.get("deadline"): continue
        dt=datetime.fromisoformat(e["deadline"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT",f"UID:{e['id']}@efoa-live",f"DTSTAMP:{stamp}",f"DTSTART:{dt}",f"SUMMARY:Deadline δηλώσεων: {e['title']}",
                  "BEGIN:VALARM","TRIGGER:-PT72H","ACTION:DISPLAY","DESCRIPTION:Λήξη δηλώσεων σε 72 ώρες","END:VALARM",
                  "BEGIN:VALARM","TRIGGER:-PT24H","ACTION:DISPLAY","DESCRIPTION:Λήξη δηλώσεων σε 24 ώρες","END:VALARM","END:VEVENT"]
    lines.append("END:VCALENDAR")
    ICS.write_text("\r\n".join(lines)+"\r\n",encoding="utf-8")

def main():
    data=load(); errors=[]
    for u in SOURCES:
        try: probe(u)
        except Exception as ex: errors.append(f"{u}: {ex}")
    data["meta"]={"updated_at":datetime.now().astimezone().isoformat(timespec="seconds"),"source_status":"ok" if not errors else "partial","errors":errors,"sources":SOURCES,"schema_version":2}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    make_ics(data.get("tournaments",[]))
    print(f"events={len(data.get('tournaments',[]))} errors={len(errors)}")

if __name__=="__main__": main()
