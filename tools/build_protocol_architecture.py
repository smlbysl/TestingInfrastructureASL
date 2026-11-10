"""Builds the architecture page (protocol contract) as one self-contained HTML file."""
import html
import sys

OUT = sys.argv[1]
E = html.escape


# ---------------------------------------------------------------- SVG helpers

def box(x, y, w, h, title, lines=(), cls="b", title_cls="bt", dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}"{dash}/>',
           f'<text x="{x + w / 2}" y="{y + 22}" class="{title_cls}" text-anchor="middle">{E(title)}</text>']
    for i, line in enumerate(lines):
        out.append(f'<text x="{x + 12}" y="{y + 46 + i * 18}" class="bl">{E(line)}</text>')
    return "".join(out)


def arrow(x1, y1, x2, y2, label="", mid=None, cls="ar", lab_dy=-6):
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" marker-end="url(#ah)"/>']
    if label:
        mx, my = mid or ((x1 + x2) / 2, (y1 + y2) / 2)
        out.append(f'<text x="{mx}" y="{my + lab_dy}" class="al" text-anchor="middle">{E(label)}</text>')
    return "".join(out)


DEFS = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ahd"/></marker></defs>')


def svg(w, h, body, label):
    return (f'<figure class="dia"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{E(label)}">{DEFS}{body}</svg>'
            f'<figcaption>{E(label)}</figcaption></figure>')


def sequence(parts, steps, label, width=920):
    """parts: [(name, highlight)], steps: [(from, to, text)] or ("note", idx, text)."""
    n = len(parts)
    gap = width / n
    xs = [gap * i + gap / 2 for i in range(n)]
    height = 70 + len(steps) * 38 + 30
    out = []
    for i, (name, hl) in enumerate(parts):
        cls = "bp" if hl else "b"
        out.append(f'<rect x="{xs[i] - 78}" y="10" width="156" height="34" rx="7" class="{cls}"/>')
        out.append(f'<text x="{xs[i]}" y="32" class="bt" text-anchor="middle">{E(name)}</text>')
        out.append(f'<line x1="{xs[i]}" y1="44" x2="{xs[i]}" y2="{height - 10}" class="life"/>')
    y = 74
    for step in steps:
        if step[0] == "note":
            _, i, text = step
            out.append(f'<text x="{xs[i] + 8}" y="{y}" class="note">{E(text)}</text>')
        else:
            a, b, text = step
            if a == b:
                x = xs[a]
                out.append(f'<path d="M{x},{y - 8} h34 v14 h-30" class="ar" fill="none" marker-end="url(#ah)"/>')
                out.append(f'<text x="{x + 42}" y="{y + 2}" class="al">{E(text)}</text>')
            else:
                x1, x2 = xs[a], xs[b]
                dx = 6 if x2 > x1 else -6
                cls = "ar" if x2 > x1 else "ar ret"
                out.append(arrow(x1 + dx, y, x2 - dx, y, text, cls=cls))
        y += 38
    return svg(width, height, "".join(out), label)


# ---------------------------------------------------------------- diagrams

components = svg(1000, 330, "".join([
    box(10, 110, 120, 70, "Test kodu", ["mesajlar"]),
    box(160, 110, 140, 70, "Comm", ["send / start", "wait / olaylar"]),
    box(330, 90, 180, 110, "Kanal", ["ad, interface", "protokol nesnesi", "kayıtlı mesajlar", "tanıma kuralı"]),
    box(580, 40, 230, 210, "Protokol", ["(başka ekip / kara kutu)", "", "adres tanımı", "TX: encode", "RX: decode",
                                       "UTS adaptörü", "adaptör config'i", "isteğe bağlı: simulate"],
        cls="bp", dashed=True),
    box(840, 110, 150, 70, "UTS istemcisi", ["post / get", "config, JSON"]),
    box(330, 250, 180, 66, "Mesaj", ["BaseMessageStructure", "(değişmiyor)"]),
    arrow(130, 145, 158, 145),
    arrow(300, 145, 328, 145),
    arrow(510, 128, 578, 128, "Giden", lab_dy=-8),
    arrow(578, 166, 512, 166, "Gelen", lab_dy=20),
    arrow(810, 145, 838, 145),
    arrow(420, 200, 420, 248, "decode / pack", mid=(468, 228)),
]), "Şekil 1. Bileşenler: çekirdek (düz kutular) ve protokol (kesikli kutu)")

contract = svg(960, 380, "".join([
    box(10, 10, 225, 150, "Adres", ["protokol tanımlar", "değişmez, karşılaştırılır", "ör. node=5 subnet=3",
                                    "ör. can_id=0x123", "düz Ethernet: boş"]),
    box(245, 10, 225, 150, "Giden (TX girdisi)", ["adres", "veri: bytes", "(mesajın baytları)", "mesaj adı (log için)"]),
    box(480, 10, 225, 150, "UTS isteği (TX çıktısı)", ["gövde: dict (JSON)", "uç: protokolün path'i", "+ kanalın interface'i"]),
    box(715, 10, 235, 150, "UTS öğesi (RX girdisi)", ["GET cevabındaki bir öğe", "dict (JSON)", "biçimini protokol bilir"]),
    box(245, 200, 225, 150, "Gelen (RX çıktısı)", ["adres", "veri: bytes", "zaman: saniye (UTS)", "bir öğeden 0..n tane"]),
    box(480, 200, 470, 150, "Protokol (arayüz)", ["path, address_fields, config",
                                                  "make_address(**alanlar) -> Adres",
                                                  "encode(Giden) -> UTS isteği",
                                                  "decode(UTS öğesi) -> list[Gelen]",
                                                  "configure(uts, interface)    isteğe bağlı",
                                                  "check / reset / simulate     isteğe bağlı"], cls="bp"),
]), "Şekil 2. Sözleşmedeki veri modelleri: çekirdek ile protokol arasında sadece bunlar geçer")

channel_model = svg(940, 250, "".join([
    box(10, 20, 300, 210, "Kanal", ["name           \"BUS_A\"", "interface      1", "protocol       protokol nesnesi",
                                   "                (config'i içinde)", "messages       kayıtlı mesajlar",
                                   "", "send(mesaj)", "receive(UTS öğesi)", "open() / close()"]),
    box(350, 20, 280, 210, "Kayıt (kanalın içinde)", ["anahtar: (adres, imza)", "imzasız mesaj: (adres, -)",
                                                    "", "tanıma sırası:", " 1. adres", " 2. imza (veri içinde)",
                                                    " 3. adresteki tek mesaj", " 4. yoksa: bilinmeyen"]),
    box(670, 20, 260, 210, "Mesaj (değişmiyor)", ["BaseMessageStructure", "alanlar, imza, özel alanlar",
                                                   "pack() -> bytes", "decode(bytes)", "geçmiş, snapshot",
                                                   "", "yeni: adres alanları", "(node=, subnet=, can_id=)"]),
    arrow(310, 125, 348, 125),
    arrow(630, 125, 668, 125),
]), "Şekil 3. Kanal ne tutar")

tx_seq = sequence(
    [("Test", False), ("Kanal", False), ("Mesaj", False), ("Protokol", True), ("UTS istemcisi", False)],
    [(0, 1, "send(mesaj)"),
     (1, 2, "pack()"),
     (2, 1, "veri (bytes)"),
     (1, 3, "check(veri)        isteğe bağlı"),
     (1, 3, "encode(Giden: adres, veri)"),
     (3, 1, "UTS isteği (gövde)"),
     (1, 4, "post(path, interface, gövde)"),
     (4, 1, "tamam / hata"),
     ("note", 1, "başarılıysa: sayaç, geçmiş, olay"),
     ],
    "Şekil 4. TX akışı: protokol mesajı değil, adres + baytları alır")

rx_seq = sequence(
    [("RX döngüsü", False), ("UTS istemcisi", False), ("Kanal", False), ("Protokol", True), ("Mesaj", False)],
    [(0, 1, "get(path, interface)"),
     (1, 0, "UTS öğeleri"),
     (0, 2, "receive(öğe)"),
     (2, 3, "decode(öğe)"),
     (3, 2, "list[Gelen] (adres, veri, zaman)"),
     (2, 2, "kayıt: adres -> imza"),
     (2, 4, "decode(veri, zaman)"),
     (4, 2, "geçerli / geçersiz"),
     ("note", 2, "olay: alındı / geçersiz / bilinmeyen"),
     ],
    "Şekil 5. RX akışı: protokol öğeyi çözer, mesajı kanal bulur")

open_seq = sequence(
    [("Comm", False), ("Kanal", False), ("Protokol", True), ("UTS istemcisi", False)],
    [(0, 1, "open()"),
     (1, 2, "configure(uts, interface)"),
     (2, 3, "set_config(... protokolün config'i ...)"),
     (3, 2, "tamam / UtsError"),
     ("note", 1, "close(): protokol.reset()  (yarım paket vs.)"),
     ],
    "Şekil 6. Açılış: protokol kendi UTS ayarlarını yapar", width=760)


# ---------------------------------------------------------------- page

CSS = """
:root { --bg:#ffffff; --panel:#f6f7f9; --text:#1d2433; --muted:#5b6474; --line:#d9dde4; --accent:#2456c7;
  --accent-soft:#e8efff; --proto:#7a3eb1; --proto-soft:#f3ebfb; --code-bg:#0f1420; --code-text:#e6ebf5;
  --warn-bg:#fff6e0; --warn-line:#d89a00; --ok-bg:#e9f7ef; --ok-line:#2a9d5c; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#0e1116; --panel:#161b23; --text:#e4e8ef; --muted:#9aa4b5; --line:#2c3440; --accent:#7ea6ff;
  --accent-soft:#1b2740; --proto:#c39bff; --proto-soft:#251b33; --code-bg:#090c12; --code-text:#dfe6f3;
  --warn-bg:#2b2412; --warn-line:#e0a526; --ok-bg:#12261b; --ok-line:#3fbf7a; } }
:root[data-theme="dark"] { --bg:#0e1116; --panel:#161b23; --text:#e4e8ef; --muted:#9aa4b5; --line:#2c3440;
  --accent:#7ea6ff; --accent-soft:#1b2740; --proto:#c39bff; --proto-soft:#251b33; --code-bg:#090c12;
  --code-text:#dfe6f3; --warn-bg:#2b2412; --warn-line:#e0a526; --ok-bg:#12261b; --ok-line:#3fbf7a; }
* { box-sizing:border-box } html { scroll-behavior:smooth }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif }
.layout { display:grid; grid-template-columns:250px minmax(0,1fr) }
nav { position:sticky; top:0; height:100vh; overflow-y:auto; background:var(--panel); border-right:1px solid var(--line); padding:20px 14px }
nav .brand { font-weight:700; margin:0 } nav .sub { color:var(--muted); font-size:13px; margin:2px 0 14px }
nav a { display:block; padding:4px 8px; border-radius:6px; color:var(--text); text-decoration:none; font-size:14px }
nav a:hover { background:var(--accent-soft); color:var(--accent) }
main { padding:34px clamp(16px,5vw,60px) 90px; max-width:1000px; min-width:0 }
h1 { font-size:30px; margin:0 0 6px } p.lead { color:var(--muted); font-size:17px; margin-top:0 }
h2 { font-size:23px; margin:48px 0 10px; padding-top:12px; border-top:1px solid var(--line) }
h3 { font-size:17px; margin:24px 0 8px }
code { font:13.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; background:var(--panel); border:1px solid var(--line);
  padding:1px 5px; border-radius:4px }
pre { background:var(--code-bg); color:var(--code-text); padding:14px 16px; border-radius:10px; overflow-x:auto;
  font:13.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace }
pre code { background:none; border:0; padding:0; color:inherit }
table { width:100%; border-collapse:collapse; margin:10px 0 18px; font-size:14.5px; display:block; overflow-x:auto }
th, td { text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line) }
th { color:var(--muted); font-size:12.5px; text-transform:uppercase; letter-spacing:.04em }
.box { border-radius:8px; padding:12px 16px; margin:14px 0 }
.note { background:var(--accent-soft); border-left:3px solid var(--accent) }
.warn { background:var(--warn-bg); border-left:3px solid var(--warn-line) }
.ok { background:var(--ok-bg); border-left:3px solid var(--ok-line) }
.box strong { display:block; margin-bottom:2px }
.tag { font-size:11.5px; padding:1px 7px; border-radius:99px; white-space:nowrap }
.t-req { background:var(--accent-soft); color:var(--accent) } .t-opt { background:var(--panel); color:var(--muted); border:1px solid var(--line) }
.t-core { background:var(--accent-soft); color:var(--accent) } .t-proto { background:var(--proto-soft); color:var(--proto) }
figure.dia { margin:16px 0 22px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px; overflow-x:auto }
figure.dia svg { width:100%; height:auto; min-width:560px; display:block }
figcaption { color:var(--muted); font-size:13px; margin-top:6px; text-align:center }
svg .b { fill:var(--bg); stroke:var(--line); stroke-width:1.5 }
svg .bp { fill:var(--proto-soft); stroke:var(--proto); stroke-width:1.5 }
svg .bt { fill:var(--text); font:600 14px system-ui,sans-serif }
svg .bl { fill:var(--muted); font:12.5px ui-monospace,Menlo,Consolas,monospace; white-space:pre }
svg .ar { stroke:var(--accent); stroke-width:1.6 } svg .ar.ret { stroke-dasharray:5 4 } svg .ar.dim { stroke:var(--line) }
svg .ahd { fill:var(--accent) } svg .al { fill:var(--text); font:12.5px system-ui,sans-serif }
svg .life { stroke:var(--line); stroke-dasharray:3 4 } svg .note { fill:var(--muted); font:italic 12.5px system-ui,sans-serif }
.q { counter-increment:q; border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:10px 0 }
.q h4 { margin:0 0 4px; font-size:15.5px } .q h4::before { content:"Soru " counter(q) ": "; color:var(--accent) }
.q p { margin:4px 0 } .muted { color:var(--muted) }
@media (max-width:820px) { .layout { grid-template-columns:minmax(0,1fr) } nav { position:static; height:auto;
  border-right:0; border-bottom:1px solid var(--line) } h1 { font-size:25px } }
"""

nav_items = [("ozet", "Özet"), ("sinirlar", "Amaç ve sınırlar"), ("bilesenler", "Bileşenler"),
             ("sozlesme", "Sözleşme: veri modelleri"), ("protokol", "Protokol arayüzü"), ("kanal", "Kanal ne tutar"),
             ("mesaj", "Mesaj (BaseMessageStructure)"), ("akis", "Akışlar"), ("hatalar", "Hatalar ve sorumluluk"),
             ("bilinen", "Bilinen protokoller"), ("disinda", "Bilerek dışarıda"), ("sorular", "Karar bekleyenler"),
             ("isimler", "Ek: isimler")]

body = f"""
<h1>Protokol arayüzü: mimari taslak</h1>
<p class="lead">Protokolün iç yapısından bağımsız bir sözleşme. Protokolü başka bir ekip geliştiriyormuş gibi düşünüldü:
çekirdek, protokolün içini bilmeden onu nasıl kullanır, protokol çekirdekten ne alır, ne verir.</p>
<p class="muted">Durum: taslak, kod değişikliği yok. İç tasarım bir sonraki adımda bilinen protokollerden (Ethernet, RS422, 1553, CAN) ilerleyerek yapılacak.</p>

<h2 id="ozet">Özet</h2>
<ul>
  <li><b>Protokol bir kara kutudur.</b> Bir bus türünün TX ve RX kuralını, UTS'e nasıl yazılacağını (UTS adaptörü) ve UTS ayarlarını (adaptör config'i) içerir.</li>
  <li><b>Çekirdek protokolün içini bilmez.</b> Protokole sadece <i>adres + baytlar</i> verir, ondan <i>UTS isteği</i> alır; RX'te <i>UTS öğesi</i> verir, ondan <i>adres + baytlar + zaman</i> alır.</li>
  <li><b>Kanal</b> bir hattır: ad, interface, bir protokol nesnesi ve o hatta kayıtlı mesajlar. Mesajı bulmak (adres → imza) kanalın işidir, protokolün değil.</li>
  <li><b>Mesaj değişmez.</b> <code>BaseMessageStructure</code> aynen kalır; tek ek, protokolün istediği adres alanları (1553'te <code>node</code>, <code>subnet</code>).</li>
</ul>

<h2 id="sinirlar">Amaç ve sınırlar</h2>
<table>
  <tr><th>İlke</th><th>Ne demek</th></tr>
  <tr><td>Protokol içerden bağımsız</td><td>Çekirdek protokolün sınıf yapısını, yardımcılarını, iç tamponunu bilmez. Sadece aşağıdaki sözleşmeyi bilir.</td></tr>
  <tr><td>Mesaj modeli korunur</td><td><code>BaseMessageStructure</code>, alanlar, imza, özel alanlar (uzunluk, sayaç, CRC), geçmiş ve snapshot aynen kalır.</td></tr>
  <tr><td>Bilinmeyene optimizasyon yok</td><td>UTS'in henüz bilmediğimiz davranışları (çok adımlı istekler, UTS'te zamanlanan gönderim, servis protokolleri) şimdi tasarlanmaz. Sözleşme bunları engellemeyecek kadar açık bırakılır.</td></tr>
  <tr><td>Sade isimler</td><td>PDU / PCI / SDU yerine: <i>adres</i>, <i>veri</i> (baytlar), <i>UTS isteği</i>, <i>UTS öğesi</i>. Eski isimlerin karşılığı <a href="#isimler">ekte</a>.</td></tr>
</table>

<h2 id="bilesenler">Bileşenler</h2>
{components}
<table>
  <tr><th>Bileşen</th><th>Sahibi</th><th>Sorumluluğu</th><th>Bilmediği</th></tr>
  <tr><td>Test kodu</td><td><span class="tag t-core">test</span></td><td>Mesaj nesneleri oluşturur, gönderir, bekler.</td><td>Protokol, UTS</td></tr>
  <tr><td>Comm</td><td><span class="tag t-core">çekirdek</span></td><td>Kanalları açar/kapatır, TX zamanlayıcı, RX döngüsü, olaylar.</td><td>Protokolün içi</td></tr>
  <tr><td>Kanal</td><td><span class="tag t-core">çekirdek</span></td><td>Protokolü ve mesajları bir arada tutar; gelen veriyi doğru mesaja verir.</td><td>UTS'in JSON biçimi</td></tr>
  <tr><td>Protokol</td><td><span class="tag t-proto">protokol ekibi</span></td><td>Adres tanımı, TX encode, RX decode, UTS adaptörü ve config'i.</td><td>Mesaj sınıfları, imzalar, test</td></tr>
  <tr><td>UTS istemcisi</td><td><span class="tag t-core">çekirdek</span></td><td>HTTP: post, get, config. Sadece JSON taşır.</td><td>Protokoller</td></tr>
  <tr><td>Mesaj</td><td><span class="tag t-core">proje (ICD)</span></td><td>Alanlar, imza, özel alanlar; <code>pack()</code> baytları, <code>decode()</code> baytları alır.</td><td>Bus, UTS</td></tr>
</table>

<h2 id="sozlesme">Sözleşme: veri modelleri</h2>
<p>Çekirdek ile protokol arasında sadece bu beş şey geçer. Hiçbiri mesaj nesnesi değildir; protokol mesaj sınıflarını hiç görmez.</p>
{contract}
<table>
  <tr><th>Model</th><th>Kim üretir</th><th>İçerik</th><th>Not</th></tr>
  <tr><td><b>Adres</b></td><td>Protokol (<code>make_address</code>)</td><td>Protokolün tanımladığı alanlar</td><td>Çekirdek sadece karşılaştırır ve loglarda gösterir. Adresi olmayan protokolde boş.</td></tr>
  <tr><td><b>Giden</b></td><td>Çekirdek</td><td>adres, veri (bytes), mesaj adı</td><td>TX'te protokolün aldığı tek şey.</td></tr>
  <tr><td><b>UTS isteği</b></td><td>Protokol (<code>encode</code>)</td><td>gövde (dict)</td><td>Çekirdek bunu protokolün <code>path</code>'i ve kanalın interface'iyle POST eder.</td></tr>
  <tr><td><b>UTS öğesi</b></td><td>UTS</td><td>GET cevabındaki bir öğe (dict)</td><td>Biçimini sadece protokol bilir.</td></tr>
  <tr><td><b>Gelen</b></td><td>Protokol (<code>decode</code>)</td><td>adres, veri (bytes), zaman (saniye)</td><td>Bir öğeden 0, 1 ya da birden fazla Gelen çıkabilir (bölünmüş akış).</td></tr>
</table>
<div class="box note"><strong>Neden mesaj nesnesi değil de baytlar?</strong>
Protokol mesaj sınıflarına bağlanırsa her ICD değişikliği protokolü etkiler, ve protokol ekibi mesaj modelimizi bilmek zorunda kalır.
Baytlar + adres, iki taraf arasındaki en dar ve en kararlı sınır.</div>

<h2 id="protokol">Protokol arayüzü</h2>
<p>Bir protokol bu yöntemleri sağlar. Zorunlu olanlar olmadan çalışmaz; isteğe bağlılar yoksa çekirdek atlar.</p>
<pre><code>class Protocol:
    path: str                                    # UTS'teki bus adı: "ethernet", "serials", "1553", "can"
    address_fields: tuple[str, ...]              # mesaj oluştururken istenen alanlar: ("node", "subnet") ya da ()
    config: object                               # protokolün UTS ayarları (adaptör config'i)

    def make_address(self, **fields) -&gt; Address  # eksik alan / aralık dışı değer -&gt; hata (tanım anında)
    def encode(self, out: Outgoing) -&gt; dict      # TX: adres + veri -&gt; UTS gövdesi
    def decode(self, item: dict) -&gt; list[Incoming]   # RX: UTS öğesi -&gt; adres + veri + zaman

    # isteğe bağlı
    def configure(self, uts, interface) -&gt; None  # açılışta: config'i UTS'e uygular
    def check(self, data: bytes) -&gt; None         # TX'ten önce: bus bu boyu taşıyabilir mi
    def reset(self) -&gt; None                      # açılış / kapanış: iç tamponları temizler
    def simulate(self, inc: Incoming) -&gt; dict    # sahte UTS için: cihaz bunu gönderseydi UTS ne döndürürdü</code></pre>

<table>
  <tr><th>Yöntem</th><th></th><th>Alır</th><th>Döner</th><th>Ne zaman</th></tr>
  <tr><td><code>path</code>, <code>address_fields</code>, <code>config</code></td><td><span class="tag t-req">zorunlu</span></td><td>-</td><td>-</td><td>Protokol oluşturulurken</td></tr>
  <tr><td><code>make_address</code></td><td><span class="tag t-req">zorunlu</span></td><td>adres alanları</td><td>Adres</td><td>Mesaj nesnesi oluşturulurken</td></tr>
  <tr><td><code>encode</code></td><td><span class="tag t-req">zorunlu</span></td><td>Giden</td><td>UTS gövdesi</td><td>Her gönderimde</td></tr>
  <tr><td><code>decode</code></td><td><span class="tag t-req">zorunlu</span></td><td>UTS öğesi</td><td>Gelen listesi</td><td>Her alınan öğede</td></tr>
  <tr><td><code>configure</code></td><td><span class="tag t-opt">isteğe bağlı</span></td><td>UTS istemcisi, interface</td><td>-</td><td><code>comm.open()</code></td></tr>
  <tr><td><code>check</code></td><td><span class="tag t-opt">isteğe bağlı</span></td><td>veri</td><td>- (hata fırlatır)</td><td>Gönderimden önce</td></tr>
  <tr><td><code>reset</code></td><td><span class="tag t-opt">isteğe bağlı</span></td><td>-</td><td>-</td><td>Açılış / kapanış</td></tr>
  <tr><td><code>simulate</code></td><td><span class="tag t-opt">isteğe bağlı</span></td><td>Gelen</td><td>UTS öğesi</td><td>Sadece testlerde (sahte UTS)</td></tr>
</table>
<div class="box warn"><strong>TX gövdesi ile RX öğesi aynı biçimde olmak zorunda değil</strong>
UTS'e gönderdiğimiz gövde ile UTS'ten okuduğumuz öğe farklı biçimde olabilir. Bu yüzden <code>encode</code> ve <code>decode</code> ayrı,
ve sahte UTS'in cihaz gibi davranabilmesi için ayrıca <code>simulate</code> var.</div>
<div class="box note"><strong>UTS adaptörü ve config'i protokolün içinde</strong>
UTS'in bir bus'ı JSON'da nasıl yazdığı o bus'a özgü olduğu için protokolün parçası. Protokol içte bunu ayrı bir adaptör sınıfı olarak
tutabilir; çekirdek için önemli değil. Seri moddaki RS422 / Camera Link seçimi gibi ayarlar <code>config</code>'te durur ve
<code>configure</code> ile UTS'e uygulanır.</div>

<h2 id="kanal">Kanal ne tutar</h2>
{channel_model}
<table>
  <tr><th>Alan</th><th>Anlamı</th></tr>
  <tr><td><code>name</code></td><td>Projedeki adı (<code>ChannelSet</code> verir); log, olay, CSV'de görünür.</td></tr>
  <tr><td><code>interface</code></td><td>UTS'teki hat numarası. Protokolün <code>path</code>'i ile birlikte UTS uç noktasını verir.</td></tr>
  <tr><td><code>protocol</code></td><td>Bir protokol nesnesi; config'i içinde. Her kanalın kendi nesnesi (kendi config'i, kendi iç tamponu).</td></tr>
  <tr><td><code>messages</code></td><td>Kanala kayıtlı mesajlar. Anahtar <code>(adres, imza)</code>, imzasız mesaj için <code>(adres, -)</code>; v2.1-base'deki <code>(kanal, imza)</code> anahtarının kanal içindeki hali.</td></tr>
</table>
<p>Kanalın davranışı:</p>
<ul>
  <li><b><code>send(mesaj)</code></b>: <code>mesaj.pack()</code> ile baytları alır, protokole <code>encode</code> ettirir, UTS istemcisiyle gönderir.</li>
  <li><b><code>receive(öğe)</code></b>: protokole <code>decode</code> ettirir; her Gelen için mesajı bulur ve <code>mesaj.decode(veri, zaman)</code> çağırır.</li>
  <li><b>Tanıma sırası</b> (kanalın kuralı): 1) adres, 2) verinin içindeki imza, 3) o adreste imzasız tek mesaj varsa o, 4) değilse bilinmeyen. Belirsizlik mesaj tanımlanırken hata verir.</li>
  <li><b><code>open()</code> / <code>close()</code></b>: protokolün <code>configure</code> ve <code>reset</code>'ini çağırır.</li>
</ul>
<div class="box note"><strong>Öneri: bir UTS uç noktası = bir kanal</strong>
v2.1-base'de aynı interface'i başlıklı ve başlıksız iki kanal paylaşabiliyordu; bu, kanal sırası, "her şeyi kabul eden kanal"
kuralı ve adres başına splitter gibi kuralları getirdi. Uç nokta başına tek kanal olursa bu kurallar kalkar; aynı hatta iki farklı
paket türü varsa bunları ayırmak protokolün işi olur (iki farklı adres döndürür). Bkz. <a href="#sorular">Soru 1</a>.</div>

<h2 id="mesaj">Mesaj (BaseMessageStructure)</h2>
<p>Mesaj modeli aynen kalır: <code>_fields_</code>, aileler ve <code>Signature</code>, özel alanlar, <code>pack()</code> / <code>decode()</code>,
<code>has_new</code>, geçmiş, <code>snapshot</code>. Tek ek, kanalın protokolünün istediği adres alanlarıdır:</p>
<pre><code>report = bit_report(node=5, subnet=3)        # 1553: protokolün address_fields'i
wheel  = wheel_speed(can_id=0x123)           # CAN
status = comut(DEST, SRC, 0x20)              # Ethernet / RS422: adres yok, bugünkü gibi</code></pre>
<p>Mesaj adres alanlarını kendisi doğrulamaz; kanalının protokolüne <code>make_address(**alanlar)</code> ile sorar. Böylece hangi alanın
zorunlu olduğuna protokol karar verir, mesaj modeli protokolü bilmez.</p>

<h2 id="akis">Akışlar</h2>
<h3>Gönderim (TX)</h3>
{tx_seq}
<h3>Alım (RX)</h3>
{rx_seq}
<h3>Açılış ve kapanış</h3>
{open_seq}

<h2 id="hatalar">Hatalar ve sorumluluk</h2>
<table>
  <tr><th>Durum</th><th>Kim fark eder</th><th>Sonuç</th></tr>
  <tr><td>UTS'e ulaşılamıyor, HTTP hatası</td><td>UTS istemcisi</td><td>Bağlantı hatası olayı; gönderim <code>False</code> döner, RX döngüsü devam eder</td></tr>
  <tr><td>UTS öğesi beklenen biçimde değil</td><td>Protokol (<code>decode</code> hata fırlatır)</td><td>Bağlantı hatası olayı; aynı cevaptaki diğer öğeler işlenir</td></tr>
  <tr><td>Bus bu boyu taşıyamaz</td><td>Protokol (<code>check</code>)</td><td>Gönderilmez, hata loglanır (UTS hatası sayılmaz)</td></tr>
  <tr><td>Adres eksik / aralık dışı</td><td>Protokol (<code>make_address</code>)</td><td>Mesaj oluşturulurken hata</td></tr>
  <tr><td>Adreste ya da imzada mesaj yok</td><td>Kanal</td><td>Bilinmeyen paket olayı</td></tr>
  <tr><td>Mesaj bulundu ama boy / CRC tutmuyor</td><td>Mesaj (<code>decode</code>)</td><td>Geçersiz paket olayı</td></tr>
</table>
<div class="box ok"><strong>Kural</strong>
Protokolden gelen hiçbir istisna RX ya da TX döngüsünü durdurmaz; çekirdek her öğeyi ve her gönderimi ayrı ayrı korur.</div>

<h2 id="bilinen">Bilinen protokoller bu sözleşmeye nasıl oturur</h2>
<p>İç tasarımın başlangıç noktası. "Bilinen" senin verdiğin bilgi, "varsayım" henüz doğrulanmadı.</p>
<table>
  <tr><th></th><th>Ethernet</th><th>RS422 (serials)</th><th>MIL-STD-1553</th><th>CAN</th></tr>
  <tr><td>address_fields</td><td>yok</td><td>yok</td><td><code>node</code>, <code>subnet</code> (1..32)</td><td><code>can_id</code></td></tr>
  <tr><td>encode çıktısı</td><td><code>{{"message": [baytlar]}}</code></td><td><code>{{"message": [baytlar]}}</code></td><td><code>{{"message": [node, subnet, wc, word'ler]}}</code></td><td>varsayım: <code>{{"id", "message"}}</code></td></tr>
  <tr><td>decode girdisi</td><td><code>{{"message", "timestamp"}}</code></td><td>aynı; akış bölünebilir</td><td>varsayım: encode ile aynı biçim</td><td>varsayım</td></tr>
  <tr><td>config</td><td>bilinmiyor</td><td>RS422 / Camera Link seçimi, baud</td><td>bilinmiyor (UTS rolü?)</td><td>bit hızı?</td></tr>
  <tr><td>Durum</td><td>bilinen</td><td>bilinen</td><td>TX bilinen, RX varsayım</td><td>varsayım</td></tr>
</table>

<h2 id="disinda">Bilerek dışarıda bırakılanlar</h2>
<p>Bunlar şimdi tasarlanmıyor; sözleşme bunları sonradan eklemeyi engellemiyor.</p>
<ul>
  <li><b>Bir gönderimin birden fazla UTS isteği olması</b> (ör. 1553'te komut + veri). Gerekirse <code>encode</code> bir liste döndürebilir.</li>
  <li><b>UTS'in kendi zamanladığı gönderim</b> (ör. 1553 çerçeve çizelgesi). Bugün periyot çekirdekte.</li>
  <li><b>İstekle gelen RX</b> (UTS bus controller ise RT'den veri istemek). Bugün RX sadece sorgulanır.</li>
  <li><b>Servis protokolleri</b> (CANopen SDO / NMT): mesaj değil servis olarak, protokolün üstünde.</li>
  <li><b>UTS filtreleri</b>: bayt konumu protokole özgü; gerekirse isteğe bağlı bir yöntem.</li>
</ul>

<h2 id="sorular">Karar bekleyenler</h2>
<div class="q"><h4>Bir UTS uç noktası = bir kanal mı?</h4>
<p>Evet ise: kanal sırası ve adres başına splitter kuralları kalkar; aynı hattaki farklı paket türlerini protokol ayırır. Hayır ise:
bugünkü "başlıklılar önce, her şeyi kabul eden en sonda" kuralı kalır.</p></div>
<div class="q"><h4>TX'te protokol sadece adres + baytları mı alsın?</h4>
<p>Öneri evet. Protokolün mesaj alanlarına ihtiyaç duyduğu bir durum varsa (ör. bir alanın değerine göre farklı UTS isteği), bunu şimdiden bilmek iyi olur.</p></div>
<div class="q"><h4>Adaptör config'i nerede verilir?</h4>
<p>Kanal tanımında (<code>Rs422Channel(0, mode="RS422", baud=115200)</code>) mı, yoksa ayrı bir ayar dosyasında mı? Ve <code>comm.open()</code> bunu otomatik mi uygulasın?</p></div>
<div class="q"><h4>UTS GET öğesi TX gövdesiyle aynı biçimde mi?</h4>
<p>1553 için RX tarafının biçimi ve zaman biriminin ne olduğu iç tasarımı doğrudan etkiliyor.</p></div>
<div class="q"><h4>Protokol "bu öğe benim değil" diyebilmeli mi?</h4>
<p>Soru 1'e evet denirse gerekmez: uç noktadaki her öğe o kanalındır; tanınmayan veri bilinmeyen olur.</p></div>

<h2 id="isimler">Ek: isimler</h2>
<table>
  <tr><th>Bu belgede</th><th>v2.1-pdu'daki ad</th><th>v2.1-base'deki karşılığı</th></tr>
  <tr><td>Adres</td><td>PCI (<code>Pci</code>)</td><td>yok (kanal + imza)</td></tr>
  <tr><td>Veri (baytlar)</td><td>SDU</td><td>mesaj baytları (<code>raw</code>)</td></tr>
  <tr><td>Giden / Gelen</td><td>PDU (<code>Pdu</code>)</td><td>yok / <code>RxFrame</code></td></tr>
  <tr><td>UTS isteği / öğesi</td><td>adaptör çıktısı / item</td><td><code>transfer</code> baytları / <code>UtsFrame</code></td></tr>
  <tr><td>Protokol (UTS adaptörü dahil)</td><td><code>Protocol</code> + ayrı <code>UtsAdapter</code></td><td><code>ProtocolType</code> + <code>Framing</code></td></tr>
  <tr><td>Başlık, bölme (protokolün içi)</td><td><code>Header</code>, <code>Splitter</code></td><td><code>Envelope</code>, <code>Splitter</code></td></tr>
</table>
"""

nav = "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in nav_items)
page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Protokol Arayüzü Mimarisi</title><style>{CSS}</style></head>
<body><div class="layout"><nav><p class="brand">asl_testing</p><p class="sub">Protokol arayüzü, mimari taslak</p>{nav}</nav>
<main>{body}</main></div></body></html>"""
open(OUT, "w", encoding="utf-8").write(page)
print("bytes", len(page))
