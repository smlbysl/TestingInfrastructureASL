# BaseMessageStructure - Tasarım Notları

Python ctypes ile birden fazla bus üzerinden (Ethernet, RS422, MIL-STD-1553, CAN; ileride ARINC, UART, I2C)
haberleşen projeler için test altyapısı. ICD'ye bağlı mesaj nesneleri oluşturulur; haberleşme UTS (Windows'ta çalışan
HTTP servisi) üzerinden yapılır. Kod içindeki yorumlar İngilizce.

İlgili belgeler: `docs/KNOWN_ISSUES.md` (bilinen sorunlar ve durumları), `docs/RX_HISTORY_HANDOFF.md` (mesaj geçmişi
analizi), `docs/USAGE.md` ve `docs/manual.html` (kullanım), `docs/TEST_API.md` (arayüz referansı),
`prototypes/pdu_layers/` (PDU katmanlarının ilk, bağımsız prototipi).

## Dosya yapısı
```
asl_testing/                 ÇERÇEVE (projeden bağımsız)
  __init__.py                tek giriş: from asl_testing import Comm, Mil1553Channel, Timing ... ; GIL kontrolü
  comm.py                    Comm: test tarafının tek giriş noktası
  message/                   1. Mesaj modeli (SDU): ne gönderilir
    base.py                  BaseMessageStructure: init (PCI), validate/decode, pack, snapshot, callout
    fields.py                FieldType hook'ları, Length/Counter/Checksum/Ascii
    signature.py             Signature: alan listesinden offset+mask, tek ID (SDU içinde)
    history.py               Record, MessageHistory (ring buffer), next_seq
    timing.py                Timing(period, tolerance), Direction
    state.py                 RxState / TxState (sayaçlar, zaman, history)
  protocol/                  2. Protokol katmanı: PDU = PCI + SDU, bus türleri (UTS'den bağımsız)
    pdu.py                   Pci, NoPci, Pdu
    base.py                  Protocol: PCI tipi, kurallar, receive
    stream.py                ByteStream (Ethernet, Serial), Header (in-band PCI), Splitter
    mil1553.py               Mil1553 (node + subnet, 16 bit word)
    can.py                   Can (can_id)
  channel/                   3. Kanal: interface + protokol + kayıtlı mesajlar
    channel.py               Channel, EthernetChannel, Rs422Channel, Mil1553Channel, CanChannel, ChannelSet
    registry.py              ChannelRegistry: kanal başına kayıt, tanıma (PCI -> signature)
  uts/                       4. Geçit (UTS): PDU'nun UTS'de nasıl yazıldığı
    client.py                UtsClient (JSON: post / get), UtsError
    adapters.py              UtsAdapter: protokol başına PDU <-> UTS JSON; UtsFormatError
    http.py                  HttpUtsClient (yer tutucu)
    fake.py                  FakeUtsClient (device_sends, device_sends_bytes, inject)
    control.py               UtsControl: config ve filtre (testten dikine, doğrudan çağrı)
    filters.py               filtre hesapları (mesaj -> hattaki byte konumu, değer)
  runtime/                   5. Çalışma zamanı: ne zaman ve nasıl taşınır
    transport.py             adaptör + protokol: adres başına sorgu, splitter, kanal tespiti
    rx.py                    RxPoller: sorgu, WireReceived, zaman aşımı
    tx.py                    TxScheduler: send (kilit), periyodik gönderim, WireSent
    dispatcher.py            kanal registry'si + decode + olay, unknown listesi
    clock.py                 UtsClock: tahmini UTS "şimdi"si
  events/                    6. Olaylar
  services/                  7. Olay aboneleri: CommLogger (CSV), ErrorLog, monitor/
projects/example_project/    PROJEYE ÖZEL (ICD)
  header.py                  ProjectBase (Ethernet / RS422 header'ı) ve aileler
  buses.py                   1553 ve CAN projeleri ve mesajları
  types.py, channels.py, framing.py (EthHeader), messages.py
examples/                    example, example_send_receive, multi_bus, monitor_demo (depo kökünden python -m)
tests/                       unittest (pytest ile de koşar): base (CommTestCase, HardwareTestCase), birim + entegrasyon
```

Bağımlılık yukarıdan aşağıya: `comm.py` → `services` / `runtime` → `events`, `uts` → `channel` → `protocol`;
`message` → `channel`. `projects/` sadece `from asl_testing import ...` kullanır.

