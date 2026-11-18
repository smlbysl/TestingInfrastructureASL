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
    endian.py                EndianMeta: endian="big" / "little" (mesaj ve özel tipler)
    signature.py             Signature: alan listesinden offset+mask, tek ID
    registry.py              Registry: aile başına kayıtlar, lookup, yer değiştirme kuralı
    timing.py                Timing(period, tolerance), Direction
    state.py                 RxState (UTS zamanı, yeni paket), TxState
  channel/                   2. Kanal: nereden gider
    channel.py               Channel (interface + protokol adı + framing), kanal tipleri, ChannelSet
    framing.py               Splitter, Envelope, Framing
  adapter/                   3. Adapter: baytlar cihaza nasıl taşınır
    base.py                  Adapter (send, receive; config / filtre isteğe bağlı), AdapterError, Received
  adapter/uts/               UTS'e ait her şey
    adapter.py               UtsAdapter: mesaj akışı (send, receive), config ve filtre (kanal ya da mesajla),
                             UTS istekleri (post, get, read_config, write_config, read_filter, write_filter)
    protocols.py             Protocol (path, timeout, encode, decode, simulate); Ethernet / RS422 / 1553 tanımları
    filters.py               filtre hesapları (mesaj -> hattaki byte konumu, değer)
    fake.py                  FakeUtsAdapter: UTS yerine bellekte (posted, inject)
  runtime/                   4. Çalışma zamanı: ne zaman ve nasıl taşınır
    transport.py             kanal başına: envelope, `UtsAdapter` (send / receive), splitter
    rx.py                    RxPoller: sorgu, WireReceived, zaman aşımı
    tx.py                    TxScheduler: send (kilit), periyodik gönderim, WireSent
    dispatcher.py            lookup + decode + olay, unknown listesi
    clock.py                 UtsClock: tahmini UTS "şimdi"si
  events/                    5. Olaylar
    types.py                 mesaj ve hat seviyesi olaylar
    bus.py                   EventBus: abone başına kuyruk + thread
  services/                  6. Olay aboneleri
    comm_logger.py           CommLogger: gönderilen ve alınan paketlerin CSV kaydı
    session_log.py           SessionLog: oturum klasörü (CSV + hata / olay / işaret), bkz. SESSION_LOG.md
    errors.py                ErrorLog: UTS hataları, RX zaman aşımı, abone hataları (ayrı dosya)
    monitor/                 MonitorService: mesaj değerlerini zamanla izleme sayfası (canlı / CSV)
projects/
  example_project/           PROJEYE ÖZEL (ICD)
    header.py                ProjectBase (header, varsayılan kanal) ve aileler
    types.py                 Length16, Counter8, CRC16 ...
    settings.py              ENDIAN (projenin bayt sırası)
    channels.py              MyChannels
    framing.py               örnek EthHeader
    messages.py              mesaj sınıfları
examples/                    python -m examples.example (depo kökünden)
docs/DESIGN.md
```

Bağımlılık yukarıdan aşağıya: `comm.py` → `services` / `runtime` → `events`, `adapter` → `message`, `channel`.
`projects/` sadece `message` ve `channel`'ı kullanır.

## Katmanlar
```
Test kodu        mesaj nesneleri + Comm (send, start/stop, on_receive, unknown)
Comm             katmanları kurar, open/close
TxScheduler      ne zaman gönderilir        RxPoller   ne zaman sorgulanır + zaman aşımı
                                            Dispatcher registry ile eşleme, decode, olay
EventBus         olayları abonelere dağıtır (CommLogger, ErrorLog, test dinleyicileri, ileride simülasyon/UI)
Transport        kanal başına: envelope, splitter; baytları adaptöre verir / alır
Adapter          çekirdeğin gördüğü sözleşme: send / receive (config, filtre isteğe bağlı)
  UtsAdapter     UTS'e ait her şey: protokol tanımını seçer, config ve filtre, UTS istekleri (post / get, read_ / write_)
    Protocol     protokol tanımı: baytlar <-> UTS isteği / öğesi (encode, decode), URL yolu
