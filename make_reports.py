#!/usr/bin/env python3
"""Build bilingual, academic-style journal-club PDFs from issue JSON data."""
from pathlib import Path
from html import escape
import json
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 16mm 18mm 17mm 18mm;
@bottom-center { content: 'CONDENSED MATTER LITERATURE  ·  ' counter(page); font: 8pt 'DejaVu Sans',sans-serif; color:#697482; } }
* {box-sizing:border-box}
body {font-family:'Noto Sans CJK SC','Noto Sans CJK','DejaVu Sans',sans-serif;font-size:9pt;line-height:1.46;color:#202730}
header {border-bottom:1.5pt solid #243d55;padding-bottom:8pt;margin-bottom:13pt}
.kicker {font-size:7pt;letter-spacing:1.4px;color:#456078;text-transform:uppercase;font-weight:bold}
h1 {font-family:'DejaVu Serif',serif;font-size:18pt;font-weight:500;margin:5pt 0 4pt;line-height:1.2;color:#1d3042}
.meta {color:#5a6671;font-size:8pt}
h2 {font-size:11pt;margin:14pt 0 7pt;border-bottom:0.5pt solid #d7dce1;padding-bottom:3pt;color:#233d52}
h3 {font-size:10pt;line-height:1.38;margin:0 0 3pt;font-weight:700;color:#1d3348}
a {color:#184e7a;text-decoration:none}
.index {width:100%;border-collapse:collapse;table-layout:fixed;font-size:7.9pt}
.index th {text-align:left;font-weight:bold;color:#496176;background:#f1f3f5;border-top:1pt solid #9daab6;padding:4pt}
.index td {vertical-align:top;border-bottom:0.4pt solid #d7dce1;padding:4pt}
.index .n {width:21pt}
.index .venue {width:76pt}
.index .name {font-weight:600;line-height:1.36}
.small {font-size:7.4pt;color:#576675;margin-top:1pt}
.paper {margin-top:11pt;padding-top:0;break-inside:avoid-page}
.paper + .paper {border-top:0.6pt solid #bfc8d0;padding-top:9pt}
.authors {font-size:7.5pt;color:#566371;margin:3pt 0 6pt}
.pub {font-size:7.6pt;color:#385973}
p {margin:4pt 0}
.key {font-weight:700;color:#314a62}
.block {margin-top:4pt}
.brief {margin-top:8pt;break-inside:avoid}
.brief h3 {font-size:9pt}
.note {color:#55616c;font-size:7.6pt;margin-top:5pt}
"""

def v(p, field, lang):
    return p.get(f'{field}_{lang}') or p.get(field) or ''

def safe(value):
    return escape(str(value or ''))

def link(url, text):
    return f'<a href="{safe(url)}">{safe(text)}</a>'

def document(issue, lang):
    zh = lang == 'zh'
    papers = issue.get('papers', [])
    features = [p for p in papers if p.get('level') == 'Feature']
    others = [p for p in papers if p not in features]
    headline = '凝聚态物理文献精选' if zh else 'Daily Condensed Matter Literature'
    subtitle = 'Journal Club · 精选论文' if zh else 'Journal Club · Research Notes'
    lines = [f'<html lang="{lang}"><meta charset="utf-8"><style>{CSS}</style><body>',
        '<header><div class="kicker">CONDENSED MATTER PHYSICS · LITERATURE MONITOR</div>',
        f'<h1>{headline}</h1><div class="meta">{safe(issue["date"])} · {subtitle} · {len(papers)} {"篇论文" if zh else "papers"}</div></header>']
    lines.append(f'<h2>{"当日文献索引" if zh else "Literature Index"}</h2>')
    lines.append('<table class="index"><thead><tr><th class="n">#</th><th>' +
        ('论文与作者' if zh else 'Paper and authors') + '</th><th class="venue">' +
        ('来源' if zh else 'Source') + '</th></tr></thead><tbody>')
    for i, p in enumerate(papers, 1):
        status = p.get('published_journal') or p.get('journal') or 'arXiv'
        lines.append(f'<tr><td>{i:02d}</td><td><div class="name">{link(p.get("url",""),p.get("title",""))}</div>' +
            f'<div class="small">{safe(p.get("authors"))} · {"通讯" if zh else "Corresponding"}: {safe(p.get("corresponding") or "—")}</div></td>' +
            f'<td>{safe(status)}</td></tr>')
    lines.append('</tbody></table>')
    lines.append(f'<h2>{"重点论文解读" if zh else "Featured Papers"}</h2>')
    for i, p in enumerate(features, 1):
        venue = p.get('published_journal') or p.get('journal') or ''
        lines.append(f'<section class="paper"><div class="pub">{i:02d} · {safe(venue)} · {link(p.get("url",""), "arXiv / DOI ↗")}</div>')
        lines.append(f'<h3>{safe(p.get("title"))}</h3><div class="authors">{safe(p.get("authors"))} · ' +
                     f'{"通讯" if zh else "Corresponding"}: {safe(p.get("corresponding") or "—")}</div>')
        fields = [('summary', '研究概述' if zh else 'Overview'),
                  ('method', '研究方法' if zh else 'Methods'),
                  ('result', '作者主要结果' if zh else "Authors' findings"),
                  ('future', '我们可以做什么' if zh else 'Experimental follow-up')]
        for key, label in fields:
            value = v(p, key, lang)
            if value:
                lines.append(f'<p class="block"><span class="key">{label} — </span>{safe(value)}</p>')
        if p.get('tier'):
            reason = v(p, 'tier_reason', lang)
            lines.append(f'<p class="block"><span class="key">{"预估期刊档次" if zh else "Estimated journal tier"} — </span>' +
                f'{safe(p["tier"])}{(" · "+safe(reason)) if reason else ""}</p>')
        lines.append('</section>')
    if others:
        lines.append(f'<h2>{"其他相关论文" if zh else "Additional Papers"}</h2>')
        for p in others:
            venue = p.get('published_journal') or p.get('journal') or ''
            lines.append(f'<section class="brief"><div class="pub">{safe(venue)}</div>' +
                f'<h3>{link(p.get("url",""),p.get("title",""))}</h3>')
            lines.append(f'<div class="small">{safe(p.get("authors"))} · ' +
                f'{"通讯" if zh else "Corresponding"}: {safe(p.get("corresponding") or "—")}</div>')
            if v(p,'summary',lang):
                lines.append(f'<p>{safe(v(p,"summary",lang))}</p>')
            if p.get('tier'):
                lines.append(f'<p class="note">{"预估期刊档次" if zh else "Estimated journal tier"}: ' +
                    f'{safe(p["tier"])} · {safe(v(p,"tier_reason",lang))}</p>')
            lines.append('</section>')
    return '\n'.join(lines + ['</body></html>'])

def main():
    (ROOT/'reports').mkdir(exist_ok=True)
    for file in sorted((ROOT/'issues').glob('????-??-??.json')):
        issue = json.loads(file.read_text(encoding='utf-8'))
        for lang in ('en','zh'):
            destination = ROOT/'reports'/f'{issue["date"]}.{lang}.pdf'
            HTML(string=document(issue,lang), base_url=str(ROOT)).write_pdf(destination)
            print(destination, destination.stat().st_size)

if __name__ == '__main__':
    main()
