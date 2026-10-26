# BaseMessageStructure - Tasarım Notları

Python ctypes ile Ethernet/RS422 haberleşen projeler için test altyapısı.
ICD'ye bağlı mesaj nesneleri oluşturulur, altyapıya bu nesneler verilir.
Odak: BaseMessageStructure ve ilişkili yapılar. `comm/` altındakiler (transport, scheduler, monitor) şimdilik konsept.

## Dosya yapısı
```
generic/                 projeden bağımsız, her projede aynı
  basemessage.py         BaseMessageStructure: mesajın kendi işleri (init, validate/decode, pack, callout)
  fieldtypes.py          FieldType (+ on_init/on_send/on_receive hook'ları), Length/Counter/Checksum/Ascii
  signature.py           Signature: alan listesinden offset+mask, tek ID
  registry.py            Registry: aile başına kayıtlar + lookup
  timing.py              Timing(period, tolerance): sabit zamanlama ayarı
  state.py               RxState (tazelik), TxState (gönderim zamanı): değişen değerler
  channel.py             Channel(protocol, interface)
  enumerations.py        ProtocolType, Direction (Flag), Endian
comm/                    haberleşme katmanları (konsept)
  transport.py           Transport (soyut) + LoopbackTransport (örnek/test)
  dispatcher.py          ham paket -> lookup -> decode
  monitor.py             periyodik RX tazelik kontrolü
  scheduler.py           periyodik TX gönderimi
project/                 projeye özel (ICD)
  types.py               Length16, Counter8, CRC16, Ascii4 ...
  project.py             ProjectBase (proje) + Family1, Family2 (aileler)
  messages.py            mesaj sınıfları (sadece payload)
example.py               uçtan uca örnek
```

## Katmanlar
```
Test kodu            mesaj nesnelerini kullanır (msg.comut[0], msg.pack(), msg.on_receive(...))
Proje / Aile         tanımlar; ProjectX.lookup paketin ailesini bulur
Registry             aile başına kayıtlar
Mesaj nesnesi        alanlar, signature_id, decode/pack, rx/tx durumu, callout'lar
Scheduler / Monitor  periodic_tx gönderir / periodic_rx denetler
Dispatcher           transport'tan gelen paketi lookup + decode
Transport            sadece channel + bytes; alıcı fonksiyon referansı tutar
```
Transport hiçbir şeyi bilmez; kurulumda `transport.set_receiver(dispatcher.on_raw)` ile bağlanır.

## Sınıf hiyerarşisi
```
ctypes.Structure
 └ BaseMessageStructure                      ortak davranış
    └ ProjectBase(..., LittleEndianStructure) endian, header, _channel/_direction/_timing, _families
       ├ Family1   _signature -> _registry
       │  ├ request   _fields_
       │  └ comut     _fields_
       └ Family2   _signature -> _registry
          └ bambaşka  _fields_
nesne = comut(DEST, SRC, 0x20, channel=..., direction=..., rx=Timing(0.05))
```
- **Proje**: BaseMessageStructure'dan DOĞRUDAN türeyen sınıf. Endian ctypes tabanıyla seçilir
  (`LittleEndianStructure` / `BigEndianStructure`). `_families` listesini ve kendi registry'sini açar
  (signature'ı yoksa signature'sız mesajlar, örn. sadece TX, burada tutulur).
- **Aile**: kendi `_signature`'ını tanımlayan sınıf. Kendi `Registry`'sini açar, projenin `_families`'ine ekler.
- **Mesaj sınıfı**: sadece `_fields_` (payload).
- **Nesne**: `channel`, `direction`, `rx`, `tx` keyword olarak; verilmezse sınıf varsayılanı.

## İsimlendirme
- `_x_` sadece ctypes'a ait: `_fields_`, `_pack_`.
- Sınıf ayarları `_x`: `_signature`, `_channel`, `_direction`, `_timing`, `_order` (alan tiplerinde).
- Nesne bilgileri `_x` olarak saklanır (`_channel`, `_direction`, `_rx`, `_tx`, `_signature_id`);
  kullanıcıya property ile açılır (`channel`, `direction`, `rx_state`, `tx_state`, `signature_id`).
