"""Builds docs/architecture.html: the architecture of asl_testing with diagrams.

    python tools/build_architecture.py              -> docs/architecture.html
    python tools/build_architecture.py <path>       -> also a copy without <html>/<head>/<body> (for hosting)

The diagrams are generated as inline SVG, so the page needs no library and no internet.
"""

__author__ = "İsmail Baysal"

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "architecture.html"

# ---------------------------------------------------------------------------------------------- SVG helpers

CHAR_W = 7.0          # approximate width of one 12px character, for centring labels


def svg(width: int, height: int, body: str, label: str) -> str:
    return (f'<figure class="dia"><svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
            '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path class="ahd" d="M0,0 L10,5 L0,10 z"/></marker></defs>'
            f'{body}</svg><figcaption>{escape(label)}</figcaption></figure>')


def box(x, y, w, h, title, lines=(), kind="msg", title_size=14):
    out = [f'<rect class="b {kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>',
           f'<text class="bt" x="{x + 12}" y="{y + 22}" style="font-size:{title_size}px">{escape(title)}</text>']
    for i, line in enumerate(lines):
        out.append(f'<text class="bl" x="{x + 12}" y="{y + 42 + i * 17}">{escape(line)}</text>')
    return "".join(out)


def band(x, y, w, h, title, kind):
    """Layer band; title lines are separated by "|" and stay in the left 120 px."""
    out = [f'<rect class="band {kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>']
    for i, line in enumerate(title.split("|")):
        out.append(f'<text class="bandt" x="{x + 14}" y="{y + 26 + i * 17}">{escape(line)}</text>')
    return "".join(out)


def chip(x, y, w, title, sub=""):
    out = [f'<rect class="chip" x="{x}" y="{y}" width="{w}" height="{46 if sub else 30}" rx="6"/>',
           f'<text class="ct" x="{x + 10}" y="{y + 19}">{escape(title)}</text>']
    if sub:
        out.append(f'<text class="cs" x="{x + 10}" y="{y + 37}">{escape(sub)}</text>')
    return "".join(out)


def arrow(x1, y1, x2, y2, label="", dashed=False, lx=None, ly=None):
    cls = "ar ret" if dashed else "ar"
    out = f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#ah)"/>'
    if label:
        tx = lx if lx is not None else (x1 + x2) / 2 + 6
        ty = ly if ly is not None else (y1 + y2) / 2 - 6
        out += f'<text class="al" x="{tx}" y="{ty}">{escape(label)}</text>'
    return out


