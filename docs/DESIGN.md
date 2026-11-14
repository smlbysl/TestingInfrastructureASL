# BaseMessageStructure - Tasarım Notları

Yazar: İsmail Baysal

Python ctypes ile Ethernet, RS422 ve MIL-STD-1553 üzerinden haberleşen projeler için test altyapısı.
Şemalı mimari: `docs/architecture.html` (`python tools/build_architecture.py` ile üretilir).
ICD'ye bağlı mesaj nesneleri oluşturulur; haberleşme UTS (HTTP servisi) üzerinden yapılır.
Ayrıntılı tasarım ve yol haritası: "UTS Haberleşme Katmanı – Tasarım ve Yol Haritası" belgesi.
Kod içindeki yorumlar İngilizce.

## Dosya yapısı
```
asl_testing/                 ÇERÇEVE (projeden bağımsız)
  __init__.py                kısa erişim: from asl_testing import Comm, EthernetChannel, Timing ...
  comm.py                    Comm: test tarafının tek giriş noktası
  message/                   1. Mesaj modeli: ne gönderilir
    base.py                  BaseMessageStructure: init, validate/decode, pack, callout, varsayılanlar
    fields.py                FieldType hook'ları, Length/Counter/Checksum/Ascii
    signature.py             Signature: alan listesinden offset+mask, tek ID
    registry.py              Registry: aile başına kayıtlar, lookup, yer değiştirme kuralı
    timing.py                Timing(period, tolerance), Direction
    state.py                 RxState (UTS zamanı, yeni paket), TxState
  channel/                   2. Kanal: nereden gider
    channel.py               Channel (bus + interface + framing), kanal tipleri, ChannelSet
    framing.py               Splitter, Envelope, Framing
  backend/                   3. Backend: baytlar cihaza nasıl taşınır
    base.py                  Backend (send, receive), Response, Received, BackendError
    fake.py                  FakeBackend (sent, inject); UTS biçimi içermez
    uts/                     UTS'e özgü her şey
      api.py                 UtsApi (post, get, config, filtre), WrapperUtsApi (ApiWrapper şablonu)
      codecs.py              bus -> UTS yolu ve JSON: SerialCodec, EthernetCodec, Mil1553Codec
      backend.py             UtsBackend: codec seçer, api'yi çağırır
      control.py             UtsControl: config ve filtre (testten dikine, doğrudan çağrı)
      filters.py             filtre hesapları (mesaj -> hattaki byte konumu, değer)
      fake.py                FakeUtsApi, FakeUtsBackend (posted, inject)
  runtime/                   4. Çalışma zamanı: ne zaman ve nasıl taşınır
    transport.py             kanal başına: envelope, backend isteği, splitter
    rx.py                    RxPoller: sorgu, WireReceived, zaman aşımı
    tx.py                    TxScheduler: send (kilit), periyodik gönderim, WireSent
    dispatcher.py            lookup + decode + olay, unknown listesi
    clock.py                 UtsClock: tahmini UTS "şimdi"si
  events/                    5. Olaylar
    types.py                 mesaj ve hat seviyesi olaylar
    bus.py                   EventBus: abone başına kuyruk + thread
  services/                  6. Olay aboneleri
    comm_logger.py           CommLogger: gönderilen ve alınan paketlerin CSV kaydı
    errors.py                ErrorLog: UTS hataları, RX zaman aşımı, abone hataları (ayrı dosya)
    monitor/                 MonitorService: mesaj değerlerini zamanla izleme sayfası (canlı / CSV)
projects/
  example_project/           PROJEYE ÖZEL (ICD)
    header.py                ProjectBase (header, varsayılan kanal) ve aileler
    types.py                 Length16, Counter8, CRC16 ...
    channels.py              MyChannels
    framing.py               örnek EthHeader
    messages.py              mesaj sınıfları
examples/                    python -m examples.example (depo kökünden)
docs/DESIGN.md
```

Bağımlılık yukarıdan aşağıya: `comm.py` → `services` / `runtime` → `events`, `uts` → `message`, `channel`.
`projects/` sadece `message` ve `channel`'ı kullanır.

## Katmanlar
```
Test kodu        mesaj nesneleri + Comm (send, start/stop, on_receive, unknown)
Comm             katmanları kurar, open/close
TxScheduler      ne zaman gönderilir        RxPoller   ne zaman sorgulanır + zaman aşımı
                                            Dispatcher registry ile eşleme, decode, olay
EventBus         olayları abonelere dağıtır (CommLogger, ErrorLog, test dinleyicileri, ileride simülasyon/UI)
Transport        kanal başına: envelope, backend isteği, splitter
Backend          hattaki baytları taşır: send(kanal, bayt), receive(kanal) -> Response
  UtsBackend     bus'a göre codec (bayt <-> UTS JSON) + UtsApi (POST / GET, yol + interface)
```

## Backend ve UTS codec'leri
- Çekirdek ile cihaza giden sistem arasındaki sınır bayt düzeyinde: `Backend.send(kanal, hattaki baytlar)` ve
  `Backend.receive(kanal)`. İkisi de `Response` döner (`ok`, `status`, `code`, `message`, `data`, `timestamp`,
  `elapsed`); başarısız istek istisna fırlatmaz, `ok=False` döner. `receive`'in `data`'sı `Received(bayt, zaman)` listesi.
- Kanal sadece bus'ı (`"serial"`, `"ethernet"`, `"mil1553"`), interface numarasını ve bus'a ait ayarı (1553
  `byte_order`) tutar. URL yolu ve JSON biçimi kanalda yok. UTS yerine başka bir sistem gelirse yeni bir backend
  yazılır; mesaj, kanal, framing, RX/TX, olaylar ve testler değişmez.
- UTS'e özgü her şey `backend/uts/` altında. `UtsBackend` bus'a göre codec seçer; codec yolu (`serials`, `ethernet`,
  `1553`) ve gövdeyi verir (`encode`), UTS öğesinden baytları ve zamanı çıkarır (`decode`). İstekleri `UtsApi` yapar;
  gövdeye bakmaz. `WrapperUtsApi` eldeki `ApiWrapper` için şablon (`post` / `get` doldurulacak).
- Codec mesajı, signature'ı, envelope'u, splitter'ı ve zamanlamayı bilmez. Envelope TX'te backend'den önce
  eklenir; splitter ve envelope RX'te backend'den sonra çalışır.
- Seri ve Ethernet'in UTS biçimi bugün aynı (`{"message": [baytlar], "timestamp": t}`) ama ayrı sınıflar:
  biri değişirse diğeri etkilenmez.