```

## Adaptör
- Çekirdek ile cihaza giden sistem arasındaki sınır `Adapter` (`adapter/base.py`): `send(kanal, bayt)`,
  `receive(kanal)`. Config ve filtre isteğe bağlı; olmayan adaptörde `AdapterError`. UTS yerine başka bir sistem
  gelirse yeni bir adaptör yazılır; mesaj, kanal, framing, RX/TX ve testler değişmez.
- UTS'e ait her şey tek sınıfta: `UtsAdapter` (`adapter/uts/adapter.py`). Üç bölüm: mesaj akışı (`send`, `receive`;
  Transport kullanır), config ve filtre (`get_config`, `set_config`, `get_filter`, `set_filter`, `clear_filter`,
  `add_filter(msg)`, `remove_filter(msg)`; test `comm.adapter` üzerinden kullanır), UTS istekleri (`post`, `get`,
  `read_config`, `write_config`, `read_filter`, `write_filter`; gerçek adaptörde yazılır). `get_` / `set_` kanal ya da
  mesaj alır; `read_` / `write_` UTS'e giden ham istektir (yol, interface).
- Gerçek UTS için `UtsAdapter`'ın alt sınıfı yazılır: `super().__init__()`, `post`, `get` (eldeki `ApiWrapper` ile),
  gerektiğinde `read_` / `write_`. `FakeUtsAdapter` aynı sınıftan türer, istekleri bellekte yapar.
- Önceki adlar: `UtsClient` + `UtsControl` + `FakeUtsClient` -> `UtsAdapter` + `FakeUtsAdapter`; `comm.control` ->
  `comm.adapter`; `UtsError` -> `AdapterError`; `uts/` -> `adapter/uts/`. `UtsClock` aynı (UTS saatini anlatıyor).

## Protokol tanımları (`UtsAdapter`)
- Kanal sadece protokolünün adını taşır (`Channel.protocol`: "ethernet", "rs422", "mil1553"; UTS yolları
  `ethernet`, `serials`, `mil1553`); UTS'e ait hiçbir şeyi
  import etmez. Tanımlar `UtsAdapter`'dadır (`adapter/uts/protocols.py`, `UtsAdapter.protocols`): yol, `encode`, `decode`,
  `simulate`. Ortak kod `Protocol` temel sınıfında bir kez; 1553 sadece 16 bitlik çeviriyi (`to_list`, `to_bytes`) ekler.
- `UtsAdapter.send(kanal, bayt)`: tanımı seçer, `encode`, `post(yol, interface, gövde)`, cevaptan gönderim zamanı
  (`sent_time`). `receive(kanal)`: `get`, cevabın `messages` öğelerine `decode`, `isBufferOverflow` → `Polled(received,
  overflow)`. Gerçek UTS için sadece `post` ve `get` yazılır, ikisi cevap gövdesini döndürür; `FakeUtsAdapter` aynı
  tanımları ve aynı cevap biçimini kullanır.
- UTS cevabı: `{"statusInfo": {status, code, message}, ...}`. POST'ta `timestamp` (µs), GET'te `messages` ve
  `isBufferOverflow`. 200 olmayan cevabı `UtsAdapter.answer(status, gövde)` `AdapterError(status, code)` yapar;
  mevcut modül JSON'u nasıl verirse versin gerçek adaptör `post` / `get` içinde bunu çağırır.
- Taşma: UTS tamponu ring olarak tutar, GET boşaltır, taşınca sadece bayrak verir (silme isteği yok). RX thread'i uyarı
  loglar, `RxOverflow(kanal)` yayınlar (ErrorLog yazar), paketleri işlemeye devam eder.
- Gönderim zamanı: `Transport.send` → `(tel, zaman)`, `MessageSent.timestamp` (CSV log'da `uts_time`).
- Ayarın yeri: 1553 kelime sırası mesaj yapısına bağlı, kanalda (`Mil1553Channel(byte_order=...)`); UTS zaman birimi
  UTS'e bağlı, adaptörde (`UtsAdapter(time_unit=...)`, varsayılan 1e-6: mikrosaniye).
- Protokol mesajı, signature'ı, envelope'u, splitter'ı ve zamanlamayı bilmez. Envelope TX'te `encode`'dan önce
  eklenir; splitter ve envelope RX'te `decode`'dan sonra çalışır (bugünkü gibi).
- İstek timeout'u: protokol tanımında (Ethernet ve 1553: 2 sn, RS422: 3 sn; UTS'in TX timeout'u + pay), ya da
  `UtsAdapter(timeout=...)` ile hepsi için tek değer. `send` / `receive` süreyi `post` / `get`'e verir; gerçek adaptör
  süre içinde cevap yoksa `AdapterError` fırlatır. İstek tekrar denenmez. RS422 süresi baud'dan hesaplanmıyor (sabit).
- Ethernet ve RS422'nin UTS biçimi bugün aynı (`{"message": [baytlar]}`) ama ayrı sınıflar:
  biri değişirse diğeri etkilenmez.
- MIL-STD-1553 (`Mil1553Protocol`, `Mil1553Channel`): UTS paketi `[rt, subnet, word_count, word, word, ...]` listesi
  olarak taşır, ör. `[30, 1, 3, 0x0001, 0x3344, 0x1122]`. `rt`, `subnet`, `word_count` mesajın ilk alanlarıdır
  (projede `c_uint16`); protokol sadece mesaj baytlarını 16 bitlik değer listesine çevirir ve geri. Değerler
  kontrol edilmez. Tanıma bugünkü signature ile: `Signature("rt", "subnet")`.
  Her alan 16 bitlik sınırda başlamalı ve çift bayt olmalı; değilse bir kelime iki alanın parçasını taşır (kontrol yok).
  Kanalın `byte_order`'ı mesaj yapısının endian'ıyla aynı olmalı: little + "little" → 32 bit alanın düşük kelimesi önce,
  big + "big" → yüksek kelime önce; uyuşmazsa her değerin baytları ters gider (`30` → `7680`).
- Açık: Ethernet ve 1553 cevaplarının seri port ile aynı biçimde olduğu (belgelenmiş olan seri port).

## Kanal ve framing
- `Channel`: bir interface = interface numarası + protokol adı + `Framing`
  (alt sınıflar: `EthernetChannel`, `Rs422Channel`, `Mil1553Channel`; protokol adını belirler, 1553 `byte_order` ekler).
  IP, port, baud gibi fiziksel ayarlar kanalda yok. Eşitlik kimliğe göre: her kanal bir kez tanımlanır.
- `Framing(splitter, envelope)`, ikisi de isteğe bağlı; varsayılanları bir şey yapmaz.
  - Splitter: akış seviyesi; UTS'ten geleni paketlere böler.
  - Envelope: paket seviyesi; `on_send` ekler, `on_receive` çıkarır, kabul etmezse `None` (paket bilinmeyen olur).
- Proje kanallarını `ChannelSet` ile tanımlar (`project/channels.py`): isimleri verir, sınıf tanımlanırken bir
  interface'in iki kez kullanılmadığını kontrol eder. `Comm`'a verilmez.
- Kanal mesaja sınıf varsayılanı olarak verilir (`_channel = MyChannels.CONTROL`); nesne oluştururken verilmez.
- Bir interface'in tek kanalı var; gelen paketin kanalı her zaman bellidir. Envelope'u kabul etmeyen paket o kanalda
  unknown olur.
- Sorgulanan kanallar: RX mesajı kayıtlı kanallar ve `comm.listen(kanal)` ile eklenenler; her kanal kendi RX
  thread'inde. Kanal içi paket sırası korunur; farklı kanalların olayları arasında sıra yok.
```
TX:  msg.pack() -> envelope.on_send -> adapter.send(kanal) [protocol.encode -> post(path, interface, timeout) -> sent_time]
RX:  adapter.receive(kanal) [get(path, interface, timeout) -> items -> protocol.decode, overflow] -> splitter -> envelope.on_receive -> Dispatcher
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