def sequence(lifelines: list[tuple[str, str]], steps: list[tuple], label: str, col: int = 132,
             row: int = 34, left: int = 20) -> str:
    """lifelines: (name, kind); steps: (from, to, text, style) with style "call", "ret", "self" or "note"."""
    names = [n for n, _ in lifelines]
    xs = {n: left + col // 2 + i * col for i, n in enumerate(names)}
    top, head = 14, 40
    height = top + head + 20 + len(steps) * row + 20
    width = left * 2 + col * len(names)
    out = []
    for name, kind in lifelines:
        x = xs[name]
        out.append(f'<rect class="b {kind}" x="{x - col / 2 + 6}" y="{top}" width="{col - 12}" height="{head}" rx="7"/>')
        out.append(f'<text class="lt" x="{x}" y="{top + 25}" text-anchor="middle">{escape(name)}</text>')
        out.append(f'<line class="life" x1="{x}" y1="{top + head}" x2="{x}" y2="{height - 10}"/>')
    y = top + head + 28
    for frm, to, text, style in steps:
        if style == "note":
            x = xs[frm]
            w = len(text) * CHAR_W + 16
            out.append(f'<rect class="note" x="{x - w / 2}" y="{y - 15}" width="{w}" height="22" rx="4"/>')
            out.append(f'<text class="nt" x="{x}" y="{y}" text-anchor="middle">{escape(text)}</text>')
        elif style == "self":
            x = xs[frm]
            out.append(f'<path class="ar" d="M{x},{y - 8} h26 v14 h-22" marker-end="url(#ah)"/>')
            out.append(f'<text class="al" x="{x + 32}" y="{y + 2}">{escape(text)}</text>')
        else:
            x1, x2 = xs[frm], xs[to]
            cls = "ar ret" if style == "ret" else "ar"
            pad = 4 if x2 > x1 else -4
            out.append(f'<line class="{cls}" x1="{x1}" y1="{y}" x2="{x2 - pad}" y2="{y}" marker-end="url(#ah)"/>')
            out.append(f'<text class="al" x="{(x1 + x2) / 2}" y="{y - 7}" text-anchor="middle">{escape(text)}</text>')
        y += row
    return svg(width, height, "".join(out), label)


# ---------------------------------------------------------------------------------------------- diagrams

def context_diagram() -> str:
    b = [
        box(20, 40, 190, 92, "Test kodu", ["tests/, HardwareTestCase", "projects/ (mesaj tanımı)"], "test"),
        box(260, 40, 230, 92, "asl_testing", ["mesaj modeli, kanal,", "protokol, RX/TX thread'leri"], "core"),
        box(560, 40, 190, 92, "UTS", ["Windows HTTP servisi", "POST / GET, config"], "uts"),
        box(800, 40, 180, 92, "Hedef donanım", ["test edilen yazılım", "(gömülü)"], "test"),
        arrow(210, 86, 258, 86, "çağrı", ly=78, lx=214),
        arrow(490, 76, 558, 76, "POST JSON", ly=68, lx=496),
        arrow(558, 100, 492, 100, "GET JSON", dashed=True, ly=118, lx=496),
        arrow(750, 76, 798, 76),
        arrow(798, 100, 752, 100, dashed=True),
        f'<text class="al" x="757" y="150">Ethernet, RS422,</text><text class="al" x="757" y="166">MIL-STD-1553</text>',
    ]
    return svg(1000, 180, "".join(b), "Bağlam: test kodu donanıma UTS üzerinden ulaşır")


def layer_diagram() -> str:
    W = 960
    b = [band(20, 10, W, 64, "Test tarafı", "test"),
         chip(150, 30, 210, "tests/ , examples/", "CommTestCase, HardwareTestCase"),
         chip(380, 30, 250, "projects/<proje>/", "kanallar, aileler, mesajlar, tipler"),
         chip(650, 30, 300, "from asl_testing import ...", "tek giriş: asl_testing/__init__.py"),

         band(20, 90, W, 64, "Giriş ve|servisler", "svc"),
         chip(150, 110, 220, "comm.py  Comm", "katmanları kurar, open / close"),
         chip(390, 110, 260, "services/", "CommLogger, ErrorLog, MonitorService"),
         chip(670, 110, 280, "uts/control.py  UtsControl", "config ve filtre, doğrudan çağrı"),

         band(20, 170, W, 64, "Çalışma|zamanı", "run"),
         chip(150, 190, 150, "TxScheduler", "gönderim, periyot"),
         chip(310, 190, 150, "RxPoller", "yoklama, zaman aşımı"),
         chip(470, 190, 150, "Dispatcher", "tanıma, decode"),
         chip(630, 190, 150, "Transport", "kanal ↔ UTS"),
         chip(790, 190, 160, "UtsClock", "UTS saati tahmini"),

         band(20, 250, W, 64, "Olaylar", "evt"),
         chip(150, 270, 260, "EventBus", "publish / subscribe, abone başına thread"),
         chip(430, 270, 520, "MessageReceived, MessageSent, InvalidReceived, UnknownReceived,",
              "WireReceived, WireSent, RxTimeout, RxRestored, LinkError"),

         band(20, 330, W, 64, "Hat", "uts"),
         chip(150, 350, 400, "protocol/  Protocol: encode / decode / simulate",
              "EthernetProtocol, Rs422Protocol, Mil1553Protocol"),
         chip(570, 350, 380, "uts/  UtsClient: post / get / config / filter",
              "HttpUtsClient (taslak), FakeUtsClient"),

         band(20, 410, W, 64, "Model", "msg"),
         chip(150, 430, 300, "channel/  Channel, ChannelSet, Framing",
              "Ethernet/Rs422/Mil1553Channel, Envelope, Splitter"),
         chip(470, 430, 480, "message/  BaseMessageStructure, FieldType, Signature, Registry",
              "RxState / TxState, MessageHistory, Timing, Direction"),
         arrow(990, 30, 990, 470, ""),
         ]
    text = '<text class="al" x="993" y="250" transform="rotate(90 993 250)" text-anchor="middle">kullanır</text>'
    return svg(1010, 490, "".join(b) + text,
               "Katmanlar: her katman sadece altındakileri kullanır; model katmanı hiçbir şeye bağlı değildir")


def model_diagram() -> str:
    b = [
        box(20, 40, 270, 74, "ctypes.Structure", ["LittleEndianStructure / BigEndianStructure"], "ext"),
        box(20, 150, 270, 110, "BaseMessageStructure", ["pack() / decode() / validate()", "has_new, rx_history, snapshot",
                                                         "on_send / on_receive (callout)", "_channel, _direction, _timing"], "msg"),
        box(20, 300, 270, 92, "ProjectBase (proje)", ["başlık alanları, bayt sırası", "varsayılan kanal / zamanlama"], "msg"),
        box(20, 430, 270, 92, "Family1 / Family2 / Serial2", ["_signature = Signature(...)", "aile başına bir Registry"], "msg"),
        box(20, 560, 270, 74, "request, motor_cmd, diag_log ...", ["mesaj sınıfı: _fields_ (yük)"], "msg"),
        arrow(155, 148, 155, 116), arrow(155, 298, 155, 262), arrow(155, 428, 155, 394), arrow(155, 558, 155, 524),
        '<text class="al" x="162" y="137">türer</text>',

        box(390, 150, 240, 110, "RxState / TxState", ["count, _seen (has_new / has_sent)", "timestamp, errors",
                                                      "RxState.history: MessageHistory"], "run"),
        box(390, 300, 240, 92, "Timing / Direction", ["periyot, tolerans", "RX, TX, BOTH"], "run"),
        box(390, 430, 240, 110, "Signature + Registry", ["Signature: alanlar → offset + mask", "compute(raw) → tek kimlik",
                                                         "Registry: (kanal, kimlik) → nesne"], "run"),
        arrow(292, 205, 388, 205, "nesne başına", ly=197, lx=300),
        arrow(292, 346, 388, 346, "varsayılan", ly=338, lx=306),
        arrow(292, 476, 388, 476, "aile başına", ly=468, lx=304),

        box(680, 150, 300, 110, "FieldType (özel alan)", ["on_init / on_send / on_receive", "after_send, val (on_get / on_set)",
                                                           "_order: çalışma sırası"], "msg"),
        box(680, 300, 135, 80, "LengthType", ["toplam boy"], "msg"),
        box(845, 300, 135, 80, "CounterType", ["her pack +1"], "msg"),
        box(680, 410, 135, 80, "ChecksumType", ["_order = 100"], "msg"),
        box(845, 410, 135, 80, "AsciiType", ["val ↔ str"], "msg"),
        '<line class="ar" x1="830" y1="450" x2="830" y2="262" marker-end="url(#ah)"/>',
        '<line class="ar" x1="815" y1="340" x2="830" y2="340"/><line class="ar" x1="845" y1="340" x2="830" y2="340"/>',
        '<line class="ar" x1="815" y1="450" x2="830" y2="450"/><line class="ar" x1="845" y1="450" x2="830" y2="450"/>',
        '<text class="al" x="836" y="280">türer</text>',
        box(680, 560, 300, 74, "Proje tipleri", ["Length16, Counter8, CRC16, CmdByte"], "test"),
        arrow(830, 558, 830, 492, "türer", lx=836, ly=530),
        '<path class="ar" d="M830,148 V24 H250 V146" marker-end="url(#ah)"/>',
        '<text class="al" x="420" y="18">özel alan, mesajın bir alanı olarak kullanılır</text>',
    ]
    return svg(1000, 650, "".join(b), "Mesaj modeli: hiyerarşi (sol), nesne ve aile bilgileri (orta), özel alan tipleri (sağ)")


def bytes_diagram() -> str:
    xs, w = (20, 300, 580, 860), 190
    names = [("Mesaj nesnesi", ["ctypes düzeni", "alanlar, CRC, uzunluk"], "msg", "message/"),
             ("Mesaj baytları", ["pack(): gövde + CRC", "decode(): geri yazılır"], "msg", "message/ (pack, decode)"),
             ("Hattaki baytlar", ["Envelope: başlık", "Splitter: akış → paket"], "core", "channel/ (Framing)"),
             ("UTS gövdesi (JSON)", ["Protocol.encode", "Protocol.decode"], "uts", "protocol/ (Protocol)")]
    out = []
    for x, (title, lines, kind, module) in zip(xs, names):
        out.append(box(x, 20, w, 92, title, lines, kind))
        out.append(f'<text class="al" x="{x + 4}" y="136">{escape(module)}</text>')
    for (x1, x2), (tx, rx) in zip(zip(xs, xs[1:]), [("pack", "decode"), ("on_send", "on_receive"), ("encode", "decode")]):
        a1, a2 = x1 + w + 2, x2 - 2
        mid = (a1 + a2) / 2
        out.append(f'<line class="ar" x1="{a1}" y1="56" x2="{a2}" y2="56" marker-end="url(#ah)"/>')
        out.append(f'<text class="al" x="{mid}" y="48" text-anchor="middle">{tx}</text>')
        out.append(f'<line class="ar ret" x1="{a2}" y1="84" x2="{a1}" y2="84" marker-end="url(#ah)"/>')
        out.append(f'<text class="al" x="{mid}" y="102" text-anchor="middle">{rx}</text>')
    return svg(1070, 150, "".join(out), "Bayt dönüşümleri: her aşamayı tek bir modül yapar (düz ok TX, kesikli ok RX)")


def tx_sequence() -> str:
    lifelines = [("Test", "test"), ("Comm", "svc"), ("TxScheduler", "run"), ("Mesaj", "msg"),
                 ("Transport", "run"), ("Protocol", "core"), ("UtsClient", "uts"), ("EventBus", "evt")]
    steps = [
        ("Test", "Comm", "send(msg)", "call"),
        ("Comm", "TxScheduler", "send(msg)", "call"),
        ("TxScheduler", "TxScheduler", "_send_lock", "note"),
        ("TxScheduler", "Mesaj", "_pack()", "call"),
        ("Mesaj", "Mesaj", "on_send kancaları", "self"),
        ("Mesaj", "Mesaj", "kopyada: uzunluk, sayaç, CRC", "self"),
        ("Mesaj", "TxScheduler", "raw, image", "ret"),
        ("TxScheduler", "Transport", "send(channel, raw)", "call"),
        ("Transport", "Transport", "envelope.on_send", "self"),
        ("Transport", "Protocol", "encode(wire)", "call"),
        ("Protocol", "Transport", "gövde (dict)", "ret"),
        ("Transport", "UtsClient", "post(path, if, gövde)", "call"),
        ("Transport", "TxScheduler", "wire", "ret"),
        ("TxScheduler", "Mesaj", "_sent(): sayaç, after_send", "call"),
        ("TxScheduler", "EventBus", "WireSent, MessageSent", "call"),
        ("TxScheduler", "Test", "True (hata: False + LinkError)", "ret"),
    ]
    return sequence(lifelines, steps, "Gönderim (TX): tek seferlik send; periyodik gönderimde TxScheduler thread'i aynı send'i çağırır",
                    col=122)


def rx_sequence() -> str:
    lifelines = [("RxPoller", "run"), ("Transport", "run"), ("UtsClient", "uts"), ("Protocol", "core"),
                 ("Framing", "core"), ("Dispatcher", "run"), ("Mesaj", "msg"), ("EventBus", "evt")]
    steps = [
        ("RxPoller", "RxPoller", "her poll_interval", "note"),
        ("RxPoller", "Transport", "poll(adres, kanallar)", "call"),
        ("Transport", "UtsClient", "get(path, if)", "call"),
        ("UtsClient", "Transport", "öğeler", "ret"),
        ("Transport", "Protocol", "decode(öğe)", "call"),
        ("Protocol", "Transport", "bayt + zaman", "ret"),
        ("Transport", "Framing", "split, envelope", "call"),
        ("Framing", "Transport", "kanal, mesaj baytları", "ret"),
        ("Transport", "RxPoller", "RxFrame listesi", "ret"),
        ("RxPoller", "EventBus", "WireReceived", "call"),
        ("RxPoller", "Dispatcher", "dispatch(frame)", "call"),
        ("Dispatcher", "Dispatcher", "signature, sonra kanal", "self"),
        ("Dispatcher", "Mesaj", "decode(raw, ts)", "call"),
        ("Mesaj", "Mesaj", "validate, tek kopya, geçmiş", "self"),
        ("Mesaj", "Dispatcher", "True / False", "ret"),
        ("Dispatcher", "EventBus", "Message / Invalid / UnknownReceived", "call"),
        ("RxPoller", "RxPoller", "zaman aşımı: RxTimeout / RxRestored", "self"),
    ]
    return sequence(lifelines, steps, "Alım (RX): RxPoller thread'i her döngüde bu akışı her adres için çalıştırır",
                    col=122)


def thread_diagram() -> str:
    b = [
        box(20, 20, 225, 150, "Test thread'i", ["alan yazar / okur", "send, start, stop", "has_new, wait_for",
                                                "snapshot, rx_history"], "test"),
        box(265, 20, 225, 150, "TxScheduler thread'i", ["periyodik mesajlar", "_pack, transport.send",
                                                        "_sent, olay yayını"], "run"),
        box(510, 20, 225, 150, "RxPoller thread'i", ["UTS get, decode", "dispatch, geçmiş", "zaman aşımı",
                                                     "msg.on_receive kancaları"], "run"),
        box(755, 20, 225, 150, "Abone thread'leri", ["her subscribe için bir", "kendi kuyruğu", "CommLogger, ErrorLog,",
                                                     "Monitor, comm.on_receive"], "evt"),
        box(20, 210, 960, 120, "Paylaşılan veri ve korunması", [
            "Mesaj nesnesi (RX): decode yeni değerleri ayrı tamponda hazırlar, tek kopyayla yazar → okuyan eski ya da yeni paketi görür",
            "Mesaj nesnesi (TX): _pack özel alanları kopyada hesaplar, sadece değişen özel alanları geri yazar → CRC her zaman pakete uyar",
            "Gönderim: TxScheduler._send_lock → test ve periyodik gönderim sayaç / CRC'yi karıştırmaz",
            "MessageHistory: kilit + koşul değişkeni; RxState / TxState sayaçları tek thread yazar, okuma tek adım",
            "Olaylar: değişmez kayıtlar, baytların kopyasını taşır; abone event.snapshot() ile okur"], "core", title_size=14),
    ]
    return svg(1000, 345, "".join(b), "Thread modeli: mesaj başına thread yok; korumalar GIL'e dayanır")


# ---------------------------------------------------------------------------------------------- page

CSS = """
:root { --bg:#ffffff; --panel:#f6f7f9; --text:#1d2433; --muted:#5b6474; --line:#d9dde4; --accent:#2456c7;
  --accent-soft:#e8efff; --code-bg:#0f1420; --code-text:#e6ebf5; --warn-bg:#fff6e0; --warn-line:#b07d00;
  --c-test:#eef0f3; --c-test-l:#8a93a3; --c-msg:#e8efff; --c-msg-l:#4c74d0; --c-run:#e7f5ee; --c-run-l:#2f8f5b;
  --c-core:#f3ebfb; --c-core-l:#7a3eb1; --c-uts:#fff1e3; --c-uts-l:#c06a12; --c-evt:#e6f6f7; --c-evt-l:#178a93;
  --c-svc:#fdeef0; --c-svc-l:#b4405a; --c-ext:#f6f7f9; --c-ext-l:#9aa3b2;
  --font-body: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#0e1116; --panel:#161b23; --text:#e4e8ef; --muted:#9aa4b5; --line:#2c3440; --accent:#7ea6ff;
  --accent-soft:#1b2740; --code-bg:#090c12; --code-text:#dfe6f3; --warn-bg:#2b2412; --warn-line:#e0a526;
  --c-test:#1b2029; --c-test-l:#6b7587; --c-msg:#16223a; --c-msg-l:#7ea6ff; --c-run:#13261d; --c-run-l:#4fc287;
  --c-core:#241a31; --c-core-l:#c39bff; --c-uts:#2b1f12; --c-uts-l:#f0a050; --c-evt:#10272a; --c-evt-l:#4cc3cc;
  --c-svc:#2c171c; --c-svc-l:#f08aa0; --c-ext:#161b23; --c-ext-l:#6b7587; color-scheme:dark; } }
:root[data-theme="dark"] {
  --bg:#0e1116; --panel:#161b23; --text:#e4e8ef; --muted:#9aa4b5; --line:#2c3440; --accent:#7ea6ff;
  --accent-soft:#1b2740; --code-bg:#090c12; --code-text:#dfe6f3; --warn-bg:#2b2412; --warn-line:#e0a526;
  --c-test:#1b2029; --c-test-l:#6b7587; --c-msg:#16223a; --c-msg-l:#7ea6ff; --c-run:#13261d; --c-run-l:#4fc287;
  --c-core:#241a31; --c-core-l:#c39bff; --c-uts:#2b1f12; --c-uts-l:#f0a050; --c-evt:#10272a; --c-evt-l:#4cc3cc;
  --c-svc:#2c171c; --c-svc-l:#f08aa0; --c-ext:#161b23; --c-ext-l:#6b7587; color-scheme:dark; }
* { box-sizing:border-box } html { scroll-behavior:smooth }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior:auto } }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.6 var(--font-body) }
a { color:var(--accent) }
.layout { display:grid; grid-template-columns:250px minmax(0,1fr) }
nav { position:sticky; top:0; height:100vh; overflow-y:auto; background:var(--panel); border-right:1px solid var(--line);
  padding:20px 14px }
nav .brand { font-weight:700; margin:0 } nav .sub { color:var(--muted); font-size:13px; margin:2px 0 14px }
nav a { display:block; padding:4px 8px; border-radius:6px; color:var(--text); text-decoration:none; font-size:14px }
nav a:hover, nav a:focus-visible { background:var(--accent-soft); color:var(--accent); outline:none }
main { padding:34px clamp(16px,4vw,48px) 90px; max-width:1120px; min-width:0 }
h1 { font-size:30px; line-height:1.25; margin:0 0 6px; text-wrap:balance }
p.lead { color:var(--muted); font-size:17px; margin-top:0; max-width:72ch }
h2 { font-size:23px; margin:48px 0 10px; padding-top:12px; border-top:1px solid var(--line); text-wrap:balance }
h3 { font-size:17px; margin:24px 0 8px }
p, li { max-width:76ch }
code { font:13.5px var(--font-mono); background:var(--panel); border:1px solid var(--line); padding:1px 5px; border-radius:4px }
pre { background:var(--code-bg); color:var(--code-text); padding:14px 16px; border-radius:10px; overflow-x:auto;
  font:13px/1.55 var(--font-mono) }
pre code { background:none; border:0; padding:0; color:inherit }
.tw { overflow-x:auto; margin:10px 0 18px }
table { width:100%; border-collapse:collapse; font-size:14.5px }
th, td { text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line) }
th { color:var(--muted); font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap }
td code { white-space:nowrap }
.box { border-radius:8px; padding:12px 16px; margin:14px 0; background:var(--accent-soft); border-left:3px solid var(--accent) }
.box.warn { background:var(--warn-bg); border-left-color:var(--warn-line) }
.legend { display:flex; flex-wrap:wrap; gap:8px 16px; font-size:13px; color:var(--muted); margin:6px 0 0 }
.legend span::before { content:""; display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px;
  vertical-align:-1px; border:1.5px solid var(--l); background:var(--f) }
figure.dia { margin:16px 0 22px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px;
  overflow-x:auto }
figure.dia svg { width:100%; height:auto; min-width:760px; display:block }
figcaption { color:var(--muted); font-size:13px; margin-top:6px; text-align:center }
svg .b { stroke-width:1.5 }
svg .test { fill:var(--c-test); stroke:var(--c-test-l) } svg .msg { fill:var(--c-msg); stroke:var(--c-msg-l) }
svg .run { fill:var(--c-run); stroke:var(--c-run-l) } svg .core { fill:var(--c-core); stroke:var(--c-core-l) }
svg .uts { fill:var(--c-uts); stroke:var(--c-uts-l) } svg .evt { fill:var(--c-evt); stroke:var(--c-evt-l) }
svg .svc { fill:var(--c-svc); stroke:var(--c-svc-l) } svg .ext { fill:var(--c-ext); stroke:var(--c-ext-l); stroke-dasharray:5 4 }
svg .band { stroke-width:1.2 }
svg .chip { fill:var(--bg); stroke:var(--line); stroke-width:1.2 }
svg .bt, svg .lt { fill:var(--text); font:600 14px var(--font-body) }
svg .lt { font-size:13px }
svg .bl { fill:var(--muted); font:12px var(--font-body) }
svg .bandt { fill:var(--text); font:600 12.5px var(--font-body) }
svg .ct { fill:var(--text); font:600 12.5px var(--font-mono) } svg .cs { fill:var(--muted); font:11.5px var(--font-body) }
svg .ar { stroke:var(--accent); stroke-width:1.5; fill:none } svg .ar.ret { stroke-dasharray:5 4 }
svg .ahd { fill:var(--accent) } svg .al { fill:var(--text); font:12px var(--font-body) }
svg .life { stroke:var(--line); stroke-dasharray:3 4 }
svg .note { fill:var(--warn-bg); stroke:var(--warn-line); stroke-width:1 } svg .nt { fill:var(--text); font:11.5px var(--font-body) }
@media (max-width:820px) { .layout { grid-template-columns:minmax(0,1fr) }
  nav { position:static; height:auto; border-right:0; border-bottom:1px solid var(--line) } h1 { font-size:25px } }
"""

LEGEND = ('<div class="legend">'
          '<span style="--f:var(--c-test);--l:var(--c-test-l)">test / proje</span>'
          '<span style="--f:var(--c-svc);--l:var(--c-svc-l)">giriş, servis</span>'
          '<span style="--f:var(--c-run);--l:var(--c-run-l)">çalışma zamanı</span>'
          '<span style="--f:var(--c-evt);--l:var(--c-evt-l)">olaylar</span>'
          '<span style="--f:var(--c-core);--l:var(--c-core-l)">protokol, çerçeveleme</span>'
          '<span style="--f:var(--c-uts);--l:var(--c-uts-l)">UTS</span>'
          '<span style="--f:var(--c-msg);--l:var(--c-msg-l)">mesaj modeli</span></div>')

NAV = [("genel", "Genel bakış"), ("katman", "Katmanlar"), ("sorumluluk", "Kim ne yapar"), ("model", "Mesaj modeli"),
       ("bayt", "Baytların yolu"), ("tx", "Gönderim akışı"), ("rx", "Alım akışı"), ("thread", "Thread modeli"),
       ("olay", "Olaylar"), ("genisletme", "Genişletme noktaları"), ("klasor", "Klasör yapısı"), ("acik", "Açık noktalar")]


def table(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="tw"><table><tr>{th}</tr>{body}</table></div>'


def page() -> str:
    responsibility = table(["Modül / sınıf", "Sorumluluğu", "Bilmediği", "Kullanan"], [
        ["<code>Comm</code>", "Katmanları kurar, thread'leri açar / kapatır; test kodunun tek giriş noktası "
         "(send, start, wait_new, wait_for, subscribe, control).", "Paket biçimi, UTS JSON'u", "Test kodu"],
        ["<code>BaseMessageStructure</code>", "Alanlar, varsayılanlar, pack (TX baytları), validate / decode (RX), sayaçlar, geçmiş, kancalar.",
         "UTS, kanal biçimi, thread'ler", "Proje tanımı, Dispatcher, TxScheduler"],
        ["<code>FieldType</code> ve alt tipleri", "Özel alanın yaşam döngüsü: uzunluk, sayaç, CRC, ASCII, komut bitleri.",
         "Diğer alanlar, UTS", "BaseMessageStructure"],
        ["<code>Signature</code>", "Alan listesinden offset + mask; paketten tek kimlik.", "Kanal, UTS", "Registry, UtsControl"],
        ["<code>Registry</code>", "Ailenin nesneleri; (kanal, signature) → nesne; zaman aşımı listesi.", "Paket içeriği",
         "BaseMessageStructure, Dispatcher, RxPoller"],
        ["<code>RxState</code> / <code>TxState</code>", "Sayaçlar ve zamanlar (has_new, has_sent, rx_age).", "Mesaj içeriği", "BaseMessageStructure"],
        ["<code>MessageHistory</code>", "Son N alınan paketin kaydı; mark / since / wait_for.", "Kanal, UTS", "BaseMessageStructure, Comm"],
        ["<code>Channel</code> / <code>ChannelSet</code>", "Protokol tipi + interface + framing; kanal kuralları.", "Mesajlar", "Proje, Transport"],
        ["<code>Envelope</code> / <code>Splitter</code>", "Başlık ekleme / çıkarma; akıştan paket ayırma.", "Mesaj, UTS JSON'u", "Transport"],
        ["<code>Protocol</code> alt sınıfları", "Hattaki baytlar ↔ UTS gövdesi / öğesi (encode, decode, simulate).",
         "Mesaj, signature, envelope, zamanlama", "Transport, FakeUtsClient"],
        ["<code>UtsClient</code>", "UTS'e HTTP ile ulaşmak (post, get, config, filter).", "Gövdenin anlamı", "Transport, UtsControl"],
        ["<code>FakeUtsClient</code>", "UTS yerine geçer: gönderilenleri tutar, inject ile cihazı oynar.", "Gerçek zaman davranışı",
         "Testler, örnekler"],
        ["<code>UtsControl</code>", "Interface ayarı ve alım filtresi; testten doğrudan, senkron.", "RX / TX thread'leri", "Comm.control"],
        ["<code>Transport</code>", "Kanal ↔ UTS: envelope, protokol, splitter, kanal tespiti.", "Mesaj, signature, zamanlama",
         "TxScheduler, RxPoller"],
        ["<code>TxScheduler</code>", "Tek seferlik ve periyodik gönderim; gönderim kilidi; TX olayları.", "UTS JSON'u", "Comm"],
        ["<code>RxPoller</code>", "Yoklama döngüsü, WireReceived, RX zaman aşımı.", "Mesaj tanıma kuralı", "Comm"],
        ["<code>Dispatcher</code>", "Paketin mesajını bulur, decode eder, sonuç olayını yayınlar; bilinmeyenleri tutar.",
         "UTS, kanal biçimi", "RxPoller"],
        ["<code>UtsClock</code>", "Paketlerdeki UTS zamanından şu anki UTS zamanını tahmin eder.", "Mesajlar", "RxPoller"],
        ["<code>EventBus</code>", "Olayları abonelere dağıtır; abone başına kuyruk ve thread.", "Olayın içeriği", "Bütün katmanlar"],
        ["<code>CommLogger</code> / <code>ErrorLog</code> / <code>MonitorService</code>",
         "CSV kaydı / hata dosyası / tarayıcıda izleme; olaylardan beslenir.", "Runtime'ın içi", "Test kodu"],
    ])
    events = table(["Olay", "Yayınlayan", "Ne zaman"], [
        ["<code>WireSent</code>, <code>MessageSent</code>", "TxScheduler", "Başarılı gönderimden sonra"],
        ["<code>LinkError</code>", "TxScheduler / RxPoller", "UTS isteği başarısız"],
        ["<code>WireReceived</code>", "RxPoller", "Her gelen paket, tanınmadan önce"],
        ["<code>MessageReceived</code>", "Dispatcher", "Paket bir mesaja ait ve geçerli"],
        ["<code>InvalidReceived</code>", "Dispatcher", "Mesaja ait, boy / uzunluk / CRC tutmuyor"],
        ["<code>UnknownReceived</code>", "Dispatcher", "Hiçbir mesaja ait değil"],
        ["<code>RxTimeout</code>, <code>RxRestored</code>", "RxPoller", "Periyodik RX mesajı gecikti / yeniden geldi"],
    ])
    extend = table(["Ne eklenir", "Nerede", "Ne yazılır"], [
        ["Yeni hat tipi (ör. CAN)", "<code>protocol/</code>, <code>channel/channel.py</code>, <code>protocol/defaults.py</code>",
         "<code>Protocol</code> alt sınıfı (path, encode, decode, simulate), kanal sınıfı, varsayılan eşleme"],
        ["Yeni özel alan (ör. farklı CRC)", "Projenin <code>types.py</code>'si", "<code>ChecksumType</code> / <code>FieldType</code> alt sınıfı"],
        ["Proje başlığı", "Projenin <code>framing.py</code>'si", "<code>Envelope</code> alt sınıfı (on_send, on_receive, offset)"],
        ["Akış ayırma", "Projenin <code>framing.py</code>'si", "<code>Splitter</code> alt sınıfı (split)"],
        ["Yeni servis (ör. simülasyon düğümü)", "<code>services/</code>", "<code>comm.subscribe(...)</code> ile olay dinleyen sınıf"],
        ["Gerçek UTS", "<code>uts/http.py</code>", "<code>post</code>, <code>get</code>, config ve filtre çağrıları"],
    ])
    tree = """asl_testing/
  __init__.py        tek import yüzeyi
  comm.py            Comm
  message/           base, fields, signature, registry, state, history, timing
  channel/           channel (Channel, ChannelSet, kanal tipleri), framing (Envelope, Splitter)
  protocol/          base (Protocol), ethernet, rs422, mil1553, defaults
  uts/               client (UtsClient), http, fake, control (UtsControl), filters
  runtime/           transport, rx (RxPoller), tx (TxScheduler), dispatcher, clock
  events/            bus (EventBus), types
  services/          history (CommLogger), errors (ErrorLog), monitor/
projects/example_project/   channels, header (proje, aileler), messages, types, framing
tests/               base (CommTestCase, HardwareTestCase), test_*.py, conftest.py
examples/            example, example_send_receive, monitor_demo
docs/                USAGE, manual.html, TEST_API, DESIGN, KNOWN_ISSUES, architecture.html
tools/               build_architecture.py (bu sayfa)"""

    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in NAV)
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="author" content="İsmail Baysal">
<title>asl_testing Mimarisi</title><style>{CSS}</style></head>
<body><div class="layout">
<nav aria-label="İçindekiler"><p class="brand">asl_testing</p><p class="sub">Mimari, v2.1 · İsmail Baysal</p>{nav}</nav>
<main>
<h1>asl_testing mimarisi</h1>
<p class="lead">Modüller, aralarındaki ilişkiler ve her birinin sorumluluğu. Kod dalı <code>v2.1-base</code>. Kullanım için
<code>docs/USAGE.md</code> ve <code>docs/manual.html</code>, bilinen sorunlar için <code>docs/KNOWN_ISSUES.md</code>.</p>

<h2 id="genel">Genel bakış</h2>
<p>asl_testing, donanımda çalışan yazılımı test etmek için mesaj gönderip alan bir Python altyapısıdır. Donanıma doğrudan değil,
UTS adlı Windows HTTP servisi üzerinden ulaşır. Mesajlar ctypes yapılarıyla tanımlanır; altyapı paketleme, CRC, uzunluk, sayaç,
periyodik gönderim, alım, tanıma ve zaman aşımı işlerini test kodundan alır.</p>
{context_diagram()}
<ul>
<li><b>Test kodu</b> mesaj nesneleriyle ve <code>Comm</code> ile konuşur; her şeyi <code>from asl_testing import ...</code> ile alır.</li>
<li><b>Proje</b> (<code>projects/</code>) kanalları, mesaj ailelerini, mesajları ve özel alan tiplerini tanımlar.</li>
<li><b>Altyapı</b> iki thread çalıştırır: biri gönderir (TxScheduler), biri UTS'i yoklar (RxPoller). Sonuçlar olay olarak yayınlanır.</li>
</ul>
{LEGEND}

<h2 id="katman">Katmanlar</h2>
<p>Her katman yalnızca altındaki katmanları kullanır. Model katmanı (mesaj, kanal) hiçbir şeye bağlı değildir; proje tanımı sadece onu kullanır.</p>
{layer_diagram()}

<h2 id="sorumluluk">Kim ne yapar</h2>
{responsibility}

<h2 id="model">Mesaj modeli</h2>
{model_diagram()}
<ul>
<li><b>Proje</b> doğrudan <code>BaseMessageStructure</code>'dan türer: bayt sırası (<code>LittleEndianStructure</code> /
<code>BigEndianStructure</code>), başlık alanları, varsayılan kanal ve zamanlama.</li>
<li><b>Aile</b> kendi <code>_signature</code>'ını tanımlar ve kendi <code>Registry</code>'sini açar. <code>_signature = None</code>
yazan aile kanalıyla tanınır (kanal başına bir RX mesajı).</li>
<li><b>Mesaj sınıfı</b> yük alanlarını ekler, son alan checksum'dır. Değişken boyda <code>_variable_size = True</code> ve <code>body_size()</code>.</li>
<li><b>Nesne</b> oluşturulunca kendini registry'ye ekler. Aynı sınıf, kanal, signature ve yönde yeni nesne eskisinin yerini alır.</li>
<li><b>Özel alanlar</b> <code>_order</code> sırasıyla çalışır; checksum (100) her zaman en sondadır.</li>
</ul>

