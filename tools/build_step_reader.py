"""Builds a single-page code reader: v2.1-pdu files in reading order, with the v2.1-base version and the diff."""
import html, keyword, re, subprocess, sys

REPO, OUT = sys.argv[1], sys.argv[2]
NEW, OLD = "v2.1-protocol", "v2.1-base"

ORDER = [  # (group, path, note)
 ("1. Yeni: protokol", "asl_testing/protocol/base.py", "Sözleşme: path, encode, decode, simulate"),
 ("1. Yeni: protokol", "asl_testing/protocol/ethernet.py", "Ethernet protokolü: bayt listesi, zaman birimi"),
 ("1. Yeni: protokol", "asl_testing/protocol/defaults.py", "Hangi kanal türü hangi protokolü kullanır"),
 ("1. Yeni: protokol", "asl_testing/protocol/__init__.py", "Paket"),
 ("2. Değişen", "asl_testing/runtime/transport.py", "TX / RX: protokol varsa post / get, yoksa eski yol"),
 ("2. Değişen", "asl_testing/uts/client.py", "UTS istemcisine JSON düzeyi: post / get"),
 ("2. Değişen", "asl_testing/uts/fake.py", "Sahte UTS: post / get, Ethernet için simulate"),
 ("2. Değişen", "asl_testing/comm.py", "Comm(..., protocols=)"),
 ("2. Değişen", "asl_testing/__init__.py", "Dışa açılan isimler"),
 ("3. Test", "tests/test_protocol.py", "Adım 1 testleri"),
 ("4. Değişmeyenler (referans)", "asl_testing/channel/channel.py", "Kanal: aynı"),
 ("4. Değişmeyenler (referans)", "asl_testing/channel/framing.py", "Envelope, Splitter: aynı"),
 ("4. Değişmeyenler (referans)", "asl_testing/message/base.py", "BaseMessageStructure: aynı"),
 ("4. Değişmeyenler (referans)", "asl_testing/runtime/rx.py", "RX döngüsü: aynı"),
 ("4. Değişmeyenler (referans)", "asl_testing/runtime/tx.py", "TX zamanlayıcı: aynı"),
]


def git(*args):
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


KW = set(keyword.kwlist) | {"self", "cls"}
TOKEN = re.compile(r'(?P<str>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')'
                   r'|(?P<com>#[^\n]*)|(?P<name>\b[A-Za-z_][A-Za-z0-9_]*\b)|(?P<num>\b\d[\dxXa-fA-F_.]*\b)')


def highlight(src):
    out, pos = [], 0
    for m in TOKEN.finditer(src):
        out.append(html.escape(src[pos:m.start()]))
        t = html.escape(m.group())
        if m.lastgroup == "str":
            out.append(f'<span class="s">{t}</span>')
        elif m.lastgroup == "com":
            out.append(f'<span class="c">{t}</span>')
        elif m.lastgroup == "name" and m.group() in KW:
            out.append(f'<span class="k">{t}</span>')
        elif m.lastgroup == "num":
            out.append(f'<span class="n">{t}</span>')
        else:
            out.append(t)
        pos = m.end()
    out.append(html.escape(src[pos:]))
    return "".join(out)


def numbered(src):
    body = highlight(src)
    lines = body.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return "".join(f'<span class="ln">{i}</span>{l}\n' for i, l in enumerate(lines, 1))


def diff_html(d):
    rows = []
    for line in d.splitlines():
        if line.startswith(("diff --git", "index ", "--- ", "+++ ")):
            continue
        cls = "add" if line.startswith("+") else "del" if line.startswith("-") else "hunk" if line.startswith("@@") else ""
        rows.append(f'<span class="{cls}">{html.escape(line) or " "}</span>')
    return "".join(rows)


items, nav = [], []
current = None
for idx, (group, path, note) in enumerate(ORDER):
    new = git("show", f"{NEW}:{path}")
    old = git("show", f"{OLD}:{path}")
    if new is None and old is None:
        continue
    if group != current:
        nav.append(f'<div class="grp">{html.escape(group)}</div>')
        current = group
    state = "yeni" if old is None else "silindi" if new is None else ("değişti" if new != old else "aynı")
    nav.append(f'<a href="#" data-i="{idx}"><span class="fname">{html.escape(path.split("/", 1)[1])}</span>'
               f'<span class="badge b-{state}">{state}</span></a>')
    lines = len((new or old).splitlines())
    tabs, panes = [], []
    if new is not None:
        tabs.append(("Kod (adım 1)", f'<pre class="code">{numbered(new)}</pre>'))
    if new is not None and old is not None and new != old:
        d = git("diff", f"{OLD}", f"{NEW}", "--", path)
        tabs.append(("Fark (v2.1-base → adım 1)", f'<pre class="code diff">{diff_html(d)}</pre>'))
    if old is not None:
        tabs.append(("v2.1-base hali", f'<pre class="code">{numbered(old)}</pre>'))
    tab_btns = "".join(f'<button data-t="{k}"{" class=on" if k == 0 else ""}>{html.escape(t)}</button>' for k, (t, _) in enumerate(tabs))
    tab_panes = "".join(f'<div class="pane"{"" if k == 0 else " hidden"}>{p}</div>' for k, (_, p) in enumerate(tabs))
    items.append(f'''<section class="file" id="f{idx}" hidden>
<header><div class="path">{html.escape(path)}</div><div class="note">{html.escape(note)} · {lines} satır · <span class="badge b-{state}">{state}</span></div>
<div class="tabs">{tab_btns}</div></header>{tab_panes}</section>''')