- Çerçeve kodu (generic, comm) her zaman alt çizgili bilgiyi kullanır. Böylece ICD'de `channel` ya da
  `direction` isimli bir alan olsa bile çakışmaz (o mesajda property'yi alan gölgeler, çerçeve etkilenmez).

## Timing
- `Timing(period=None, tolerance=2.0)`, frozen. `period is None` -> event, değilse periyodik (`is_periodic`).
- Ayrı "periyodik mi" bayrağı yok; çelişen durum oluşamaz.
- Ayar sabit ve paylaşılabilir (proje varsayılanı `_timing`); değişen değerler RxState/TxState'te.
- RX ve TX ayrı: çift yönlü mesajda `rx=Timing(0.1), tx=Timing(0.05)` gibi.

## Özel alanlar (FieldType hook'ları)
- `__init_subclass__` `_fields_` içindeki FieldType alanlarını `(_order, ad)` olarak `_special`'da toplar
  (miras alınanlar dahil). BaseMessage alan isimlerini bilmez, sadece hook'ları sırayla çağırır:
  - `on_init(msg)`: nesne oluşturulurken (LengthType uzunluğu, ChecksumType ilk CRC'yi yazar)
  - `on_send(msg)`: `pack()` sırasında (CounterType artar, ChecksumType hesaplar)
  - `on_receive(msg, raw) -> bool`: `validate()` sırasında (LengthType, ChecksumType kontrol eder)
- ChecksumType `_order = 100`: her zaman en son çalışır, diğer alanların yeni değerini kapsar.
- Yeni bir özel alan tipi eklemek BaseMessage'a dokunmayı gerektirmez.

## Kullanıcı callout'ları
- `msg.on_receive(fn)`: geçerli paket nesneye yazıldıktan sonra `fn(msg)`. Dekoratör olarak da kullanılır.
- `msg.on_send(fn)`: `pack()` içinde, alan hook'larından ÖNCE `fn(msg)`; yapılan değişiklikler checksum'a girer.

## Signature
- Aile başına tek tanım: `Signature("alan1", "alan2", ...)`.
- `bind` alan listesinden offset ve mask çıkarır; endian mesaj sınıfından okunur. Miras alınan alanları da bulur.
- `bind` ilk nesnenin `__init__`'inde bir kere çalışır (`__init_subclass__`'ta ctypes layout hazır değil).
- `compute(raw)` hem ham pakette hem `bytes(nesne)`'de aynı ID'yi verir.

## Registry (aile başına)
- `all`: tüm nesneler. `dispatch`: `(channel, signature_id) -> nesne`, sadece RX/çift yönlü.
- `channels`: ailenin RX aldığı channel'lar. `ProjectX.families(channel)` bununla filtreler.
- `periodic_rx` (monitor), `periodic_tx` (scheduler): `timing.is_periodic` olanlar.
- TX-only nesneler `dispatch`'e girmez. Aynı channel + imza ile ikinci RX nesnesi `ValueError`.
- `ProjectX.clear_registry()`: projenin tüm ailelerini temizler (testler arası).

## RX / TX akışı
- `decode(raw)`: `validate` (boy + özel alanların `on_receive`'i) -> memmove -> `rx_state.on_receive()`
  -> kullanıcı `on_receive` callout'ları. Geçersizse nesne değişmez, `rx_state.on_error()`.
- `pack()`: kullanıcı `on_send` callout'ları -> özel alanların `on_send`'i (counter, checksum)
  -> `tx_state.on_send()` -> byte'lar.

## Açık konular
- Alt sınıfın eklediği alanlar checksum alanının arkasına düşüyor; CRC bu alanları kapsamıyor.
  Checksum her zaman mesaj sonunda olacaksa yapı buna göre düzenlenmeli.
- Aynı channel'ı paylaşan ailelerde bir paket birden fazla ailenin signature'ıyla eşleşebilir;
  şu an `_families` sırasındaki ilk aile kazanır. ICD'de aileleri ayıran bir alan yoksa öncelik belirlenmeli.
- Tolerans kuralı (1.5-2x mi, art arda N kaçırma mı) ICD'ye göre seçilecek; şu an `period * tolerance`.
- Gerçek transport (HTTP üzerinden service) yazılmadı; `Transport`'tan türetilecek.
- `Counter8` 16 bit (`c_uint16`) alanda tutuluyor, değer 256'da sarıyor; ICD ile kontrol edilmeli.
- Callout'lar scheduler thread'inde çalışır; uzun süren bir callout gönderim zamanlamasını kaydırır.