<h2 id="bayt">Baytların yolu</h2>
{bytes_diagram()}
{table(["Protokol", "UTS'e giden / gelen", "Not"], [
        ["<code>EthernetProtocol</code>", "<code>{{\"message\": [b0, b1, ...], \"timestamp\": t}}</code>", ""],
        ["<code>Rs422Protocol</code>", "<code>{{\"message\": [b0, b1, ...], \"timestamp\": t}}</code>", "Öğe akış parçası olabilir; splitter böler"],
        ["<code>Mil1553Protocol</code>", "<code>{{\"message\": [rt, subnet, word_count, word, ...]}}</code>",
         "16 bitlik değerler; <code>byte_order</code> yapının endian'ıyla aynı olmalı"],
    ])}

<h2 id="tx">Gönderim akışı</h2>
{tx_sequence()}
<p>Periyodik mesajda TxScheduler thread'i zamanı gelen her mesaj için aynı <code>send</code>'i çağırır; bir sonraki zaman
<code>önceki zaman + periyot</code> olarak ilerler, gecikme birikmez.</p>

<h2 id="rx">Alım akışı</h2>
{rx_sequence()}
<p>Tanıma sırası: önce bütün projelerde signature eşleşmesi, sonra kanalıyla tanınan aile. Eşleşme yoksa paket
<code>comm.unknown</code> listesine ve <code>UnknownReceived</code> olayına gider. Bir paketin işlenmesinde hata olursa
loglanır, döngü sıradaki pakete geçer.</p>

