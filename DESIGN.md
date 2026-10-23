# BaseMessageStructure - Tasarım Notları

Python ctypes ile Ethernet/RS422 haberleşen projeler için test altyapısı.
ICD'ye bağlı mesaj nesneleri oluşturulur, altyapıya bu nesneler verilir.
Odak: BaseMessageStructure ve ilişkili yapılar. `comm/` altındakiler (transport, scheduler, monitor) şimdilik konsept.

## Dosya yapısı
```
generic/                 projeden bağımsız, her projede aynı
  basemessage.py         BaseMessageStructure: mesajın kendi işleri (init, validate/decode, pack)
  fieldtypes.py          FieldType, LengthType, CounterType, ChecksumType, AsciiType
  signature.py           Signature: alan listesinden offset+mask, tek ID
  registry.py            Registry: aile başına kayıtlar + lookup
  state.py               RxState (tazelik), TxState (gönderim zamanı)
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
Test kodu            mesaj nesnelerini kullanır (msg.comut[0], msg.pack())
Proje / Aile         tanımlar; ProjectX.lookup paketin ailesini bulur
Registry             aile başına kayıtlar
Mesaj nesnesi        alanlar, signature_id, decode/pack, rx/tx durumu
Scheduler / Monitor  periodic_tx gönderir / periodic_rx denetler
Dispatcher           transport'tan gelen paketi lookup + decode
Transport            sadece channel + bytes; alıcı fonksiyon referansı tutar
```
Transport hiçbir şeyi bilmez; kurulumda `transport.set_receiver(dispatcher.on_raw)` ile bağlanır.

## Sınıf hiyerarşisi
```
ctypes.Structure
 └ BaseMessageStructure                      ortak davranış
    └ ProjectBase(..., LittleEndianStructure) endian, header, varsayılanlar, _families
       ├ Family1   _signature -> _registry
       │  ├ request   _fields_
       │  └ comut     _fields_
       └ Family2   _signature -> _registry
          └ bambaşka  _fields_
nesne = comut(DEST, SRC, 0x20, channel=..., direction=..., rx_period=...)
```
- **Proje**: BaseMessageStructure'dan DOĞRUDAN türeyen sınıf. Endian ctypes tabanıyla seçilir
  (`LittleEndianStructure` / `BigEndianStructure`). `_families` listesini ve kendi registry'sini açar
  (signature'ı yoksa signature'sız mesajlar, örn. sadece TX, burada tutulur).
- **Aile**: kendi `_signature`'ını tanımlayan sınıf. Kendi `Registry`'sini açar, projenin `_families`'ine ekler.
  Bir projede birden fazla aile (farklı signature) olabilir.
- **Mesaj sınıfı**: sadece `_fields_` (payload).
- **Nesne**: `channel`, `direction`, `rx_period`, `tx_period`, `rx_tolerance` keyword olarak;
  verilmezse proje varsayılanı. Aynı tanım farklı channel'larda farklı nesnelerle kullanılabilir.

## Signature
- Aile başına tek tanım: `Signature("alan1", "alan2", ...)`.
- `bind` alan listesinden offset ve mask çıkarır; endian mesaj sınıfından okunur. Miras alınan alanları da bulur.
- `bind` ilk nesnenin `__init__`'inde bir kere çalışır (`__init_subclass__`'ta ctypes layout hazır değil).
- `compute(raw)` hem ham pakette hem `bytes(nesne)`'de aynı ID'yi verir.

## Registry (aile başına)
- `all`: tüm nesneler. `dispatch`: `(channel, signature_id) -> nesne`, sadece RX/çift yönlü.
- `channels`: ailenin RX aldığı channel'lar. `ProjectX.families(channel)` bununla filtreler.
- `periodic_rx` (monitor), `periodic_tx` (scheduler).
- TX-only nesneler `dispatch`'e girmez. Aynı channel + imza ile ikinci RX nesnesi `ValueError`.
- Mesaj nesnesi kuralları bilmez; sadece `self._registry.add(self)`.
- `ProjectX.clear_registry()`: projenin tüm ailelerini temizler (testler arası).

## RX / TX
- `decode(raw)`: `validate` (boy, length alanı, checksum) -> memmove -> `rx_state.on_receive()`;
  geçersizse nesne değişmez, `rx_state.on_error()`.
- `pack()`: counter++, checksum, `tx_state.on_send()`, byte'ları döner.

## Açık konular
- Alt sınıfın eklediği alanlar checksum alanının arkasına düşüyor; CRC bu alanları kapsamıyor.
  Checksum her zaman mesaj sonunda olacaksa yapı buna göre düzenlenmeli.
- Aynı channel'ı paylaşan ailelerde bir paket birden fazla ailenin signature'ıyla eşleşebilir;
  şu an `_families` sırasındaki ilk aile kazanır. ICD'de aileleri ayıran bir alan yoksa öncelik belirlenmeli.
- Tolerans kuralı (1.5-2x mi, art arda N kaçırma mı) ICD'ye göre seçilecek; şu an `period * tolerance`.
- Gerçek transport (HTTP üzerinden service) yazılmadı; `Transport`'tan türetilecek.
- `Counter8` 16 bit (`c_uint16`) alanda tutuluyor, değer 256'da sarıyor; ICD ile kontrol edilmeli.
