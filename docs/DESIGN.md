# BaseMessageStructure - Tasarım Notları

Python ctypes ile Ethernet/RS422 haberleşen projeler için test altyapısı.
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
    channel.py               Channel, EthernetChannel, Rs422Channel, ChannelSet, ProtocolType
    framing.py               Splitter, Envelope, Framing
  uts/                       3. Sürücü: UTS'ye nasıl ulaşılır
    client.py                UtsClient (arayüz), UtsFrame
    http.py                  HttpUtsClient (yer tutucu)
    fake.py                  FakeUtsClient
    control.py               UtsControl: config ve filtre (testten dikine, doğrudan çağrı)
    filters.py               filtre hesapları (mesaj -> hattaki byte konumu, değer)
  runtime/                   4. Çalışma zamanı: ne zaman ve nasıl taşınır
    transport.py             envelope, adres başına sorgu, splitter, kanal tespiti
    rx.py                    RxPoller: sorgu, WireReceived, zaman aşımı
    tx.py                    TxScheduler: send (kilit), periyodik gönderim, WireSent
    dispatcher.py            lookup + decode + olay, unknown listesi
    clock.py                 UtsClock: tahmini UTS "şimdi"si
  events/                    5. Olaylar
    types.py                 mesaj ve hat seviyesi olaylar
    bus.py                   EventBus: abone başına kuyruk + thread
  services/                  6. Olay aboneleri
    history.py               CommLogger: mesajlaşma geçmişi (CSV)
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
Transport        kanal envelope'u, adres (protocol + interface) başına sorgu, splitter, kanal tespiti
UtsClient        HTTP (POST transfer, GET mesaj listesi); UTS'ye özgü her şey burada
```

## Kanal ve framing
- `Channel`: generic kanal tanımı = protokol (alt sınıf: `EthernetChannel`, `Rs422Channel`) + interface + `Framing`.
  IP, port, baud gibi fiziksel ayarlar kanalda yok. Eşitlik kimliğe göre: her kanal bir kez tanımlanır.
- `Framing(splitter, envelope)`, ikisi de isteğe bağlı; varsayılanları bir şey yapmaz.
  - Splitter: akış seviyesi, kanal belli olmadan çalışır; bir adreste en fazla bir splitter.
  - Envelope: paket seviyesi; `on_send` ekler, `on_receive` çıkarır, paket bu kanalın değilse `None`.
- Proje kanallarını `ChannelSet` ile tanımlar (`project/channels.py`): isimleri verir, kuralları sınıf tanımlanırken
  kontrol eder (adres başına en fazla bir splitter, en fazla bir envelope'suz kanal). `Comm`'a verilmez.
- Kanal mesaja sınıf varsayılanı olarak verilir (`_channel = MyChannels.CONTROL`); nesne oluştururken verilmez.
- Aynı adresi paylaşan kanallar: adres bir kez sorgulanır; RX'te kanallar sırayla denenir (envelope'lular önce,
  envelope'suz en son), paketi kabul eden ilk kanal seçilir; hiçbiri kabul etmezse paket unknown olur.
- Sorgulanan adresler: RX mesajı kayıtlı kanalların ve `comm.listen(kanal)` ile eklenenlerin adresleri.
  RX mesajı olmayan bir kanalın paketleri, o kanal `listen` ile eklenmedikçe tanınmaz.
```
TX:  msg.pack() -> kanal envelope.on_send -> UTS (protocol, interface)
RX:  UTS (adres) -> adresin splitter'ı -> kanallar sırayla envelope.on_receive -> Dispatcher
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
- Mesaj akışından ayrı, dikine bir yol: test -> `comm.control` (UtsControl) -> UtsClient. RX/TX thread'leri ve
  olaylar kullanılmaz; çağrı senkron, sonucu döner ya da istisna fırlatır (`UtsError`). Her çağrı INFO loglanır.
- Hedef bir mesaj nesnesi ya da kanal; mesaj kendi kanalını verir. Kanalın protocol + interface'i UTS arayüzünü seçer.
- `get_config` / `set_config(**ayarlar)`, `get_filter -> (kind, groups)`, `set_filter(groups, kind)`, `clear_filter`.
- `add_filter(msg)` / `remove_filter(msg)`: filtreyi okur, mesajın signature byte'larını ekler/çıkarır, geri yazar.
  Konumlar hattaki konumlardır: kanal envelope'unun `offset`'i (mesajın önündeki byte sayısı) eklenir
  (`Envelope.offset`, varsayılan 0; örnek `EthHeader.offset = 8`).
- UtsClient'ın yönetim metotları soyut değil (varsayılan `NotImplementedError`); FakeUtsClient bunları saklar,
  gelen paketlere uygulamaz.
- Dikkat: ilk `add_filter` arayüzü "her şey geçer"den "sadece filtre geçer"e çevirir; aynı arayüzdeki (ve aynı adresi
  paylaşan kanallardaki) filtreye eklenmemiş mesajlar artık gelmez.

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
- Altyapının yazdıkları: UTS send/poll hatası ERROR (traceback ile), abone exception'ı ERROR,
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
- 1 RxPoller, 1 TxScheduler, abone başına 1 thread. Mesaj başına thread yok.
- Gönderim tek kilit altında: counter, checksum, byte, UTS isteği.
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
  `periodic_rx` (zaman aşımı), `periodic_tx` (aday listesi; gönderim `comm.start` ile).
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
- UTS filtresi: arayüz başına (aynı adresi paylaşan kanallar paylaşır); kısmi bit maskeli signature byte'ını UTS'nin
  destekleyip desteklemediği; config alan adları/tipleri (doğrulama yok); gerçek HTTP gövdeleri; seri akışta filtre
  konumunun anlamı; okuma-ekleme-yazma tek işlem değil (aynı anda iki thread add_filter çağırırsa biri kaybolabilir);
  alım tamponunu boşaltma (clear) RX thread'iyle yarış yüzünden eklenmedi.
- Aynı kanalda signature'sız iki RX mesajı desteklenmiyor (gerekirse projenin tanıma fonksiyonu ile).
- Length = signature olan sabit boylu mesajlarla değişken boylu (kanala göre) bir mesaj aynı kanaldaysa, değişken
  paketin boyu sabit bir mesajın boyuna eşit olduğunda paketi sabit mesaj alır (signature önce denenir; CRC de
  tutabilir). Bu boylar çakışmamalı ya da signature'a ayırt edici başka bir alan eklenmeli.
- Periyodik gönderimde `after_send` yarışı: test thread'i istek bitini pack ile after_send arasında yazarsa
  sıfırlama bu değeri siler (istek gitmez). Koruma yok; gerekirse "bir sonraki gönderimde bir kez" yardımcısı.
- **RX doğrulamada kilitlenme (K1, çözüldü):** değişken boylu mesajda uzunluk alanı checksum boyundan küçük
  gelince RxPoller thread'i ölüyordu. Artık `LengthType.on_receive` alt sınırı (`min_length`) kontrol ediyor,
  `validate()` hook istisnasında `False` dönüyor, RX döngüsü tek paketteki hatayı loglayıp devam ediyor.
  Ayrıntı: `KNOWN_ISSUES.md` → K1. Paketin sonundaki fazla baytlar (K2) hâlâ karar bekliyor.
- Sonraki fazlar: sinyal geçmişi + UI köprüsü, CAPL benzeri SimulationNode (on_message, on_timer).
