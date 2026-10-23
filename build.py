"""Build static bilingual site from dated issue JSON files."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent
issues=[json.loads(p.read_text(encoding="utf8")) for p in sorted((root/"issues").glob("????-??-??.json"),reverse=True)]
reports={}
for p in (root/"reports").glob("????-??-??.*.pdf") if (root/"reports").exists() else []:
    parts=p.name.split(".")
    if len(parts)==3 and parts[1] in ("en","zh"):
        reports.setdefault(parts[0],{})[parts[1]]="reports/"+p.name
payload=json.dumps(issues,ensure_ascii=False).replace("</","<\\/")
template=(root/"site_template.html").read_text(encoding="utf8")
(root/"index.html").write_text(template.replace("__ISSUES__",payload).replace("__REPORTS__",json.dumps(reports)),encoding="utf8")
print(f"Built {len(issues)} issues with {sum(len(i['papers']) for i in issues)} papers")
