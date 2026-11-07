# BaseMessageStructure - Tasarım Notları

Python ctypes ile Ethernet/RS422 haberleşen projeler için test altyapısı.
ICD'ye bağlı mesaj nesneleri oluşturulur; haberleşme UTS (HTTP servisi) üzerinden yapılır.
Ayrıntılı tasarım ve yol haritası: "UTS Haberleşme Katmanı – Tasarım ve Yol Haritası" belgesi.
Kod içindeki yorumlar İngilizce.

## Dosya yapısı
```
generic/                 mesaj katmanı (projeden bağımsız)
  basemessage.py         BaseMessageStructure: init, validate/decode, pack, callout, varsayılanlar
  fieldtypes.py          FieldType (+ on_init/on_send/on_receive), Length/Counter/Checksum/Ascii
  signature.py           Signature: alan listesinden offset+mask, tek ID
  registry.py            Registry: aile başına kayıtlar, lookup, yer değiştirme kuralı
  timing.py              Timing(period, tolerance)
  state.py               RxState (UTS zamanı, tazelik), TxState
  channel.py             Channel (EthernetChannel, Rs422Channel), ChannelSet, kanal kuralları
  framing.py             Splitter (akış -> paket), Envelope (paket etrafı), Framing
  enumerations.py        ProtocolType, Direction (Flag), Endian
events/
  types.py               olaylar: MessageReceived/Sent, Invalid/UnknownReceived, RxTimeout/Restored, LinkError,
                         hat seviyesi: WireReceived, WireSent
  bus.py                 EventBus: abone başına kuyruk + thread, where= filtresi
comm/                    haberleşme katmanı
  uts.py                 UtsClient (soyut), HttpUtsClient (yer tutucu), FakeUtsClient
  transport.py           Transport: envelope, adres başına sorgu, splitter, kanal tespiti
  dispatcher.py          lookup + decode + olay, unknown listesi
  clock.py               UtsClock: tahmini UTS "şimdi"si
  rx.py                  RxPoller thread'i + periyodik RX zaman aşımı
  tx.py                  TxScheduler: send (kilit) + tek thread'te periyodik gönderim
  comm.py                Comm: test tarafına açık tek sınıf
services/
  commlogger.py          CommLogger: mesajlaşma geçmişi (CSV)
  errorlog.py            ErrorLog: UTS hataları, RX zaman aşımı, abone hataları (ayrı dosya)
project/                 projeye özel (ICD): types, channels (MyChannels), framing (örnek EthHeader),
                         project (proje + aileler), messages
example.py               sahte UTS ile uçtan uca örnek
```

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

## Yeni paket kontrolü
- `msg.has_new()`: son çağrıdan bu yana gelen geçerli paket sayısı (0: yok); çağrı sıfırlar.
  `rx_state.count` (toplam) ile son kontrol edilen değer (`_seen`) karşılaştırılır; kilit gerekmez, paket kaçmaz.
- `comm.wait_new(msg, timeout)`: yeni paket gelene kadar bekler; gelen paket sayısını ya da zaman aşımında 0 döner.
  Bir isteği göndermeden önce `msg.has_new()` çağrılır ki önceki paket cevap sanılmasın.

## Olaylar
- Mesaj seviyesi (değişmedi): `MessageReceived`, `MessageSent`, `InvalidReceived`, `UnknownReceived`
  (`raw` = mesaj byte'ları, envelope çıkarılmış).
- Hat seviyesi: `WireReceived` (hattan gelen her paket, envelope dahil; mesaj eşleşmesinden önce) ve
  `WireSent` (hatta giden paket). Abonelik: `comm.subscribe(WireReceived, handler)`.
- Bir paket için önce hat seviyesi, sonra mesaj seviyesi olay yayınlanır.

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
- Sonraki fazlar: sinyal geçmişi + UI köprüsü, CAPL benzeri SimulationNode (on_message, on_timer).
