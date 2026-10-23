# BaseMessageStructure - Tasarım Notları

Python ctypes ile Ethernet/RS422 haberleşen projeler için test altyapısı.
ICD'ye bağlı mesaj nesneleri oluşturulur, altyapıya bu nesneler verilir.

## Dosya yapısı
```
generic/                 mesaj tanımlama katmanı (projeden bağımsız)
  basemessage.py         BaseMessageStructure, alan tipleri (Length/Counter/Checksum/Ascii)
  signature.py           Signature: alan listesinden offset+mask, tek ID
  registry.py            ProjectRegistry: all / dispatch / periodic_rx / periodic_tx
  state.py               RxState (tazelik), TxState (gönderim zamanı)
  channel.py             Channel(protocol, interface)
  enumerations.py        ProtocolType, Direction (Flag), Endian
comm/                    haberleşme katmanları
  transport.py           Transport (soyut) + LoopbackTransport (örnek/test)
  dispatcher.py          ham paket -> lookup -> decode
  monitor.py             periyodik RX tazelik kontrolü
  scheduler.py           periyodik TX gönderimi
project/projectbase.py   proje ve mesaj tanımları (ICD)
example.py               uçtan uca örnek
```

## Katmanlar
- **Transport**: sadece byte alır/verir. Mesajı, signature'ı, periyodu bilmez.
- **Dispatcher**: `ProjectX.lookup(channel, raw)` ile nesneyi bulur, `obj.decode(raw)` ile yazar.
  Eşleşmeyen paket `unknown`, validate'ten geçemeyen paket `invalid` listesine düşer.
- **Mesaj nesnesi**: alanlar + yön durumu (`rx_state` / `tx_state`). Tazeliği kendisi söyler.
- **Monitor**: `periodic_rx` listesini tarar, `period * tolerance` aşılanları raporlar.
- **Scheduler**: `periodic_tx` listesinden zamanı geleni `pack()` edip gönderir.

## Sınıf hiyerarşisi
`BaseMessageStructure -> ProjectX -> mesaj sınıfı`
- **Proje sınıfı** = BaseMessageStructure'dan doğrudan türeyen sınıf. Kendi registry'si olur.
  Signature, varsayılan protokol/interface, yön, periyot class attribute olarak burada.
- **Mesaj sınıfı**: `_fields_` ile byte formatı.
- **Nesne**: `channel`, `direction`, `rx_period`, `tx_period`, `rx_tolerance` keyword olarak verilebilir;
  verilmezse proje sınıfındaki varsayılan kullanılır. Aynı tanım farklı channel'larda farklı nesnelerle kullanılabilir.

## Signature
- Proje başına tek tanım: `Signature("alan1", "alan2", ...)`.
- `bind` alan listesinden offset ve mask çıkarır; endian mesaj sınıfından okunur. Miras alınan alanları da bulur.
- `bind` ilk nesnenin `__init__`'inde çalışır (`__init_subclass__`'ta ctypes layout hazır değil).
- İlk sınıfın sonucu referanstır; projedeki her yeni sınıf bir kez karşılaştırılır, uyuşmazsa
  ICD'ye aykırı tanım olarak `ValueError`.
- Kayıttan sonra signature alanlarına yazmak `AttributeError` verir (saklanan ID bozulmasın).

## Registry
- `BaseMessageStructure._registry[proje sınıfı] -> ProjectRegistry` (signature'sız projeler de kayıt tutar).
- `all`: tüm nesneler. `dispatch`: `(channel, signature_id) -> nesne`, sadece RX/çift yönlü.
- TX-only nesneler `dispatch`'e girmez. Aynı channel + imza ile ikinci RX nesnesi `ValueError`.
- `BaseMessageStructure.clear_registry()`: testler arası temizlik.

## RX / TX
- `decode(raw)`: `validate` (boy, length alanı, checksum) -> memmove -> `rx_state.on_receive()`;
  geçersizse nesne değişmez, `rx_state.on_error()`.
- `pack()`: counter++, checksum, `tx_state.on_send()`, byte'ları döner.

## Açık konular
- Alt sınıfın eklediği alanlar checksum alanının arkasına düşüyor; CRC bu alanları kapsamıyor.
  Checksum her zaman mesaj sonunda olacaksa yapı buna göre düzenlenmeli.
- Tolerans kuralı (1.5-2x mi, art arda N kaçırma mı) ICD'ye göre seçilecek; şu an `period * tolerance`.
- Gerçek transport (HTTP üzerinden service) yazılmadı; `Transport`'tan türetilecek.