## Katmanlar (PDU = PCI + SDU)
```
Test kodu        mesaj nesneleri + Comm (send, start/stop, wait_new / wait_for, on_receive, unknown)
Mesaj            SDU: ctypes yapısı; signature SDU içindeki alanlardan
Protocol         PCI: protokolün alanları (1553 node/subnet, CAN id, Ethernet header'ı); kurallar; tanıma
Channel          interface + protocol nesnesi + registry (mesajlar kanala kaydolur)
UTS adaptörü     PDU <-> UTS JSON (protokol başına bir tane)
UtsClient        HTTP: POST/GET /{path}/{interface}/messages; sadece JSON, protokolden habersiz
```
AUTOSAR isimlendirmesi: SDU üst katmanın verisi, PCI bu katmanın eklediği alanlar, PDU = PCI + SDU.
Bir alanın PCI mi SDU mu olduğu, protokol katmanına mı mesaja mı ait olduğunu söyler (ör. 1553 node/subnet PCI'dır).

```
TX:  msg._pack() -> (PCI, SDU) -> protocol.check_sdu -> adapter.to_uts -> UTS POST (path, interface)
RX:  UTS GET (adres) -> adapter.from_uts -> birimler -> splitter (byte stream) -> kanallar sırayla
     protocol.receive -> PDU -> kanal registry'si (PCI, signature) -> msg.decode -> olay
```

## Protokol katmanı (protocol/)
- `Pci`: frozen dataclass; alanları o protokoldeki adrestir. `key()` registry anahtarı, `names()` zorunlu alanlar.
  `NoPci` (alanı yok): düz Ethernet / RS422.
- `Protocol`: `path` (UTS'deki bus adı), `pci_type`, `offset` (hatta SDU'nun önündeki byte sayısı, filtreler için),
  `make_pci(**adres)` (eksik alan `TypeError`, fazlası `TypeError`, aralık dışı `ValueError`), `check_sdu` (TX'te ve
  sabit boylu mesajda tanımda), `wire(pdu)` (log ve hat olayları için byte hali), `receive(birim, ts)` (bu kanalın PDU'su
  ya da `None`: sıradaki kanal denenir), `accepts_all` (her birimi kabul eder mi; adres başına en fazla bir tane).
- Protokol nesnesi kanala aittir: aynı türden iki kanal farklı ayarlanabilir (biri header'lı, biri header'sız).
- `ByteStream` (`Ethernet`, `Serial`): hat sadece byte taşır.
  - `Header` (eski Envelope): in-band PCI. `encode(pci, sdu)`, `decode(data) -> (pci, sdu) | None`, `offset`.
    Adres taşımayan header (örnek `EthHeader`) `NoPci` kullanır.
  - `Splitter`: akış seviyesi; kanal belli olmadan çalışır, adres başına en fazla bir tane.
- `Mil1553`: PCI `node` + `subnet` (1..32, zorunlu); SDU 1..32 adet 16 bit word; word byte sırası `byteorder`
  (varsayılan big: BigEndianStructure mesajında bir `c_uint16` alanı bir word'e denk gelir).
- `Can`: PCI `can_id` (11 ya da 29 bit); SDU en fazla 8 byte.
- Yeni protokol eklemek: `Pci` alt sınıfı + `Protocol` alt sınıfı (path, pci_type, kurallar) + `UtsAdapter` alt sınıfı
  (`register_adapter(ProtokolSınıfı, AdaptörSınıfı)`) + isteğe bağlı bir `Channel` alt sınıfı.

## UTS istemcisi ve adaptörler (uts/)
- `UtsClient`: `post(path, interface, body)`, `get(path, interface) -> list[dict]`; yönetim metotları
  (`get/set_config`, `get/set_filter`) isteğe bağlı. Protokol bilgisi yok.
- `UtsAdapter` (protokol başına): `to_uts(protocol, pdu) -> body`, `from_uts(protocol, item) -> birimler`
  (byte stream için `bytes`, PCI'ı veriyle yan yana gelen bus'lar için `Pdu`), `timestamp(item)`.
  Varsayılanlar `ADAPTERS` tablosunda; `Comm(..., adapters={Protokol: adaptör}, time_unit=...)` ile değiştirilir.
- Biçimler (gerçek UTS ile doğrulanacak):
  - byte stream: `{"message": [b0, b1, ...], "timestamp": t}`
  - 1553: `{"message": [node, subnet, word_count, w0, ...], "timestamp": t}`
  - CAN: `{"id": can_id, "message": [...], "timestamp": t}` (tamamen varsayım)
  - timestamp birimi bilinmiyor: `time_unit` = UTS biriminin saniye karşılığı (varsayılan 1.0).
- Biçimi bozuk öğe `UtsFormatError`: geçit sorunu, `LinkError(operation="poll")` olarak yayınlanır, ERROR loglanır;
  aynı cevaptaki diğer öğeler yine işlenir.
- `FakeUtsClient`: aynı JSON; `device_sends(msg)` (mesaj nesnesi, PCI'ı ile), `device_sends_bytes(kanal, sdu, pci)`
  (bozuk paketler için; header protokol tarafından eklenir), `inject(path, interface, item)` (ham UTS öğesi).
  Config ve filtreleri saklar, gelen öğelere uygulamaz.

## Kanal ve registry (channel/)
- `Channel(interface, protocol)`; kolaylık sınıfları `EthernetChannel(i, header=, splitter=)`,
  `Rs422Channel(...)`, `Mil1553Channel(i, byteorder=)`, `CanChannel(i, extended=)`. Adres = (UTS path, interface).
  Fiziksel ayarlar (IP, baud, seri mod) kanalda yok. Eşitlik kimliğe göre.
- `ChannelSet` isimleri verir ve kuralları tanımda kontrol eder: bir adreste tek protokol türü, en fazla bir
  splitter, her birimi kabul eden (header'sız) en fazla bir kanal.
- Mesajlar kendi kanalına kaydolur (`channel.registry`). Tanıma sırası:
  1. PCI: `pdu.pci.key()` slotu (node/subnet, CAN id; düz byte stream'de tek ortak slot)
  2. signature'sız bir mesaj slotundaki her paketi alır (slotta tek başına olmalı)
  3. değilse SDU içindeki signature'ı tutan mesaj
  4. hiçbiri: unknown
- Kurallar kayıtta kontrol edilir: signature'sız mesajın yanına başka RX mesajı kaydolamaz (ve tersi); aynı slotta aynı
  signature ID'si iki farklı sınıfta olamaz. Belirsizlik çalışma sırasında değil tanımda hata verir. Aynı slotta farklı
  signature tanımları (farklı aileler) statik olarak kontrol edilemez: bir paket ikisine uyarsa önce kaydolan alır; WARNING loglanır.
  Not: v2.1-base'deki "önce signature, yoksa kanalın signature'sız mesajı" davranışı (sabit boylu mesajlarla tek bir
  değişken boylu mesajın aynı kanalı paylaşması) artık yok; bu durumda mesajlar ayırt edici bir alanla ayrılmalı.
- Aynı sınıf + PCI + signature + yön ile yeniden oluşturulan nesne eskisinin yerini alır (`_registered = False`,
  scheduler eskisini düşürür, geçmişi yeni nesnede boş başlar).
- TX-only nesneler kayıtta tutulur (periyodik gönderim, temizlik) ama gelen paket almaz.
- Sorgulanan adresler: RX mesajı kayıtlı kanalların (projelerin kanalları) ve `comm.listen(kanal)` ile eklenenlerin.
  Aynı adres bir kez sorgulanır; kanallar header'lılar önce, header'sız en son denenir.
- `Project.clear_registry()`: projenin nesnelerini kullandığı bütün kanallardan çıkarır (testler arası).

## Mesaj katmanı (message/)
- Hiyerarşi: BaseMessageStructure -> Proje (endian, header alanları, varsayılan kanal) -> Aile (`_signature`) ->
  mesaj sınıfı -> nesne. Birden fazla bus varsa her bus kendi projesi olabilir (`buses.py`: `Mil1553Base`, `CanBase`).
- PCI: kanalın protokolünün alanları nesne oluştururken anahtar kelime olarak verilir (`bit_report(node=5, subnet=3)`)
  ya da sınıf varsayılanı `_address` (`{"can_id": 0x123}`). `msg.pci` ile okunur.
- Sabit boylu bir mesaj protokole sığmıyorsa (CAN'da 8 byte'tan büyük, 1553'te tek sayıda byte) tanımda `ValueError`.
- İsimlendirme: `_x_` sadece ctypes; sınıf ayarları `_x`; nesne bilgisi alt çizgili, dışarıya property.
- `_defaults` + `initialize()`; alan tipi hook'ları: `on_init`, `on_send` (pack içinde, kopya üzerinde), `on_receive`
  (doğrulama; istisna fırlatırsa paket geçersiz), `after_send` (başarılı gönderimden sonra, kilit altında).
- Aynı byte'ı paylaşan bitler tek bir özel tipte (örnek `CmdByte`): istek biti `after_send`'de sıfırlanır.
- `msg.on_receive` (RX thread'inde, decode'dan sonra) ve `comm.on_receive` (kendi thread'inde) ikisi de var.

## Mesaj geçmişi, snapshot ve tutarlı okuma/yazma
- Canlı nesne = son geçerli paketin görünümü. Tek alan okuması her zaman tutarlı.
- `decode`: yeni görüntü önce hazırlanır, tek `memoryview` atamasıyla yazılır (GIL bırakılmaz); okuyan thread eski ya
  da yeni paketi görür, yarım/sıfır hal görmez. (Ölçüm: eski decode 4,6 milyon tutarsız okuma, yeni 0.)
- `msg.snapshot()`: o anki değerlerin tutarlı kopyası; birden fazla alan aynı paketten okunacaksa kullanılır.
  Snapshot kayıtlı değildir ve nesne bilgisi (kanal, PCI, durum) taşımaz.
- `msg.rx_history` / `msg.tx_history` (`MessageHistory`): her geçerli/gönderilen paket bir `Record(seq, timestamp,
  host_time, image, cls)`. Kapasite `_history` (varsayılan 64) ya da `history=` ile; taşan en eski kayıt düşer
  (`dropped`). Aynı poll'de gelen birden fazla paketin ara değerleri kaybolmaz.
- Okuyucu kendi konumunu tutar: `mark()`, `since(mark)`, `last()`; kimse kimsenin verisini tüketmez (`has_new`'den farkı).
- `comm.wait_for(msg, predicate, timeout, after=mark)`: predicate her paketin snapshot'ı ile çağrılır; poll'ün ortasındaki
  bir değer de bulunur; yeni kayıt gelince uyanır (polling yok). Kayıt ya da `None` döner.
- `seq` global ve monoton: aynı poll'deki paketler aynı zaman damgasını taşısa da sıraları bellidir.
- Olay görüntüsü (`MessageReceived.image`) paketin kendisidir, callout'lardan öncedir; history kaydıyla aynıdır.
- `pack`: kullanıcı callout'ları canlı nesnede çalışır; sonra tek kopya alınır, length/counter/checksum o kopyada
  hesaplanır, hattaki byte'lar ve `MessageSent.image` o kopyadan üretilir, özel alanların yeni değerleri nesneye geri
  yazılır. Böylece başka thread'in yazdığı bir alan eski checksum ile gitmez.
- Bu korumalar GIL'e dayanır; GIL'siz (free-threaded) Python'da `import asl_testing` hata verir.

## Yeni paket kontrolü ve son paketin zamanı
- `msg.has_new()` / `msg.has_sent()`: son çağrıdan bu yana sayı; çağrı sıfırlar. `peek_new()` / `peek_sent()` sıfırlamaz.
  `comm.wait_new(msg)` / `comm.wait_sent(msg)` bunlarla bekler. Birden fazla tüketici varsa history (`mark`) kullanılmalı.
- Gönderim sayacı başarılı UTS gönderiminde artar (`pack()` tek başına sayılmaz).
- `msg.rx_timestamp` (UTS), `msg.rx_host_time`, `msg.rx_age`. Bu alanlar ayrı ayrı güncellenir; değer ve zaman birlikte
  gerekiyorsa history kaydı kullanılır.

## Olaylar
- Mesaj seviyesi: `MessageReceived`, `MessageSent`, `InvalidReceived`, `UnknownReceived`.
  `raw` = SDU (mesaj byte'ları, protokol header'ı yok); `UnknownReceived.pci` gelen paketin adresi (kanal kabul ettiyse).
- Hat seviyesi: `WireReceived` (hattan gelen her paket, header dahil; `protocol` = UTS path) ve `WireSent`.
  PCI'ı veriyle yan yana gelen bus'larda (1553, CAN) `wire` SDU'dur.
- Bir paket için önce hat seviyesi, sonra mesaj seviyesi olay yayınlanır. `EventBus.unsubscribe` tekrar çağrılabilir.

## UTS yönetimi (comm.control)
- Dikine yol: test -> `comm.control` -> UtsClient; senkron, `UtsError` fırlatabilir; her çağrı INFO loglanır.
- Hedef mesaj ya da kanal; kanalın UTS path + interface'i arayüzü seçer.
- `add_filter(msg)` / `remove_filter(msg)`: filtreyi okur, mesajın signature byte'larını ekler/çıkarır, geri yazar.
  Konumlar hattadır: protokolün `offset`'i (header boyu) eklenir (örnek `EthHeader.offset = 8`).
- Dikkat: ilk `add_filter` arayüzü "her şey geçer"den "sadece filtre geçer"e çevirir.

## Monitor (services/monitor)
- Yerel web sayfası (standart kütüphane). Canlı: Tools > Start (olay aboneliği). Offline: File > Import CSV.
- Akış anahtarı: (yön, sınıf, kanal, adres (PCI), signature); aynı sınıfın farklı 1553 node'ları ayrı akıştır.
- CSV (`CommLogger`) sütunları: host_time, uts_time, direction, channel, address, message, signature, length, data.

## Loglama
- Her modül standart `logging` ile kendi logger'ına yazar (`asl_testing.*`); hedefi test tarafı ayarlar.
- ERROR: UTS send/poll hatası, bozuk UTS öğesi, abone exception'ı, RX'te beklenmeyen hata (thread yine çalışır).
  WARNING: zaman aşımı, invalid, unknown, doğrulama hook'unun istisnası. INFO: open/close, listen, periyodik
  başlat/durdur, RX geri geldi. DEBUG: her mesaj.
- `Comm(..., logger=x)`: tüm parçalar `x`'e yazar. `CommLogger` (CSV) veri, `ErrorLog` ayrı dosya.

## Thread modeli
- 1 RxPoller, 1 TxScheduler, abone başına 1 thread. Mesaj başına thread yok.
- Gönderim tek kilit altında: pack (kopya), UTS isteği, sayaç, history, after_send.
- RxPoller tek bir paketteki ya da tek bir döngüdeki hatayı loglar ve devam eder.
- Periyodik gönderimde bir sonraki zaman `due + period` (kayma birikmez).
- ctypes nesneleri hash'lenemez: scheduler tablosu ve zaman aşımı kümesi `id(msg)` ile tutulur.

## CRC ve değişken boy
- CRC her mesajın son alanı (`ChecksumType`). Kablodaki paket = gövde + CRC.
- Değişken boylu mesaj: `_variable_size = True`; ctypes yapısı max boydur, gerçek boy length alanındadır.
  - RX: length en az "length alanının sonu + CRC boyu", en fazla max; paket ≥ length. CRC `raw[L-T:L]`'den okunur;
    decode gövdeyi başa, CRC'yi CRC alanına yazar, kullanılmayan kısım sıfırdır.
  - TX: mesaj `body_size()`'ı override eder; length, CRC ve gövde aynı kopyadan hesaplanır.

## Açık konular
Ayrıntılı ve güncel liste: `docs/KNOWN_ISSUES.md`. Özet:
- Gerçek UTS biçimleri: GET cevabı, timestamp birimi, CAN gövdesi, config/filtre gövdeleri; `HttpUtsClient` taslak.
- 1553: T/R biti ve mode code'ların PCI'a girip girmeyeceği; UTS'nin rolü (BC / RT / monitor) ve RX'in istekle mi
  geldiği; çerçeve çizelgesinin UTS'de mi olduğu. CAN FD, remote frame. CANopen (SDO/NMT) servis olarak eklenecek.
- Seri mod (RS422 / Camera Link) ve protokol config'lerinin `comm.open()` sırasında UTS'ye gönderilmesi (kanal config'i).
- Paketin sonundaki fazla byte'lar kabul ediliyor (K2, karar bekliyor).
- Özel alan tipleri projenin endian'ını takip etmiyor (K3).
- İki yönlü mesajda RX'in TX değerlerinin üzerine yazması (B14); periyodik gönderimde `after_send` yarışı (B12).
- Aynı adreste birden fazla header'lı kanalın header çakışması kontrol edilmiyor.
- UTS filtresi: arayüz başına; kısmi bit maskesi; okuma-ekleme-yazma tek işlem değil.
- `Counter8` 16 bitlik alanda; ICD ile kontrol edilmeli.
- Sonraki fazlar: segmentasyon (TP) katmanı, CAPL benzeri SimulationNode, hata enjeksiyonu (`msg.fault`).