## UTS yönetimi (comm.adapter)
- Mesaj akışından ayrı, dikine bir yol: test -> `comm.adapter` (`UtsAdapter`: `get_config`, `add_filter`, ...) ->
  UTS istekleri (`read_config`, `write_filter`, ...). RX/TX thread'leri ve
  olaylar kullanılmaz; çağrı senkron, sonucu döner ya da istisna fırlatır (`AdapterError`). Her çağrı INFO loglanır.
- Hedef bir mesaj nesnesi ya da kanal; mesaj kendi kanalını verir. Kanalın protokol tanımının yolu (adaptörden) +
  interface'i UTS arayüzünü seçer.
- `get_config` / `set_config(**ayarlar)`, `get_filter -> (kind, groups)`, `set_filter(groups, kind)`, `clear_filter`.
- `add_filter(msg)` / `remove_filter(msg)`: filtreyi okur, mesajın signature byte'larını ekler/çıkarır, geri yazar.
  Konumlar hattaki konumlardır: kanal envelope'unun `offset`'i (mesajın önündeki byte sayısı) eklenir
  (`Envelope.offset`, varsayılan 0; örnek `EthHeader.offset = 8`).
- UTS'in config ve filtre istekleri (`read_config`, `write_config`, `read_filter`, `write_filter`) soyut değil
  (varsayılan `NotImplementedError`); mesaj akışı sadece `post` / `get` ile çalışır. FakeUtsAdapter bunları saklar,
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
- RX: kanal başına 1 thread (`Rx-<kanal>`: yokla, `WireReceived`, dispatch, `poll_interval` bekle) ve 1 denetçi
  (`RxWatchdog`: RX mesajı olan ya da `listen` edilen kanalın thread'ini başlatır, RX zaman aşımlarını kontrol eder).
  Cevap vermeyen bir kanal diğerlerini ve zaman aşımı kontrolünü bekletmez; artık gerekmeyen kanalın thread'i biter.
  `UtsClock` bütün RX thread'lerinden güncellenir, kendi kilidi var. `comm.close()` cevap bekleyen bir GET'i en fazla
  timeout kadar bekler.
- TX: periyodik mesajı olan kanal başına 1 thread (`Tx-<kanal>`), kanalın ilk `comm.start(msg)`'inde açılır; her
  kanalın kendi tablosu ve uyandırma olayı var. POST'u takılan bir kanal diğerlerinin periyodik gönderimini durdurmaz.
  Kanal kaydını (tablo, thread) küçük bir iç kilit korur: aynı kanal için iki thread açılmaz; gönderimde alınmaz.
  `comm.close()` cevap bekleyen bir POST'u en fazla timeout kadar bekler. Abone başına 1 thread. Mesaj başına thread yok.
- Gönderim mesajın kilidi (`RLock`) altında: kancalar, counter, checksum, byte, UTS isteği, `after_send`. Aynı mesajın
  iki gönderimi (test ve periyodik) birbirini bekler; farklı mesajlar beklemez.
- `UtsAdapter` aynı interface'e bir anda tek POST gönderir (`(yol, interface)` başına kilit, sadece POST çevresinde);
  farklı interface'ler birbirini beklemez. GET kilit almaz. Kilit sırası: mesaj -> interface.
- `decode` yeni durumu ayrı tamponda hazırlayıp nesneye tek kopyayla yazar: tek alan okuması eski ya da yeni
  paketi görür, yarım değer görmez (B1). Birden fazla alan için `msg.snapshot()`.
- `pack` özel alanları (length, counter, CRC) nesnenin bir kopyasında hesaplar ve baytları o kopyadan üretir;
  nesneye sadece hook'un değiştirdiği özel alanlar geri yazılır (B9–B11).
- Bu koruma GIL'e dayanır (B13); free-threaded Python'da geçerli değildir.
- Periyodik gönderimde bir sonraki zaman `due + period` (kayma birikmez).
- ctypes nesneleri hash'lenemez: scheduler tablosu ve zaman aşımı kümesi `id(msg)` ile tutulur.

## Mesaj katmanı (özet)
- Hiyerarşi: BaseMessageStructure -> Proje -> Aile (`_signature`, kendi Registry'si) -> mesaj sınıfı -> nesne.
- Bayt sırası (`message/endian.py`): `BaseMessageStructure` ve `FieldType`'ın metaclass'ı `EndianMeta`.
  `endian="big"` verilen sınıfa `BigEndianStructure` tabanını ekler ve uygun metaclass'ı seçer (big metaclass
  little olandan türediği için çakışma olmaz, ikinci kök sınıf gerekmez). Varsayılan little; alt sınıflar
  tabanlarının sırasını alır. Değer projede tek yerde (`settings.py: ENDIAN`), proje sınıfı ve proje özel tipleri
  `endian=ENDIAN` ile alır. ctypes iç içe `Structure`'ı çevirmediği için mesaj, sırası farklı bir özel tipi
  tanımlanırken `TypeError` ile reddeder (K3). Python 3.13 ve 3.14'te denendi.
- Yerleşim: `BaseMessageStructure` ve `FieldType`'ta `_pack_ = 1` ve `_layout_ = "ms"`. `_pack_` 3.14'te sadece MSVC
  kurallarıyla geçerli (`gcc-sysv` ile `ValueError`); açıkça yazılmazsa Windows dışında uyarı verir, 3.19'da hata
  olacak. 3.13 `_layout_`'u yok sayar. Fark yalnız karışık tipli bit alanlarında (Linux'ta 3.13 ile 3.14 farklı);
  bit grubu tek tiple yazılır.
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
- UTS GET JSON biçimi, data kodlaması, timestamp birimi -> sadece `adapter/uts/` değişir.
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
- Periyodik gönderimde `after_send` yarışı (B12): `with msg.locked_update():` ile çözüldü. `locked_update()` mesajın
  kilidini döndürür (ek API yok; `update(...)` fonksiyonu, yol önbelleği ve erteleme eklenmedi: blok kısa tutulur).
  Düz yazmada test thread'i biti pack ile after_send arasında yazarsa sıfırlama bu değeri siler.
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

