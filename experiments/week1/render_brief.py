"""Render the meeting brief for offline reading. Requires Markdown==3.11.1."""
from pathlib import Path
import html
import re
import markdown

HERE = Path(__file__).resolve().parent
source = HERE / "MEETING_BRIEF_RU.md"
converter = markdown.Markdown(extensions=["tables", "fenced_code", "toc"],
                              extension_configs={"toc": {"toc_depth": "2-2"}})
body = converter.convert(source.read_text())
body = re.sub(r"<table>(.*?)</table>", r'<div class="table-wrap"><table>\1</table></div>',
              body, flags=re.S)
title = "Связи контрактов prediction markets: разбор перед встречей"
css = """
:root { color-scheme: light; --ink:#1d2932; --muted:#53616b; --accent:#146558; --line:#dce3e1; }
* { box-sizing:border-box; }
html { scroll-padding-top:24px; }
body { margin:0; color:var(--ink); background:#f7f8f5; font:18px/1.7 Georgia,'Times New Roman',serif; }
.layout { max-width:1330px; margin:0 auto; display:grid; grid-template-columns:255px minmax(0,1fr); gap:54px; padding:50px 32px 100px; }
aside { position:sticky; top:30px; align-self:start; font:14px/1.5 system-ui,sans-serif; color:var(--muted); }
.eyebrow { font:700 12px/1.5 system-ui,sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); }
aside ul { list-style:none; margin:18px 0; padding:0; }
aside li { padding:7px 0; }
aside a { text-decoration:none; }
main { min-width:0; max-width:900px; }
h1,h2,h3 { font-family:system-ui,sans-serif; line-height:1.22; letter-spacing:-.025em; }
h1 { font-size:42px; margin:8px 0 25px; }
h2 { font-size:28px; margin:56px 0 20px; padding-top:24px; border-top:1px solid var(--line); }
h3 { font-size:21px; margin:32px 0 15px; }
p { margin:0 0 20px; }
a { color:var(--accent); text-decoration-thickness:1px; text-underline-offset:3px; }
strong { font-weight:700; }
code { font: .86em/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:#eaf0ed; padding:2px 4px; border-radius:4px; }
pre { background:#eaf0ed; padding:20px; overflow:auto; border-radius:8px; }
pre code { padding:0; }
.table-wrap { overflow-x:auto; margin:24px 0; }
table { width:100%; border-collapse:collapse; font:14px/1.55 system-ui,sans-serif; background:white; }
th,td { padding:12px 14px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }
th { color:#183d35; background:#e6efeb; font-weight:650; }
td:first-child { min-width:110px; }
li { margin-bottom:10px; }
footer { margin-top:48px; padding-top:20px; border-top:1px solid var(--line); font:13px/1.6 system-ui,sans-serif; color:var(--muted); }
@media(max-width:1000px) { .layout { grid-template-columns:1fr; max-width:900px; padding:28px 24px 70px; gap:20px; } aside { position:static; } aside .toc { display:none; } h1{font-size:34px;} }
@media(max-width:550px) { body {font-size:17px;} h1{font-size:29px;} h2{font-size:25px;} .layout{padding:22px 18px 60px;} }
@media print { body {background:white;font-size:11pt;} .layout{display:block;padding:0;} aside{display:none;} h1{font-size:25pt;} h2{font-size:18pt;break-after:avoid;} h3{font-size:14pt;break-after:avoid;} table{font-size:9pt;} tr{break-inside:avoid;} a{color:inherit;} .table-wrap{overflow:visible;} }
"""
page = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{css}</style></head>
<body><div class="layout"><aside><div class="eyebrow">Research briefing</div>
<p>21 октября 2026<br>25-30 минут чтения</p>{converter.toc}
<p><a href="MEETING_BRIEF_RU.md">Исходный Markdown</a><br><a href="README.md">Запустить эксперимент</a></p></aside>
<main>{body}<footer>Версия для чтения собрана из MEETING_BRIEF_RU.md. Результаты E01 относятся к development diagnostic; H1-H3 на независимых реальных данных ещё не подтверждены.</footer></main></div></body></html>
'''
(HERE / "MEETING_BRIEF_RU.html").write_text(page)
print("Rendered meeting brief,", len(source.read_text().split()), "words")