page = f'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>asl_testing kod okuyucu</title>
<style>
:root {{ --bg:#fff; --panel:#f5f6f8; --text:#1d2433; --muted:#5b6474; --line:#e2e5ea; --accent:#2456c7;
  --code:#fbfbfc; --k:#7a3eb1; --s:#1f7a43; --c:#8a8f99; --n:#b0570e; --add:#e7f6ec; --del:#fdecec; --hunk:#eef2fb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0e1116; --panel:#161b23; --text:#e4e8ef; --muted:#9aa4b5; --line:#262d38;
  --accent:#7ea6ff; --code:#11151c; --k:#c39bff; --s:#7fd19b; --c:#6f7785; --n:#f0a868; --add:#12301e; --del:#3a1818; --hunk:#1a2236; }} }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif }}
.layout {{ display:grid; grid-template-columns:300px minmax(0,1fr); height:100vh }}
nav {{ overflow-y:auto; background:var(--panel); border-right:1px solid var(--line); padding:14px 10px }}
nav h1 {{ font-size:16px; margin:0 6px 2px }} nav p {{ margin:0 6px 12px; color:var(--muted); font-size:12.5px }}
.grp {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:14px 6px 4px }}
nav a {{ display:flex; justify-content:space-between; gap:6px; padding:5px 8px; border-radius:6px; color:var(--text); text-decoration:none; font-size:13.5px }}
nav a:hover, nav a.on {{ background:color-mix(in srgb, var(--accent) 14%, transparent) }}
.fname {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px; overflow:hidden; text-overflow:ellipsis }}
.badge {{ font-size:10.5px; padding:0 6px; border-radius:99px; align-self:center; white-space:nowrap }}
.b-yeni {{ background:#d8f3e2; color:#1f7a43 }} .b-değişti {{ background:#e3ebff; color:#2456c7 }}
.b-aynı {{ background:var(--line); color:var(--muted) }} .b-silindi {{ background:#fde1e1; color:#a33 }}
main {{ overflow-y:auto; min-width:0 }}
.file header {{ position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line); padding:14px 18px 0; z-index:1 }}
.path {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-weight:600; font-size:15px; word-break:break-all }}
.note {{ color:var(--muted); font-size:13px; margin:3px 0 10px }}
.tabs {{ display:flex; gap:4px; flex-wrap:wrap }} .tabs button {{ border:1px solid var(--line); border-bottom:none; background:var(--panel);
  color:var(--text); padding:6px 12px; border-radius:8px 8px 0 0; cursor:pointer; font-size:13px }}
.tabs button.on {{ background:var(--accent); color:#fff; border-color:var(--accent) }}
pre.code {{ margin:0; padding:12px 18px 40px; background:var(--code); font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  overflow-x:auto; tab-size:4 }}
.ln {{ display:inline-block; width:3.2em; color:var(--muted); opacity:.6; user-select:none; text-align:right; margin-right:1em }}
.k {{ color:var(--k); font-weight:600 }} .s {{ color:var(--s) }} .c {{ color:var(--c); font-style:italic }} .n {{ color:var(--n) }}
.diff span {{ display:block; white-space:pre }} .diff .add {{ background:var(--add) }} .diff .del {{ background:var(--del) }}
.diff .hunk {{ background:var(--hunk); color:var(--muted) }}
.intro {{ padding:28px; max-width:760px }} .intro h2 {{ margin-top:0 }}
@media (max-width:800px) {{ .layout {{ grid-template-columns:minmax(0,1fr); grid-template-rows:auto 1fr; height:auto }}
  nav {{ max-height:42vh; border-right:0; border-bottom:1px solid var(--line) }} main {{ overflow:visible }} pre.code {{ padding:10px 12px 30px }} }}
</style></head><body><div class="layout">
<nav><h1>asl_testing</h1><p>Adım 1: Ethernet protokolü · v2.1-base'e göre. Rozet: v2.1-base'e göre durum.</p>{"".join(nav)}</nav>
<main><div class="intro" id="intro"><h2>Nasıl okunur</h2>
<p>Adım 1: Ethernet için bir protokol nesnesi; transport onu kullanıyor. Kanal, mesaj, envelope, splitter, kayıt ve RS422 değişmedi.
Her dosyada <b>Kod</b> sekmesi bugünkü hali, <b>Fark</b> sekmesi v2.1-base'e göre değişen satırlar (yeşil eklenen, kırmızı silinen),
<b>v2.1-base hali</b> sekmesi kendi eski kodumuz.</p>
</div>{"".join(items)}</main></div>
<script>
const links=[...document.querySelectorAll('nav a')];
function show(i){{document.getElementById('intro').hidden=true;
 document.querySelectorAll('section.file').forEach(s=>s.hidden=true);
 const s=document.getElementById('f'+i); s.hidden=false;
 links.forEach(a=>a.classList.toggle('on',a.dataset.i==i)); document.querySelector('main').scrollTop=0; window.scrollTo(0,0);}}
links.forEach(a=>a.addEventListener('click',e=>{{e.preventDefault();show(a.dataset.i);}}));
document.querySelectorAll('section.file').forEach(sec=>{{const btns=[...sec.querySelectorAll('.tabs button')],panes=[...sec.querySelectorAll('.pane')];
 btns.forEach((b,k)=>b.addEventListener('click',()=>{{btns.forEach(x=>x.classList.remove('on'));b.classList.add('on');panes.forEach((p,j)=>p.hidden=j!==k);}}));}});
const ch=links.find(a=>a.textContent.startsWith('runtime/transport.py')); if(ch) show(ch.dataset.i);
</script></body></html>'''
open(OUT, "w", encoding="utf-8").write(page)
print("files:", len(items), "bytes:", len(page))