## Tasarım 2: UTS sürücü katmanı (tasarım aşamasında, uygulanmadı)

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

## Tasarım 3: kanal başına thread ve kilitler (tasarım aşamasında, uygulanmadı)

Amaç: cevap vermeyen ya da yavaş bir interface diğerlerini bekletmesin. Kanal ile interface bire bir eşleşir;
"kanal başına" ile "interface başına" aynı anlamdadır.

**Thread'ler.**

| Thread | Sayı | Görevi | Ne zaman açılır |
|---|---|---|---|
| `Rx-<kanal>` | Dinlenen kanal başına 1 | GET → decode → dispatch → `poll_interval` bekle | Denetçi, kanalda RX mesajı görünce ya da `listen` edilince |
| `RxWatchdog` | 1 | Yeni kanalların RX thread'ini başlatır; RX zaman aşımlarını kontrol eder | `comm.open()` |
| `Tx-<kanal>` | Periyodik mesajı olan kanal başına 1 | O kanalın periyodik mesajları (kendi tablosu, kendi uyandırma olayı) | O kanalda ilk `comm.start(msg)` |
| Test thread'i | — | `comm.send()` | — |

Zaman aşımı kontrolü tek bir denetçide: kanal thread'i isteğinde takılıyken kendi mesajlarını kontrol edemez.
Yoklama sabit aralıkla (`poll_interval`); denetçi de aynı aralıkla döner.