- MIL-STD-1553 (`Mil1553Codec`, `Mil1553Channel`): UTS paketi `[rt, subnet, word_count, word, word, ...]` listesi
  olarak taşır, ör. `[30, 1, 3, 0x0001, 0x3344, 0x1122]`. `rt`, `subnet`, `word_count` mesajın ilk alanlarıdır
  (projede `c_uint16`); codec sadece mesaj baytlarını 16 bitlik değer listesine çevirir ve geri. Değerler
  kontrol edilmez. Tanıma bugünkü signature ile: `Signature("rt", "subnet")`.
  Kanalın `byte_order`'ı mesaj yapısının endian'ıyla aynı olmalı: little + "little" → 32 bit alanın düşük kelimesi
  önce, big + "big" → yüksek kelime önce; uyuşmazsa her değerin baytları ters gider (`30` → `7680`).
  Big-endian 1553 projesinde K3 (özel alanların endian'ı) etkili olur.
- Sahte backend iki tane: `FakeBackend` (UTS biçimi yok; `sent`, `inject`) testlerin varsayılanı;
  `FakeUtsBackend` (gerçek codec'ler + `FakeUtsApi`; `posted`, `inject`) UTS biçimini sınayan testler için.
- UTS cevapları: POST `{"statusInfo": {status, code, message}, "timestamp": t}`; GET `{"statusInfo": {...},
  "messages": [öğe, ...], "isBufferOverflow": false}`. `uts_response(http_kodu, gövde)` bunu `Response`'a çevirir;
  `timestamp`, `messages`, `isBufferOverflow` alanlarını codec okur. Zaman mikrosaniye (`time_unit=1e-6`).
- Açık: Ethernet ve 1553 cevaplarının seri ile aynı olduğu ve zaman biriminin mikrosaniye olduğu doğrulanmalı.

## Kanal ve framing
- `Channel`: bir interface = bus + interface numarası + `Framing`
  (alt sınıflar: `EthernetChannel`, `Rs422Channel` (bus `serial`), `Mil1553Channel`; bus'ı belirler).
  IP, port, baud gibi fiziksel ayarlar kanalda yok. Eşitlik kimliğe göre: her kanal bir kez tanımlanır.
- `Framing(splitter, envelope)`, ikisi de isteğe bağlı; varsayılanları bir şey yapmaz.
  - Splitter: akış seviyesi; UTS'ten geleni paketlere böler.
  - Envelope: paket seviyesi; `on_send` ekler, `on_receive` çıkarır, kabul etmezse `None` (paket bilinmeyen olur).
- Proje kanallarını `ChannelSet` ile tanımlar (`project/channels.py`): isimleri verir, sınıf tanımlanırken bir
  interface'in iki kez kullanılmadığını kontrol eder. `Comm`'a verilmez.
- Kanal mesaja sınıf varsayılanı olarak verilir (`_channel = MyChannels.CONTROL`); nesne oluştururken verilmez.
- Bir interface'in tek kanalı var; gelen paketin kanalı her zaman bellidir. Envelope'u kabul etmeyen paket o kanalda
  unknown olur.
- Sorgulanan kanallar: RX mesajı kayıtlı kanallar ve `comm.listen(kanal)` ile eklenenler; her kanal kendi
  thread'inde.
```
TX:  msg.pack() -> envelope.on_send -> backend.send(kanal, bayt)          [UTS: codec.encode -> api.post(yol, interface)]
RX:  backend.receive(kanal) -> splitter -> envelope.on_receive -> Dispatcher   [UTS: api.get(yol, interface) -> codec.decode]
```

## Monitor (services/monitor)
- Ayrı bir servis; mevcut koda dokunmaz. Yerel bir web sayfası (sadece standart kütüphane, internet gerekmez).
  `MonitorService(comm, [ProjectBase], port=8050).start()` -> http://127.0.0.1:8050.
- Canlı: Tools > Start, `MessageReceived` / `MessageSent` olaylarına abone olur (Stop: abonelik kalkar).
  Offline: File > Import CSV (CommLogger dosyası); satırlar mesaj sınıfı adıyla çözülür. Testsiz açmak için:
  `python -m asl_testing.services.monitor projects.example_project.header:ProjectBase projects.example_project.messages`
  (mesaj sınıflarının modülü de verilir, sınıflar adla bulunur).
- Recorder her mesaj akışı (yön, sınıf, kanal, signature) için (zaman, ctypes görüntüsü) tutar; alan değerleri sadece
  görüntülenen sinyaller için, istendikçe çözülür. Alan yolları: `speed`, `comut[0]`, `cmd.startReq`; özel tiplerde `.val`.
- Sayfa: RX/TX ağacı (tık: alanlar ve son değerler; sağ tık: "Add all fields" / "Add to plot"; çift tık: ekle),
  sinyal başına ayrı renkte grafik, ortak zaman ekseni (10/30/60 s / All), Pause, imleçle değer okuma, tekerlek ile
  yakınlaştırma, sürükleyerek kaydırma, grafikte sağ tık ile kaldırma.
- Maliyet: canlı modda iki abonelik (olay başına ~2–3 µs); çözme sadece sayfa açıkken ve seçili sinyaller için.
- Açık: kayıtlar bellekte sınırsız birikir (uzun koşularda sınır gerekebilir); zaman ekseni bu bilgisayarın saati
  (UTS zamanı değil); değişken boylu mesajlarda CSV'den çözülen görüntüde kullanılmayan kısım sıfırdır.

## UTS yönetimi (comm.control)
- Mesaj akışından ayrı, dikine bir yol: test -> `comm.control` (UtsControl) -> UtsApi. RX/TX thread'leri ve
  olaylar kullanılmaz; çağrı senkron. Her çağrı INFO loglanır. `comm.control` backend'den gelir; config ve
  filtresi olmayan backend'de (`FakeBackend`) `None`'dır.
- Hedef bir mesaj nesnesi ya da kanal; mesaj kendi kanalını verir. Kanalın bus'ı (codec yolu) + interface'i UTS
  arayüzünü seçer.
- `get_config` / `set_config(**ayarlar)`, `get_filter -> (kind, groups)`, `set_filter(groups, kind)`, `clear_filter`.
- `add_filter(msg)` / `remove_filter(msg)`: filtreyi okur, mesajın signature byte'larını ekler/çıkarır, geri yazar.
  Konumlar hattaki konumlardır: kanal envelope'unun `offset`'i (mesajın önündeki byte sayısı) eklenir
  (`Envelope.offset`, varsayılan 0; örnek `EthHeader.offset = 8`).
- UtsApi'nin yönetim metotları soyut değil (varsayılan `NotImplementedError`); FakeUtsApi bunları saklar,
  gelen paketlere uygulamaz.
- Dikkat: ilk `add_filter` arayüzü "her şey geçer"den "sadece filtre geçer"e çevirir; aynı arayüzdeki
  filtreye eklenmemiş mesajlar artık gelmez.

## Kanala göre tanıma (signature'sız aile)
- Sınıfta açıkça `_signature = None` yazılırsa (aile ya da proje) RX mesajı sadece kanalından tanınır:
  anahtar `(kanal, None)`. Kanal başına en fazla bir RX mesajı (ikincisi çakışma hatası).
  `_signature` hiç yazılmamış bir proje eskisi gibi kalır: ona doğrudan bağlı RX mesajları kayda girmez.
- Sıra: önce bütün projelerde signature eşleşmesi, yoksa kanalın signature'sız mesajı. Böylece aynı kanalda
  sabit boylu mesajlar (ör. length = signature) ile tek bir değişken boylu mesaj birlikte çalışır.
- Kanal eşleştiği için doğrulamayı geçemeyen paket invalid olur (unknown değil). Değişken boyda boy length alanından.
- Sabit boylu mesajlarda length alanı signature olarak kullanılabilir (`Signature("length")`); boy her
  mesajda farklıysa ayrışırlar. Değişken boyda length kimlik olamaz.

## Yeni paket kontrolü
- `msg.has_new()`: son çağrıdan bu yana gelen geçerli paket sayısı (0: yok); çağrı sıfırlar.
  `rx_state.count` (toplam) ile son kontrol edilen değer (`_seen`) karşılaştırılır; kilit gerekmez, paket kaçmaz.
- `comm.wait_new(msg, timeout)`: yeni paket gelene kadar bekler; gelen paket sayısını ya da zaman aşımında 0 döner.
  Bir isteği göndermeden önce `msg.has_new()` çağrılır ki önceki paket cevap sanılmasın.

## Mesaj geçmişi (rx_history)
- Her RX nesnesi son N geçerli paketi sırayla tutar (`asl_testing/message/history.py`). Canlı nesne son paketi
  gösterir; tek yoklamada gelen aradaki paketler geçmişte kalır (B2).
- Kayıt (`Record`) `decode`'un nesneye yazdığı baytların aynısıdır; `MessageReceived.image` de aynı baytları taşır.
  Kayıtlar değişmez; `snapshot()` ayrı, kayıtsız bir nesne verir.
- Okuma veriyi tüketmez: her okuyan kendi `mark()`'ını tutar (B6). `has_new` / `wait_new` aynen kalır.
- `comm.wait_for` / `history.wait_for` kilit + koşul değişkeniyle bekler, yeni kayıtta uyanır (5 ms yoklama yok).
  Koşul her kaydın snapshot'ında, yeni kayıtlar için bir kez çalışır.
- Kapasite: sınıfta `_history` (varsayılan 64), nesnede `history=`. Dolunca en eski düşer, `dropped` artar, ilk
  taşmada bir kez WARNING. Geçmiş `RxState` içinde olduğu için nesne yeniden oluşturulunca boşalır.
- `seq` bütün mesajlar için tek sayaçtır (`itertools.count`, GIL altında atomik); aynı zaman damgalı paketlerin
  sırası buradan anlaşılır. UTS listesinin kronolojik olduğu varsayılıyor, doğrulanmalı.
- TX geçmişi yok (yüksek frekanslı periyodik gönderim kapasiteyi doldurur); gerekirse aynı yapıyla eklenir.

## Son paketin zamanı (mesaj üzerinden)
- `msg.rx_timestamp`: UTS'nin bildirdiği geliş zamanı (saniye).
- `msg.rx_host_time`: paketin bu bilgisayarda alındığı tarih-saat (`time.time`).
- `msg.rx_age`: son paketten bu yana geçen saniye (bu bilgisayarın saati).
- Paket gelmediyse ya da mesaj TX-only ise `None`. `rx_` öneki, ICD'deki `timestamp` gibi alanların
  property'yi gölgelememesi için. Belirli bir paketin zamanı için olaydaki `ev.timestamp` / `ev.host_time` kullanılır.

## Olaylar
- Mesaj seviyesi (değişmedi): `MessageReceived`, `MessageSent`, `InvalidReceived`, `UnknownReceived`
  (`raw` = mesaj byte'ları, envelope çıkarılmış).
- Hat seviyesi: `WireReceived` (hattan gelen her paket, envelope dahil; mesaj eşleşmesinden önce) ve
  `WireSent` (hatta giden paket). Abonelik: `comm.subscribe(WireReceived, handler)`.
- Bir paket için önce hat seviyesi, sonra mesaj seviyesi olay yayınlanır.

## Loglama
- Genel log: her modül standart `logging` ile kendi logger'ına yazar (`logging.getLogger(__name__)`,
  ör. `asl_testing.runtime.rx`). Altyapı handler eklemez; kayıtların nereye gideceğini test tarafı bir kez
  ayarlar (ör. `logging.basicConfig(filename=...)`). Ayar yoksa WARNING ve üstü konsola düşer.
- UTS istekleri `asl_testing.uts` logger'ında: başarısız istek ERROR (yol, interface, durum, kod, mesaj, süre),
  başarılı POST ve öğe döndüren GET DEBUG; boş GET yazılmaz. Başarısız isteği backend loglar, çekirdek aynı
  hatayı ikinci kez yazmaz (sadece `LinkError` yayınlar); çekirdek beklenmeyen istisnaları traceback ile yazar.
- Altyapının yazdıkları: backend isteği hatası ERROR, abone exception'ı ERROR,
  RX zaman aşımı / invalid / unknown paket WARNING, open/close, listen, periyodik başlat/durdur,
  RX geri geldi INFO, her gönderilen/alınan mesaj DEBUG.
- `Comm(..., logger=x)`: tüm parçalar (bus, RX, TX, dispatcher) `x`'e yazar. `x`'in `debug`, `info`, `warning`,
  `error`, `exception` metotları olması yeterli (standart olmayan logger için küçük adaptör).
  Alternatif: mevcut logger'a yönlendiren bir `logging.Handler` kök logger'a eklenir; o zaman her şey oraya gider.
- Mesaj geçmişi (`CommLogger`, CSV) log değil veri; ayrı servis olarak kalır.
- `ErrorLog` event tabanlı, ayrı dosya. Kendi logger'ı (`asl_testing.errors`) genel loga iletmez (tekrar olmasın);
  abone hataları için bus logger'ına da handler ekler. Comm'a özel logger verilse de çalışır
  (o durumda abone hataları o logger'a gider, bu dosyaya değil).

## Thread modeli
- Kanal başına 1 RX thread'i (`Rx-<kanal>`), periyodik mesajı olan kanal başına 1 TX thread'i (`Tx-<kanal>`),
  1 denetçi (`RxWatchdog`), abone başına 1 thread. Mesaj başına thread yok.
- RX thread'i: yokla, `WireReceived`, dispatch, `poll_interval` kadar bekle. Cevap vermeyen bir kanal diğerlerini
  ve zaman aşımı kontrolünü bekletmez. Kanal içi paket sırası korunur; farklı kanalların olayları arasında sıra yok.
- Denetçi her `poll_interval`'da: RX mesajı olan ya da `listen` edilen kanalın thread'ini başlatır (kanallar
  `open`'dan sonra da ortaya çıkabilir) ve RX zaman aşımlarını kontrol eder. Artık gerekmeyen kanalın thread'i biter.
- TX thread'i kanalın ilk `comm.start(msg)` çağrısında açılır, `close`'a kadar yaşar.
- Gönderim kanalın kilidi altında: counter, checksum, byte, backend isteği, `after_send`. Bir mesaj hep aynı kanaldan
  gittiği için tutarlılık aynı; farklı kanallardaki gönderimler birbirini beklemez (kapasite interface başına).
  Kilit sırası: kanal gönderim kilidi -> backend'in interface kilidi.
- `UtsClock` bütün RX thread'lerinden güncellenir, denetçiden okunur; kendi kilidi var.
- `close`, o an cevap bekleyen bir isteğin bitmesini bekler (en fazla isteğin timeout'u kadar).
- `decode` yeni durumu ayrı tamponda hazırlayıp nesneye tek kopyayla yazar: tek alan okuması eski ya da yeni
  paketi görür, yarım değer görmez (B1). Birden fazla alan için `msg.snapshot()`.
- `pack` özel alanları (length, counter, CRC) nesnenin bir kopyasında hesaplar ve baytları o kopyadan üretir;
  nesneye sadece hook'un değiştirdiği özel alanlar geri yazılır (B9–B11).
- Bu koruma GIL'e dayanır (B13); free-threaded Python'da geçerli değildir.
- Periyodik gönderimde bir sonraki zaman `due + period` (kayma birikmez).
- ctypes nesneleri hash'lenemez: scheduler tablosu ve zaman aşımı kümesi `id(msg)` ile tutulur.

## Mesaj katmanı (özet)
- Hiyerarşi: BaseMessageStructure -> Proje -> Aile (`_signature`, kendi Registry'si) -> mesaj sınıfı -> nesne.
- İsimlendirme: `_x_` sadece ctypes; sınıf ayarları `_x`; nesne bilgisi alt çizgili, dışarıya property.
  Çerçeve kodu her zaman alt çizgili bilgiyi kullanır (ICD alan adlarıyla çakışmaz).
- `decode(raw, timestamp)`: UTS zamanı `rx_state.timestamp`'e yazılır (ctypes alanı değil).
- `_defaults` + `initialize()`; alan tipi hook'ları; `msg.on_send` (pack içinde, checksum'dan önce).
- Alan tipi hook'ları: `on_init`, `on_send` (pack içinde), `on_receive` (doğrulama), `after_send`
  (TX katmanı, UTS isteği başarılı olunca, gönderim kilidi altında; UTS hatasında çağrılmaz).
  Olaylar gönderilen değeri taşır (sıfırlamadan önce).
- Aynı byte'ı paylaşan bitler tek bir özel tipte toplanır (örnek `CmdByte`): ilk değerler `on_init`'te,
  bir kez gidecek istek biti `after_send`'de sıfırlanır. Erişim `msg.cmd.startReq`; bu tipte `.val` yok,
  `_defaults` kullanılmaz.
- `msg.on_receive` (RX thread'inde) ve `comm.on_receive` (kendi thread'inde) ikisi de var; hangisinin
  kalacağı açık.

## CRC ve değişken boy
- CRC header'da değil: her mesaj tanımı CRC'yi (`ChecksumType`) son alan olarak ekler.
- Kablodaki paket = gövde + CRC. Sabit boylu mesajda gövde CRC'ye kadar olan kısım, paket = `bytes(self)`.
- Değişken boylu mesaj: `_variable_size = True`. ctypes yapısı max boydur; gerçek boy length alanındadır.
  - RX: paket ≥ length, length ≤ max; CRC `raw[L-T:L]`'den okunur; decode gövdeyi başa, CRC'yi CRC alanına
    yazar, kullanılmayan kısmı sıfırlar.
  - TX: mesaj `body_size()`'ı override eder (ör. `entries.offset + count * 4`); length = gövde + CRC,
    CRC gövde üzerinden hesaplanır, paket gövde + CRC olarak gider.
- Olaylar iki kopya taşır: `raw` (kablodaki paket, loglanır) ve `image` (ctypes yapısı, `snapshot()` için).

## Registry
- `all`, `dispatch` (`(channel, signature_id) -> nesne`, sadece RX), `channels` (dispatch'ten),
  `periodic_rx` (zaman aşımı). Periyodik gönderim `comm.start` ile başlar.
- Aynı sınıf + channel + signature + yön ile yeniden oluşturulan nesne eskisinin yerini alır;
  eskisi tüm listelerden çıkar, `_registered = False` olur, scheduler onu tablodan düşürür.
- Farklı sınıf aynı channel + signature ile RX'e girerse `ValueError`.

## Açık konular (esnek bırakıldı)
- UTS GET JSON biçimi, data kodlaması, timestamp birimi -> sadece `comm/uts.py` değişir.
- UTS toplu/periyodik gönderim desteği -> sadece TX katmanı değişir.
- `msg.on_receive` kalacak mı.
- Aynı channel'ı paylaşan ailelerde bir paket iki ailenin signature'ıyla eşleşebilir (ilk aile kazanır).
- `Counter8` 16 bitlik alanda tutuluyor; ICD ile kontrol edilmeli.
- Unknown paket WARNING olarak loglanıyor; `listen` edilen kanalda beklenen paketler için seviye düşürülebilir.
- Her mesajın genel loga DEBUG yazılması (CSV ile tekrar) kalacak mı.
- UTS filtresi: arayüz (kanal) başına; kısmi bit maskeli signature byte'ını UTS'nin
  destekleyip desteklemediği; config alan adları/tipleri (doğrulama yok); gerçek HTTP gövdeleri; seri akışta filtre
  konumunun anlamı; okuma-ekleme-yazma tek işlem değil (aynı anda iki thread add_filter çağırırsa biri kaybolabilir);
  alım tamponunu boşaltma (clear) RX thread'iyle yarış yüzünden eklenmedi.
- Aynı kanalda signature'sız iki RX mesajı desteklenmiyor (gerekirse projenin tanıma fonksiyonu ile).
- Length = signature olan sabit boylu mesajlarla değişken boylu (kanala göre) bir mesaj aynı kanaldaysa, değişken
  paketin boyu sabit bir mesajın boyuna eşit olduğunda paketi sabit mesaj alır (signature önce denenir; CRC de
  tutabilir). Bu boylar çakışmamalı ya da signature'a ayırt edici başka bir alan eklenmeli.
- Periyodik gönderimde `after_send` yarışı (B12): test thread'i istek bitini pack ile after_send arasında yazarsa
  sıfırlama bu değeri siler (istek gitmez). **Bilinçli kullanım:** tek seferlik istek bitleri periyodik mesaj
  üzerinden değiştirilecekse bu risk bilinerek yapılır; gerekmiyorsa `comm.send()` ile tek seferlik gönderim
  kullanılır (yarış oluşmaz). Olası iyileştirme aşağıda.
- **RX doğrulamada kilitlenme (K1, çözüldü):** değişken boylu mesajda uzunluk alanı checksum boyundan küçük
  gelince RxPoller thread'i ölüyordu. Artık `LengthType.on_receive` alt sınırı (`min_length`) kontrol ediyor,
  `validate()` hook istisnasında `False` dönüyor, RX döngüsü tek paketteki hatayı loglayıp devam ediyor.
  Ayrıntı: `KNOWN_ISSUES.md` → K1. Paketin sonundaki fazla baytlar (K2) hâlâ karar bekliyor.
- Sonraki fazlar: sinyal geçmişi + UI köprüsü, CAPL benzeri SimulationNode (on_message, on_timer).

## Yapılabilecekler (olası iyileştirmeler)
Zorunlu değil; ihtiyaç olursa ele alınacak fikirler.

- **`after_send` yarışını daraltmak (B12):** `after_send` hook'ları da `on_send` gibi gönderilen paketin kopyasında
  çalışır; değişiklik canlı nesneye **bit bit** uygulanır: bir bit, gönderildiği değerden bu yana canlı nesnede
  değişmediyse hook'un sonucu yazılır, değiştiyse (test thread'i arada yazdı) canlı değer korunur.
  - `startReq=1` gitti, kimse dokunmadı → 0'lanır; `startReq=0` gitti, test arada 1 yazdı → 1 kalır, sonraki
    pakette gider; aynı bayttaki başka bitler (`mode`) korunur.
  - Maliyet: `_sent()` içinde ~15 satır + test; yeni API yok, proje tipleri değişmez.
  - Kısıtlar: pencere tamamen kapanmaz (okuma ile yazma arasında birkaç Python işlemi kalır; bugün tüm UTS isteği
    süresince açık); aynı değerin yeniden yazılması (1 → 1) ayırt edilemez, iki istek tek pakette birleşir;
    hook'un nesneye eklediği Python özellikleri (`msg.foo`) korunmaz, sadece alan değerleri geri yazılır.
  - Alternatif: "bir sonraki gönderimde bir kez" yardımcısı (`msg.once(...)`); istek TX thread'inde uygulanıp geri
    alınır, yarış yapısal olarak kalkar ama yeni API gerektirir.

## Tasarım 1: mesaj başına kilit ve `update()` (tasarım aşamasında, uygulanmadı)

**Sorun.** Periyodik gönderimde paketi TX thread'i hazırlıyor, test thread'i aynı mesaja yazıyor.
- Birbirine bağlı iki alan (`speed`, `mode`) ayrı ayrı yazılırken paket araya girerse yarım güncellenmiş içerik gider
  (CRC tutarlı, içerik karışık).
- B12: test `startReq=1` yazdığında gönderim ile `after_send` arasına denk gelirse `after_send` isteği gönderilmeden siler.

**Tasarım.** Her mesaj nesnesinin bir kilidi (`RLock`) var; bayrak, bekleyen listesi, gölge tampon yok.

| İşlem | Kilidi ne kadar tutar |
|---|---|
| TX gönderim döngüsü: kancalar → kopya → hesap → POST → `after_send` | Bir gönderim süresi (bir UTS isteği) |
| `msg.update(...)` | Sadece alanları yazarken |

```python
motor.update(speed=500, mode=2)
motor.update(startReq=1)                            # istek kaybolmaz; bir sonraki pakette gider
motor.update({"cmd.startReq": 1, "cmd.mode": 2})    # iç içe alan: nokta ile, sözlük olarak
```

- Alanlar adıyla yazılır; karşılaştırma yok, aynı değeri yazmak da istek sayılır.
- Değer atama `_defaults` ile aynı kural: hedef `FieldType` ise `.val`'e yazılır.
- `update` döndüğünde değerler canlı nesnededir.
- B12: `update` ile `after_send` aynı kilidin içinde; `update` ya gönderimden önce (değer bu pakete girer) ya
  `after_send`'ten sonra (bir sonraki pakete kalır) olur. İstek gönderilmeden silinmez.
- Bedel: `update`, aynı mesaj o an gönderiliyorsa en fazla bir gönderim süresi bekler. TX thread'i `update` yüzünden
  sadece alan yazma süresi kadar bekler. Kilit mesaj başına; diğer mesajlar etkilenmez.
- Kilitlenme yok: `update` kilidin içinde başka kilit almaz; TX'te sıra her zaman genel gönderim kilidi, sonra mesaj
  kilidi. `RLock` olduğu için kanca içinden aynı mesajın `update`'i kilitlenmez.

**Kapsam dışı.**
- Düz yazma (`motor.speed = 5`) kilitsiz kalır: CRC tutarlılığını `pack()`'teki kopya sağlar; alanlar arası tutarlılık
  ve B12 koruması yoktur. Kural: birbirine bağlı alanlar ve istek bitleri `update` ile yazılır.
- RX `decode` kilit almaz (tek kopyayla yazıyor). Alsaydı iki yönlü (`BOTH`) mesajda RX thread'i TX'in UTS isteğini beklerdi.
- Kanca içinde başka bir mesajı `comm.send` ile göndermemek.

**Tahmini maliyet.** `message/base.py` ~20 satır (`RLock`, `update`), `runtime/tx.py` ~3 satır (gönderim döngüsü
`with msg._lock:`), testler ~80 satır, dokümanlar ~30 satır.

**Değerlendirilen alternatifler.**
- Sadece `update` + kopya için kısa kilit (B12'yi kapatmaz).
- Bayrak + bekleyen değerler sözlüğü (B12'yi kapatır; `update` beklemez ama değer canlı nesneye gönderim bitince geçer,
  ek durum tutar).
- Gölge tampon + XOR ile birleştirme (aynı değerin tekrar yazılmasını göremez; daha fazla mekanik).

**Kararlar (sonradan verildi, aşağıda "Tasarım 1'e eklenen kararlar").**
1. İsim `update`; aynı adlı ICD alanı sınıf tanımında hata verir.
2. İç içe alanlar noktalı sözlükle, yol önbellekli; blok biçimi de var.
3. `snapshot()` sadece TX yönü olan mesajda kilit alır.

**`snapshot()` ve kilit.** `bytes(self)` tek bir bellek kopyası ve GIL altında yapılıyor; bir Python thread'inin tek
bir alan yazması da tek adım. Bu yüzden snapshot hiçbir zaman yarım yazılmış bir alan görmez ve `decode` ile her zaman
tutarlıdır (`decode` de tek kopyayla yazıyor). Görebileceği tek tutarsızlık başka bir thread'in **birden fazla alanlık**
bir `update`'inin ortası. Bu sadece aynı TX mesajını iki ayrı thread kullanırken olur.
- Kilit alırsa: `update`'in yarısını hiç görmez. Bedel: o mesaj o an gönderiliyorsa en fazla bir gönderim süresi bekler.
  Sadece RX olan mesajları TX hiç kilitlemediği için onlarda beklemez.
- Almazsa: bekleme yok; aynı mesajı tek thread yazıyorsa (normal kullanım) fark yok.
- `Record.snapshot()` (geçmiş) ve `event.snapshot()` değişmeyen baytlardan kopyalar; kilit gerekmez.
- Free-threaded Python'da (GIL yok, B13) tek kopyanın atomikliği garanti değildir; o durumda kilit şart olur.

## Tasarım 2: UTS sürücü katmanı (uygulanmadı; yerini Tasarım 2a aldı, ölçümler ve TX zamanlaması notları geçerli)

**Bugün UTS'e kim istek atıyor.**

| Kim | Thread | İstek | Sıra |
|---|---|---|---|
| Periyodik gönderim | TX | POST | `TxScheduler._send_lock` |
| `comm.send` | Test | POST | Aynı `_send_lock` |
| `comm.on_receive` işleyicisinden `comm.send` | Abone | POST | Aynı `_send_lock` |
| Alım yoklaması | RX | GET, kanal başına, sırayla | Kendi içinde sıralı; TX ile aynı anda gidebilir |
| `comm.control` (config, filtre) | Test | GET / POST | Sırasız; TX ve RX ile aynı anda gidebilir |

TX gönderimleri kendi aralarında sıralı; RX yoklaması ve kontrol çağrıları bu sıranın dışında. UTS'e aynı anda en fazla
bir POST, bir RX GET'i ve bir kontrol isteği gidebiliyor; UTS'in eşzamanlı istekleri nasıl karşıladığı bilinmiyor.
RX döngüsü `poll_interval`'i turu bitirdikten sonra bekliyor: tur = aralık + (kanal sayısı × GET süresi)
(3 kanal, 2 ms → 16 ms, ~190 GET/s). UTS yavaşladıkça yoklama aralığı da uzar.

**Tek thread TX kapasitesi (ölçüm, sahte UTS 2 / 5 ms gecikmeyle).** Kapasite ~1 / istek süresi. Aşılınca periyotlar
uyarısız uzuyor (2 ms'de 3 mesaj × 5 ms: 200 yerine 152 paket/s; 5 mesaj × 5 ms: 91). Geride kalınca
`sonraki = önceki + periyot` kuralı kaçanları peş peşe göndermeye çalışıyor.

**Tasarım.** `UtsDriver`, `UtsClient` ile aynı arayüzü sunar ve gerçek istemciyi sarar; Transport ve UtsControl değişmez,
`Comm` istemciyi sürücüyle sarar. Sorumlulukları:
1. Eşzamanlılık kuralı tek yerde: sınırsız (bugünkü) / tek istek (giden istek bitmeden diğeri gitmez) / en fazla N
   (semafor). UTS ölçülene kadar ayarlanabilir; varsayılan bugünkü davranış.
2. UTS düzeyinde bildirimler: istek hatası (`LinkError` tek kaynaktan), UTS yavaşladı / düzeldi, bağlantı koptu /
   geldi, TX gecikmesi (`TxLate`). Her istek için olay yok; sayaçlar ve süre istatistikleri `driver.stats`'ta.
3. UTS'in cevabı: `post` cevabı döndürür, sürücü protokolden bağımsız `UtsAck(ok, uts_time, ham_cevap)`'a çevirir;
   `MessageSent` bunu taşır, başarısız onay gönderilmedi sayılır. Protokole özel kısım (ör. 1553 durum kelimesi)
   gerekirse protokolün isteğe bağlı bir metoduyla okunur.
4. İleride: bağlantıyı açık tutma, yeniden bağlanma, yeniden deneme, UTS destekliyorsa tek GET'te çok interface.

**Tek istek kuralının bedeli.** RX yoklamaları aynı sıraya girer ve TX kapasitesinden yer (yukarıdaki ~190 GET/s).
Seçilirse ya öncelik gerekir (TX, RX yoklamasının önüne geçer; kilit yerine öncelikli sıra) ya da daha seyrek / toplu
yoklama.

**Tasarım 1 ile ilişkisi.** Kilit sırası: mesaj kilidi → `_send_lock` → sürücü kilidi (en içte, içinde başka kilit yok;
kilitlenme olmaz). Sürücü sıraya koyarsa TX bir RX isteğini bekleyebilir; mesaj kilidi ve `update` beklemesi o kadar
uzar (birkaç ms).

**Tahmini maliyet.** `uts/driver.py` ~80 satır, yeni olaylar ~15, `comm.py` ~5, testler ~120. API gelince `UtsAck` ~30;
gerekirse öncelikli sıra ~40.

**Sıra.** (1) Sürücüyü sarmalayıcı olarak eklemek: ayarlanabilir eşzamanlılık (varsayılan sınırsız), süre ölçümü,
sorun bildirimleri; davranış değişmez, UTS ölçülebilir hale gelir. (2) Ölçümden sonra tek istek / öncelik kararı ve
cevap biçimi.

**TX zamanlaması için ayrıca.** (a) Gecikme algılama: gönderim periyodun belli oranından fazla geç kalırsa uyarı ve
`TxLate` (~10 satır). (b) Geride kalınca kaçan periyotları peş peşe göndermek yerine atlamak ve takvimi şimdiye kaydırmak;
kaçanlar sayılır (~5 satır).

**Açık sorular (UTS).** Eşzamanlı istekleri kabul ediyor mu / sıraya mı koyuyor / hata mı veriyor? Bir GET ile birden
fazla interface okunabiliyor mu? POST cevabında durum, UTS zamanı, istek numarası var mı?

**Tasarım 1'e eklenen kararlar.** Blok biçimi aynı isimle: `msg.update(a=1)` alanları yazar; `with msg.update(): ...`
blok boyunca kilitler. Blok kuralları: kısa tutulur; içinden `comm.send` çağrılabilmesi için `tx.py`'de kilit sırası
önce mesaj kilidi sonra `_send_lock` olur.

**Karar: blok kısa tutulur ve TX bütün haberleşmeyi bekletmez.**
- Kural: blok mümkün olduğunca kısa; içinde `sleep`, `wait_new`, `wait_for`, UTS'e giden çağrı olmaz.
- Erteleme: TX thread'i periyodik bir mesajın kilidini beklemeden dener (`acquire(blocking=False)`). Doluysa o mesajın
  zamanını kısa bir adım ileri alır (ör. 1 ms, periyottan uzun olmamak üzere), `_send_lock`'u hiç almadan diğer
  mesajlarla devam eder. Böylece uzun bir blok sadece kendi mesajını geciktirir; diğer periyodik mesajlar ve RX etkilenmez.
- Ertelenen mesaj periyodundan fazla geç kalırsa TX gecikme uyarısı (`TxLate`, Tasarım 2) verilir; blok sorunu sessiz kalmaz.
- Tek seferlik `comm.send` (test ya da işleyici thread'i) kilidi bekleyerek alır: isteği yapan thread'in kendisi bekler.
- Maliyet: `tx.py`'de ~6 satır (deneme, erteleme), test: uzun blok sürerken diğer periyodik mesajın gecikmemesi.

**Karar: `update` biçimleri ve iç içe alanlar.**
- Argümanlı biçim: `msg.update(speed=500)` ve iç içe alanlar için noktalı sözlük
  `msg.update({"speed": 500, "cmd.mode": 2})`. Noktalı yol, sınıf ve yol başına bir kez bölünüp önbelleğe alınır
  (`functools.lru_cache`); alan arama ve `FieldType` kontrolü her çağrıda yapılır, yanlış ad `AttributeError` verir.
- Blok biçimi: `with msg.update(): msg.cmd.mode = 2`. En hızlısı; ama düz atama olduğu için yanlış alan adı hata vermez
  (nesneye yeni bir Python özelliği eklenir), bugünkü düz yazmayla aynı.
- Ölçüm (`speed` + `cmd.mode` birlikte, yazma başına): düz atama kilitsiz 0,17 µs; blok 0,32 µs; noktalı sözlük yol
  önbellekli 0,81 µs; iç içe sözlük `{"cmd": {"mode": 2}}` 1,02 µs; noktalı sözlük önbelleksiz 1,11 µs. Hepsi bir UTS
  isteğinin (ms) binde birinden az; seçim kullanım ve güvenlik için. `snapshot()` sadece TX yönü olan mesajda kilit alır; RX'te `decode`
tek kopyayla yazdığı için gerekmez. `pack()`'teki kopya ve seçerek geri yazma kalır: düz yazmalar kilitsiz olduğu için
CRC tutarlılığını onlar sağlar.

## Tasarım 2a: backend sınırı ve UTS istemcisi (adım adım)

UTS hakkında öğrenilenlerle Tasarım 2'deki "sürücü" yerine istemci korunur; UTS'e özgü kısım tek pakette toplanır.

**UTS hakkında bilinenler.**
- POST tek mesaj gönderir. Cevap (OK / NOT OK) gelmeden aynı interface'e ikinci POST öncekini ezebilir.
- Farklı interface'ler ayrı buffer kullanır; farklı interface'lere aynı anda POST / GET atılabilir. UTS'te TX ve RX
  ayrı thread'lerde.
- POST OK cevabında zaman var: `{"statusInfo": {"status": "OK", "code": 200, "message": "..."}, "timestamp": 1731500000000000}`.
  Hatalar aynı `statusInfo` ile döner; seri POST: 400 boş mesaj / port kapalı, 404 geçersiz interface, 500 HAL timeout,
  503 eINIT modu; seri GET: 404, 503. OK gövdesi endpoint'e göre değişir. Her gövde JSON.
- GET buffer'ı tüketir (sonraki GET boş dönebilir): `{"statusInfo": {...}, "messages": [{"message": [1, 2, 3],
  "timestamp": ...}], "isBufferOverflow": false}`. Taşmada UTS sadece bayrağı set eder; `DELETE` gerekmez.
- RX buffer boyu config'den; dolunca ring çalışır ve "buffer dolu" bayrağı vardır.
- Ölçüm (Ethernet loop, iki interface): periyodik TX en fazla ~230 mesaj/sn (periyot 1 ms verilse de); RX'te kayıp
  yok. Sınır TX: POST başına ~4,3 ms ve tek TX thread'i.

| Yetenek | Serial | Ethernet | MIL-1553 | CameraLink |
|---|---|---|---|---|
| Kök yol | `/serials` | `/ethernet` | `/1553` | `/cameralink` |
| Mesaj (POST / GET / GET-index / DELETE) | var | var | var | var |
| Global config | POST + GET `/serials/configs` | kısmi: GET (POST yorumda) | yok | yok |
| Arayüz config `/{no}/configs` | POST + GET | POST + GET | kısmi (kodda var, yorumda) | yok |
| Config tamamla `/configs/complete` | POST | POST | kısmi (yorumda) | yok |
| Filtre `/{no}/filters` | POST / GET / DELETE | POST / GET / DELETE | POST / GET / DELETE | yok |
| Mesaj veri tipi | `UInt8[]` | `UInt8[]` | `UInt16[]` (word) | `UInt8[]` |
| TX timeout | baud rate'e göre, en az 1 sn | sabit 1 sn | sabit 1 sn | sabit 1 sn |
| Port açık kontrolü | var | yok (TODO) | yok (TODO) | var |
| Platform | tümü | tümü (fiilen UDP; TCP TODO) | yalnızca Windows HAL | yalnızca Windows HAL |
| Arayüz sayısı | COM port + Moxa | config'ten | fiilen 1 (TX sabit kodlu) | 1 |

**Kararlar.**
- Sınır bayt düzeyinde (`Backend`); UTS'e özgü kısım `backend/uts/`. İstekleri `UtsApi` yapar, şimdilik eldeki
  `ApiWrapper` üzerinden (`WrapperUtsApi`); tam istemci sonra aynı sözleşmeyle yazılır.
- Periyodik TX ve RX backend'de değil, TX / RX katmanında kalır (paket her gönderimde mesajdan hazırlanır;
  zaman aşımı ve dispatch mesajı bilir). İstisna UTS'in kendi periyodik gönderimi: `UtsApi` metodu olur, ne zaman
  çağrılacağına TX katmanı karar verir.
- İstek cevabı dönüş değeridir (`Response`); durum değişiklikleri (bağlantı, gecikme) olaydır. İstek başına olay yok.
- Hata teste tek tek verilmez: loglanır, sayılır, tekrar denenmez. Eşik aşılınca (art arda N hata ya da T sn
  sessizlik) interface "düştü" sayılır ve test durdurulabilir.
- İstek timeout'u backend'de; bus'a göre (UTS TX timeout'u + pay; seride baud'a göre).
- Thread'ler kanal başına (RX ve TX); RX zaman aşımı kontrolü ayrı tek bir denetçide. Böylece cevap vermeyen bir
  interface diğerlerini bekletmez.
- Bus ayarları (baud, port, buffer boyu) kanal tanımında durur; `comm.open()` sırasında UTS ile karşılaştırılır
  ("check") ya da yazılır ("apply" + complete).
- Cihazlar (power supply vb.) kanal yapısına sokulmaz: ayrı `Instrument` + `Link` katmanı; `Comm` ile birlikte bir
  `Bench` altında açılır / kapanır, aynı log ve hata politikasını kullanır. İlk cihaz gelince eklenir.

**Adımlar.**
1. Backend sınırı, `Response`, UTS paketi, `WrapperUtsApi` şablonu. **Uygulandı** (`v2.1-backend` dalı).
2. Timeout, hata ve cevap logu, interface başına TX kilidi. **Uygulandı.** Süre codec'ten (Ethernet / 1553: 2 sn,
   seri: 3 sn; GET için aynı), `UtsBackend(timeout=...)` ile tek değer verilebilir. `UtsBackend` süreyi ölçer
   (`Response.elapsed`), `asl_testing.uts`'e yazar ve `api`'nin istisnasını başarısız `Response`'a çevirir.
   Kilit sadece POST için; GET beklemez. Seri süresi baud'dan hesaplanmıyor (Adım 6). UTS kesikken her yoklama
   bir ERROR satırı yazar; bunu Adım 3'teki hata politikası sınırlayacak.
3. Hata politikası. **Ertelendi** (bugünkü işlevi etkilemiyor; tasarımı aşağıda "Adım 3: hata politikası").
4. Kanal başına RX ve TX thread'i, ayrı zaman aşımı denetçisi. **Uygulandı** (ayrıntı: "Thread modeli").
   Yoklama sabit aralıkla; "veri geldiyse hemen tekrar sor" kuralı eklenmedi (UTS yükü ölçülmeden karar verilmedi).
5. UTS zamanı `MessageSent.timestamp`'e (CSV `uts_time`), `isBufferOverflow` bayrağı `RxOverflow` olayına. **Uygulandı.**
   `DELETE` kapsamdan çıktı (GET buffer'ı zaten tüketiyor).
6. Kanal tanımında bus ayarları, açılışta config kontrolü, port açık kontrolü.
7. Tasarım 1 (mesaj kilidi ve `update()`).
8. `TxLate`, kaçan periyotları atlama, performans ölçümü (keep-alive, POST süresi).
9. İhtiyaç olunca: `Bench` ve cihaz katmanı, tam UTS istemcisi, UTS periyodik gönderimi, CameraLink.

**Açık sorular (UTS).** `GET-index` ne döndürür; `complete` ne zaman gerekir; Ethernet ve 1553 cevapları seri ile
aynı mı; timestamp birimi mikrosaniye mi; eldeki modül cevabı ham JSON olarak mı veriyor; ikinci POST reddedilir mi, öncekinin yerine mi geçer; seri TX timeout formülü; keep-alive;
`ApiWrapper`'ın imzaları, dönüş tipi ve thread güvenliği.

**Adım 3: hata politikası (tasarlandı, ertelendi).** Amaç: hatalar teste tek tek verilmez; bağlantı gerçekten
kopunca test bunu öğrenir ve durur.
- Sayma: her gönderim ve yoklama sonucu kanal başına bir izleyiciye (`LinkMonitor`, `runtime/link.py`) bildirilir;
  izleyici sadece `Response.ok`'a bakar, backend'den bağımsızdır. Başarılı istek seriyi sıfırlar.
- Eşik süreye dayalı: hatalar kesintisiz 5 sn sürerse (en az 3 hata) kanal "düştü". Sadece sayaç yanıltır: UTS
  kapalıyken 10 hata 0,1 sn'de, cevap vermezken (timeout) 20 sn'de birikir. Sayaç eşiği isteğe bağlı, varsayılan kapalı.
  `Comm(..., errors=ErrorPolicy(max_time=5.0, max_errors=None, action="abort"))`.
- 400 / 404 bizim tarafın hatasıdır, tekrarla düzelmez: beklemeden "düştü" (öneri).
- Düşünce: bir kez ERROR, `LinkDown(channel, errors, duration, last_error)`. `action="warn"` ise test sürer,
  ilk başarılı istekte `LinkUp(channel, duration)`. `action="abort"` ise `Comm` nedeni saklar.
- Testi durdurma: arka plan thread'i test thread'ine istisna fırlatamaz; `comm.send`, `start`, `wait_new`, `wait_for`,
  `wait_sent` nedeni görünce `LinkLost` fırlatır, bekleyen `wait_for` hemen uyanır. Yeni yardımcılar `comm.sleep(t)`
  ve `comm.check()`. `CommTestCase` bitişte `comm.check()` çağırır; ilk `LinkLost`'tan sonra kalan testler atlanır (öneri).
- Log sınırlama (`UtsBackend`, interface başına): serinin ilk hatası ERROR, sonrakiler DEBUG, düzelince tek INFO
  ("ok again after N failed requests"). Bugün UTS kesikken her yoklama bir ERROR satırı yazıyor.
- `RxTimeout` ayrı kalır (UTS cevap veriyor, cihaz göndermiyor). Tekrar deneme yok.
- Tahmini maliyet: `runtime/link.py` ~70 satır, olaylar ~15, `tx.py` / `rx.py` ~6, `comm.py` ~25,
  `backend/uts/backend.py` ~15, `services/errors.py` ~4, `tests/base.py` ~10, testler ~120.
- Karar bekleyenler: varsayılan eşik (5 sn, en az 3 hata); varsayılan davranış (`abort` / `warn`); 400 / 404'ün
  hemen düşürmesi; ilk kopmadan sonra kalan testlerin atlanması.