<h2 id="thread">Thread modeli</h2>
{thread_diagram()}

<h2 id="olay">Olaylar</h2>
<p>Olaylar değişmez kayıtlardır ve baytların kopyasını taşır. Her abonenin kendi kuyruğu ve thread'i vardır; yavaş bir abone
yayınlayanı ya da diğer aboneleri bekletmez. Sıra: önce hat olayı (<code>Wire*</code>), sonra mesaj olayı.</p>
{events}

<h2 id="genisletme">Genişletme noktaları</h2>
{extend}

<h2 id="klasor">Klasör yapısı</h2>
<pre><code>{escape(tree)}</code></pre>

<h2 id="acik">Açık noktalar</h2>
<ul>
<li><b>Gerçek UTS:</b> <code>HttpUtsClient</code> taslak; JSON alan adları, zaman birimi, config / filtre gövdeleri UTS API'sine bağlı.</li>
<li><b>Kanal = interface:</b> bugün aynı interface'te birden fazla kanal (başlıklı / başlıksız) tanımlanabiliyor. Her interface'in tek kanal
olması kararlaştırıldı; bunun sadeleştireceği kod ayrı bir adımda uygulanacak.</li>
<li><b>Protokol nesnesi iki yerde:</b> <code>Comm(protocols=...)</code> ile verilen nesneyi <code>FakeUtsClient</code> bilmiyor; tek kaynağa indirilmeli.</li>
<li><b>K3:</b> özel alan tipleri big-endian mesajda little-endian kalıyor (1553 big-endian projeyi etkiler).</li>
<li>Diğerleri: <code>docs/KNOWN_ISSUES.md</code>.</li>
</ul>
</main></div></body></html>
"""


def fragment(html: str) -> str:
    """The page without the document wrapper: <title>, <meta>, <style> and the body content."""
    head = html[html.index("<meta name=\"author\""):html.index("</head>")]
    body = html[html.index("<body>") + len("<body>"):html.index("</body>")]
    return head + "\n" + body


if __name__ == "__main__":
    import sys
    html = page()
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(fragment(html), encoding="utf-8")
        print(f"wrote {sys.argv[1]}")