**Kilitler: her biri koruduğu şeye ait, aynı işi yapan iki kilit yok.**

| Kilit | Sahibi | Kapsadığı iş |
|---|---|---|
| Mesaj kilidi (`RLock`) | Her mesaj nesnesi | Paketleme (kancalar, sayaç, CRC) → envelope → istek → `after_send` |
| Interface kilidi | `UtsClient` (`(yol, interface)` başına) | Yalnızca POST (UTS'nin ezme kuralı) |
| Yaprak kilitler | `UtsClock`, `FakeUtsClient` tamponu, geçmiş, olay yolu | Tek bir veri yapısı; içinde başka kilit alınmaz |

- Sıra: mesaj → interface → yaprak. Ters sırada alınan kilit yok, kilitlenme yok.
- Kanal kilidi yok. Mesaj tutarlılığını mesaj kilidi, ezmeyi interface kilidi sağlar; kanal kilidi bunların ikisini
  birden, daha kaba yapan bir kilit olurdu (aynı kanaldaki iki mesaj birbirinin kancasını beklerdi). Bir interface'in
  tek kanalı olduğu için kanal kilidi interface kilidiyle aynı kapsamdadır.
- Yalnızca interface kilidi yetmez: paketleme ve `after_send` kilidin dışında kalır; aynı mesajın iki gönderimi
  aynı sayacı alabilir, paketler ters sırada gidebilir, `after_send` başka thread'in isteğini silebilir (B12).
- RX'te mesaj kilidi yok: bir mesaja sadece kendi kanalının RX thread'i yazar (tek kopyayla). GET'i de sadece o
  thread atar; kilit gerekmez.
- `update()` ve kilitli periyodik mesajın ertelenmesi (Tasarım 1) sonra eklenir; aynı mesaj kilidini kullanır.

**Envelope ve kilit (tasarım ihtiyacı).** Envelope paketi değiştirmez; verilen baytlardan yeni bayt üretir. Durum
tutmayan envelope'u (sabit başlık, pakete göre hesaplanan uzunluk ya da başlık CRC'si; bugünkü `EthHeader`) aynı
kanaldaki iki mesaj aynı anda çağırabilir, kilit gerekmez. Kanal genelinde değişen bir değer tutan envelope farklıdır:

- Örnek: her pakette bir artan sıra numarası yazan başlık (`self.seq += 1`). Kanal kilidi olmadığı için aynı
  kanaldaki iki mesaj (test thread'inden `comm.send` ve periyodik TX) `on_send`'i aynı anda çağırabilir; ikisi de
  aynı değeri okuyup aynı numarayla gönderebilir. Mesaj kilidi bunu önlemez (iki mesajın kilidi ayrı).
- Numara tekrar etmesin yeterliyse: kilit envelope'un içinde (`on_send` içinde oku-artır-yaz). Altyapıda değişiklik yok.
- Numara gönderim sırasıyla kesin artmalıysa: numaranın verilmesi ile POST aynı kilit altında olmalı; envelope içi kilit
  yetmez (6'yı alan, 7'yi alandan sonra POST edebilir). Bu durumda o kanalın gönderimleri sıraya girmeli.
  Öneri: `Envelope.ordered = True` işareti; TX katmanı böyle bir envelope'un kanalında envelope + `client.send`'i
  kanal başına bir kilit altında yapar. Sıra: mesaj → kanal (sadece `ordered`) → interface.
- RX'te durum tutan envelope ya da splitter (son sıra numarası kontrolü, yarım paket tamponu) kilit gerektirmez:
  bir kanalı sadece kendi RX thread'i okur.
- Bugünkü projede durum tutan envelope yok; bu ihtiyaç böyle bir cihaz gelince ele alınır.

Bu kararın etkilediği yerler:

| Yer | Etki |
|---|---|
| `channel/framing.py` (`Envelope`) | Kural açıklamaya yazılır: varsayılan durumsuz; durum tutan envelope kilidini kendisi taşır. `ordered` işareti gerekirse buraya eklenir (varsayılan `False`). Bugün kod değişmez. |
| `runtime/tx.py` | Kanal kilidi yok; envelope aynı kanalda paralel çağrılabilir. `ordered` gelirse: o kanalda envelope + `client.send` için kanal başına kilit (~6 satır). |
| `uts/client.py` | Etkilenmez; interface kilidi en içte kalır. |
| RX (`runtime/rx.py`, `transport.poll`) | Etkilenmez; kanal başına tek thread. |
| Mesaj kilidi (Tasarım 1) | Etkilenmez; kancalar sadece mesaj kilidi altında çalışır. |
| Testler | Durum tutan envelope eklenirse: aynı kanaldan paralel gönderimde numara tekrar etmez; `ordered` ise numaralar gönderim sırasıyla artar. |
| Belgeler | `USAGE.md` framing bölümüne kural. |

**Paylaşılan yapılar.** `UtsClock` bütün RX thread'lerinden güncellenir, denetçiden okunur: kilit gerekir.
Dispatcher, registry, `comm.unknown` bugün de test thread'iyle paylaşılıyor; tek adımlık işlemler (GIL). Zaman aşımı
durumunu sadece denetçi yazar. Kanalın periyodik tablosunu test thread'i değiştirir, TX thread'i kopyasında döner.

**Ön koşul: istek timeout'u.** Kanal başına thread ile takılan bir istek diğer kanalları bekletmez, ama
`comm.close()` o thread'i beklerken takılır. Client'a istek timeout'u bu yapıdan önce eklenir.

**Değişen davranış.** Takılan ya da yavaş bir interface diğerlerinin RX'ini, TX'ini ve zaman aşımı kontrolünü
bekletmez. TX kapasitesi (~230/s) interface başına olur. Farklı kanalların olayları arasındaki sıra kesin değildir;
kanal içi sıra korunur.

**Etkilenen dosyalar (thread ve kilit yapısı).**

| Dosya | Değişiklik | Adım | Tahmini |
|---|---|---|---|
| `uts/client.py` | İstek timeout'u (client ya da protokol tanımı başına süre; gerçek client `post` / `get` içinde kullanır). `send` içinde `(yol, interface)` başına kilit, sadece `post` çevresinde. | 1, 2 | ~15 satır |
| `uts/fake.py`, `uts/http.py` | Timeout parametresini temel sınıfa geçirir; kilit temel sınıftan gelir. | 1 | ~3 satır |
| `runtime/clock.py` | `UtsClock` kilidi (bütün RX thread'leri günceller, denetçi okur). | 3 | ~5 satır |
| `runtime/rx.py` | Tek döngü yerine: `poll_channel(kanal)` (yokla, olay, dispatch), kanal başına `Rx-<kanal>` thread'i, `RxWatchdog` (yeni kanalın thread'ini başlatır, zaman aşımı kontrolü). Gerekmeyen kanalın thread'i biter. `poll_once()` testler için kalır (bütün kanallar + zaman aşımı, çağıran thread'de). | 3 | ~+40 satır |
| `runtime/tx.py` | Genel `_send_lock` kalkar; `send` mesaj kilidi altında (pack → envelope → `client.send` → `after_send`). Tek tablo ve thread yerine kanal başına tablo, uyandırma olayı ve `Tx-<kanal>` thread'i (ilk `start(msg)`'de açılır). `tick` kanal başına. | 4 | ~+40 satır |
| `message/base.py` | `__init__`'te `self._lock = threading.RLock()`. `_pack`'in kopyası kilidi de taşır; kancalar mesaj kilidi altında çalışır. | 4 | ~3 satır |
| `comm.py` | `open` / `close` aynı çağrılar; `close` cevap bekleyen isteği en fazla timeout kadar bekler (açıklama). | 3, 4 | ~2 satır |
| `runtime/dispatcher.py`, `message/registry.py` | Kod değişmez. Birden fazla RX thread'inden çağrılır; işlemler tek adım (GIL), uygularken tek tek kontrol. | 3 | — |
| `events/*`, `services/*`, `channel/*` | Değişmez. | — | — |
| `examples/` | Değişmez (`comm.tx.is_running` kalır). | — | — |
| Testler | Yeni: takılan kanal diğerinin RX'ini ve zaman aşımını bekletmez; takılan POST diğer kanalın periyodik TX'ini durdurmaz; `open`'dan sonra tanımlanan kanal dinlenir; `close` bütün thread'leri durdurur; aynı interface'e iki POST üst üste gitmez, farklı interface'ler beklemez; timeout. Mevcut testler değişmez. | 1–4 | ~200 satır |
| Belgeler | `DESIGN.md` (Thread modeli), `USAGE.md`, `TEST_API.md`, `manual.html` (`open` açıklaması), `KNOWN_ISSUES.md` (RX sırası notu), mimari sayfa (thread kutuları, TX/RX akış notları). | 3, 4 | kısa |

