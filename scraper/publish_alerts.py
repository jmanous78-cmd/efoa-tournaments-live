from __future__ import annotations

from pathlib import Path
import json, os, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
PENDING=ROOT/"data/pending-alerts.json"
NEXT=ROOT/"data/alert-state-next.json"
STATE=ROOT/"data/alert-state.json"
CONFIG=ROOT/"config/alerts.json"

def run(*args, capture=False):
    return subprocess.run(args,check=True,text=True,capture_output=capture)

def main():
    pending=json.loads(PENDING.read_text(encoding="utf-8"))
    alerts=pending.get("alerts") or []
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    assignee=cfg.get("assignee","")
    if alerts:
        # One persistent thread, so notifications stay organized.
        subprocess.run(["gh","label","create","tournament-alerts","--color","1D76DB",
                        "--description","Automatic EFOA tournament alerts","--force"],
                       check=False,text=True,capture_output=True)
        q=run("gh","issue","list","--state","open","--label","tournament-alerts",
              "--json","number","--jq",".[0].number",capture=True).stdout.strip()
        if not q:
            args=["gh","issue","create","--title","🎾 ΕΦΟΑ Tournament Alerts",
                  "--body","Αυτό το issue χρησιμοποιείται για αυτόματες ειδοποιήσεις για τις κατηγορίες σου.",
                  "--label","tournament-alerts"]
            if assignee:args += ["--assignee",assignee]
            url=run(*args,capture=True).stdout.strip()
            q=url.rstrip("/").split("/")[-1]
        for a in alerts:
            body=f"<!-- {a['key']} -->\n{a['markdown']}"
            with tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,suffix=".md") as f:
                f.write(body); name=f.name
            try:run("gh","issue","comment",q,"--body-file",name)
            finally:
                try:os.unlink(name)
                except OSError:pass

    # Only advance state after all GitHub notifications were published successfully.
    STATE.write_text(NEXT.read_text(encoding="utf-8"),encoding="utf-8")
    print(f"published={len(alerts)}")

if __name__=="__main__":
    main()