**Sıra (her biri ayrı onay ve commit).**
1. Client'ta istek timeout'u. **Uygulandı.**
2. Client'ta interface kilidi. **Uygulandı** (mesaj kilidiyle birlikte, thread'lerden önce).
3. RX: kanal başına thread, denetçi, `UtsClock` kilidi. **Uygulandı.**
4. TX: kanal başına thread ve mesaj kilidi. **Uygulandı.** Kanal kaydı için iç kilit (denetçiye bırakmak yerine).
5. Tasarım 1'in sade hali: `with msg.locked_update():` (mesaj kilidini döndürür). **Uygulandı.** `update(...)`,
   yol önbelleği ve erteleme eklenmedi.


## Tasarım 4: 1553 RX etkinleştirme (tasarım aşamasında, uygulanmadı)

**İhtiyaç:** 1553'te periyodik olmayan bir RX mesajının gelmesi için UTS'e önce bir TX (node / rt, subnet, word count)
gönderilmesi gerekiyor. Bu TX bir kez yapılınca o mesaj etkinleşiyor; sonra GET ile alınıyor.

**Kanal parametresi değil:** bir node'un birden fazla subnet'i olabilir; kanalda tanımlanırsa her subnet ayrı kanal olur.
Gerekli bilgi RX mesajının tanımında zaten var:

```python
class rt30_status(Bus1553):
    _defaults = {"rt": 30, "subnet": 1, "wordCount": 3}      # etkinleştirme: [30, 1, 3]
```

**Önerilen yapı** (1553'e özgü, protokol + adaptör katmanında; runtime sadece tetikler):

1. `Mil1553Protocol.enable(channel, msg) -> body | None`: mesajdan `rt`, `subnet`, `wordCount` okur,
   `{"message": [rt, subnet, wordCount]}` döner. Ethernet / RS422 `None` döner.
2. `Adapter.enable(channel, msg)`: base'de boş. `UtsAdapter`'da gövdeyi protokolden alır; (interface, rt, subnet)
   daha önce etkinleştirildiyse bir şey yapmaz, değilse interface kilidi altında POST eder ve anahtarı kilitli bir
   sette tutar. `FakeUtsAdapter` etkinleştirmeleri kaydeder (testler görsün).
3. Tetikleme: RX thread'i, `poll_channel` içinde GET'ten önce kanalın kayıtlı RX mesajlarını `adapter.enable`'a verir.
   Etkinleşmiş olanlar için sadece set kontrolü yapılır. Yeni tanımlanan RX mesajı bir sonraki turda etkinleşir.
   Hata: bugünkü yol (`LinkError` + log); anahtar kaydedilmediği için sonraki turda tekrar denenir.
4. Elle kullanım: `comm.adapter.enable(msg)`; UTS yeniden başladıysa `adapter.reset_enabled()`.

Tahmini değişiklik: `protocols.py` ~8, `adapter/base.py` ~3, `uts/adapter.py` ~15, `fake.py` ~3, `rx.py` ~5 satır,
artı testler ve dokümanlar.

**Netleşmesi gerekenler (UTS'ten öğrenilecek):**
1. Etkinleştirme POST'unun gövdesi: sadece `[rt, subnet, wordCount]` mı, normal TX'ten (BC→RT veri) nasıl ayrılıyor
   (ayrı alan / path)?
2. Ne kadar geçerli: UTS yeniden başlayınca ya da config / filtre değişince tekrar gerekiyor mu? Gerekiyorsa adaptör
   o anda setini temizler.
3. Periyodik 1553 RX mesajlarında gerekiyor mu, yoksa sadece periyodik olmayanlarda mı?
4. Anahtar (rt, subnet) mi, word count da dahil mi?

## Tasarım 5: `wait_new` / `wait_sent` için Condition (tasarım aşamasında, uygulanmadı)

**Bugün:** `comm.wait_new(msg)` ve `comm.wait_sent(msg)` sayaca yoklamayla bakıyor (`comm.py`, `_wait`):

```python
while True:
    new = check()                      # msg.has_new() / msg.has_sent()
    if new or time.monotonic() >= deadline:
        return new
    time.sleep(interval)               # 5 ms
```

RX / TX thread'i sayacı (`RxState.count`, `TxState.count`, `message/state.py`) kimseye haber vermeden artırıyor.
Sonuç: paket geldikten sonra en fazla 5 ms geç fark ediliyor; paket gelmezse 1 s beklemede ~200 boş uyanma oluyor.

**Öneri:** `RxState` ve `TxState` birer `threading.Condition` taşır; sayaç artınca bekleyenler uyandırılır.

```python
_cond: threading.Condition = field(default_factory=threading.Condition)

def on_receive(self, timestamp=None):
    with self._cond:
        ...
        self.count += 1
        self._cond.notify_all()

def wait_new(self, timeout: float) -> int:
    with self._cond:
        self._cond.wait_for(lambda: self.count > self._seen, timeout)
        return self.check_new()
```

`TxState` aynı şekilde (`on_send` içinde `notify_all`, `wait_sent(timeout)`).

- Bekleyen paket gelir gelmez uyanır; gecikme ve boş döngü yok. `_wait` ve `interval` kalkar.
- `Event` değil `Condition`: sayı önemli ve birden fazla thread aynı mesajı bekleyebilir.
- Bedeli: her pakette / gönderimde kısa bir kilit (bugün sayaç kilitsiz, tek yazan RX / TX thread'i).
- Değişiklik: `state.py` ~15 satır, `comm.py`'den `_wait` / `interval` kalkar, testlerde `interval` kullanan yerler.
- Birlikte düşünülecek: bekleme fonksiyonlarını mesaja taşımak (`msg.wait_new()`, `msg.wait_sent()`,
  `msg.wait_for()`), geçmişte arama (`rx_history.find` / `select`, zaman aralığı).
- Benzer yapı bugün TX thread'inde var: `ChannelTx.wake` (`Event`) tablo değişince thread'i uyandırıyor.

## Tasarım 6: Ağ / ICD tanımından test sınıflarını üretmek (mimari not, uygulanmadı)

**Amaç:** projenin bütün ağını (düğümler, iç / dış arayüzler, bus'lar, mesajlar, alanlar) tek kaynakta tanımlamak;
test altyapısının sınıflarını bu kaynaktan üretmek ve tanımı baştan doğrulamak.

**Katmanlar** (1–9 sistemi, 10 test tezgâhını tanımlar; ayrı tutulur):

| # | Katman | İçerik |
|---|---|---|
| 1 | Meta | ICD adı, sürüm, tarih, referanslar |
| 2 | Tipler | uint/int/float/ascii, enum, bit alanı, dizi, birim, ölçek, aralık |
| 3 | Özel alanlar | Length (kapsam), Counter (bit), Checksum (algoritma, polinom, init, kapsam) |
| 4 | Topoloji | Düğümler, bus'lar, bağlantılar, iç / dış |
| 5 | Bus parametreleri | Ethernet IP/port/UDP-TCP, RS422 baud/parity, CAN bitrate/ID, 1553 BC/RT |
| 6 | Çerçeve | Header / footer / envelope, endian, hizalama |
| 7 | Mesajlar | Kimlik (signature), üreten / tüketen, bus, boy, alanlar ve bit konumları, varsayılanlar |
| 8 | Zamanlama | Periyodik, olay, istek-cevap |
| 9 | İşlemler | İstek → ack eşleşmesi, timeout, tekrar, NAK, parçalı aktarım |
| 10 | Tezgâh | DUT, simüle edilen düğümler, UTS protokol / interface / config |

- Mesajın yönü (`Direction`) tanımda yok; tezgâhta "simüle edilen düğüm üretiyorsa TX" kuralıyla türetilir.
- Kaynak dosyalar YAML (yorumlu, gözden geçirilebilir) + JSON Schema doğrulaması; CAN için DBC içe aktarma
  (`cantools`). Excel ICD varsa Excel → YAML dönüştürücü.
- Dosya düzeni: `icd/<proje>/{network,types,framing,transactions}.yaml`, `messages/*.yaml`, `can/*.dbc`;
  `bench/<lab>.yaml`. Atıflar adla.
- Bağlantı: kod üretimi (önerilen; IDE desteği, diff) → `settings.py` (ENDIAN), `types.py`, `header.py`
  (ProjectBase, aileler), `messages.py`, `channels.py` + UTS config (tezgâhtan), `operations.py` (işlemlerden).
  Projeye özel davranış (özel CRC, hook) elle yazılan ayrı dosyada; üretilen dosyalar elle değişmez.
- Doğrulama: şema, atıflar, alan çakışması, bus boy sınırı (CAN 8/64 B, 1553 32 kelime), 1553 16 bit hizası,
  karışık tipli bit grubu, aynı bus'ta tekrar eden kimlik, bus doluluğu, tezgâhta eksik bağlantı.
- Açık: ICD'lerin bugünkü biçimi (Excel / Word), CAN ve DBC var mı, bus türleri (ARINC 429?), sinyal başına
  endian gerekiyor mu, kod üretimi mi çalışırken yükleme mi, kaynağın sahibi kim.
- Kaynak, ortak tek dosya veri tabanı olursa (araçtan bağımsız) bu üretim onun üzerinden yapılır.
