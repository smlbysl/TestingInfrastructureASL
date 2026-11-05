# BaseMessageStructure - Tasarım Notları

Python ctypes ile UTS (HTTP servisi) üzerinden Ethernet / RS422 haberleşen projeler için test altyapısı.
Test ortamından bağımsız: unittest, pytest ya da kendi script'inle aynı şekilde ayağa kalkar.
Kod içindeki yorumlar İngilizce.

## Kullanım
```python
comm = Comm.load("setups/fake.toml", ProjectBase, MyChannels)
with comm:                                  # open(): UTS yapılandırılır, thread'ler başlar
    comm.send(req)                          # tek seferlik
    comm.start(cmd) / comm.stop(cmd)        # periyodik
    comm.on_receive(status, handler)        # dinleyici, kendi thread'inde
    comm.clear(MyChannels.DIAG)             # UTS buffer temizleme
    comm.set_filter(MyChannels.DIAG, [[(0, 0x55)]])
    comm.configure(MyChannels.CONTROL, baud_rate=115200)
    comm.reset()                            # temel duruma dön (her testten sonra)
```
Testlerde: `project/testing.py` → `CommTestCase` (unittest ve pytest), `shared_comm()` (kendi altyapın).
Setup dosyası `SETUP` ortam değişkeninden seçilir (varsayılan `setups/fake.toml`).

## Dosya yapısı
```
generic/                 mesaj katmanı (projeden bağımsız)
  basemessage.py         BaseMessageStructure: init, validate/decode, pack, callout, varsayılanlar, restore
  fieldtypes.py          FieldType hook'ları, Length/Counter/Checksum/Ascii
  signature.py           Signature: alan listesinden offset+mask, tek ID
  registry.py            Registry: aile başına kayıtlar, lookup, yer değiştirme kuralı
  channel.py             Channel (mantıksal kanal: Link adı, envelope, ham kurallar), ChannelSet
  framing.py             Splitter (akış -> paket), Envelope (paket etrafı: on_send / on_receive)
  timing.py, state.py, enumerations.py
events/                  olay tipleri + EventBus (abone başına kuyruk + thread)
comm/                    haberleşme katmanı
  comm.py                Comm: tek giriş noktası, baseline / reset
  bootstrap.py           setup dosyasından Comm kurar (Comm.load)
  config.py              TOML setup dosyası
  logsetup.py            tek işlem logu (comm.log)
  link.py                Link: fiziksel UTS interface'i (EthernetLink, SerialLink), config_mode
  transport.py           kanal kuralları + envelope + Link üzerinden UTS
  dispatcher.py          lookup + decode + olay, unknown listesi
  rx.py                  RxPoller: Link'leri sorgular, zaman aşımı, buffer taşması
  tx.py                  TxScheduler: send (kilit), periyodik gönderim
  clock.py               UtsClock: tahmini UTS "şimdi"si
  uts/                   UTS'ye özgü her şey
    base.py              UtsClient arayüzü, UtsFrame, UtsError
    http.py              UtsHttp: istek -> (status_code, headers, body), statusInfo kontrolü
    api.py               UtsApi: REST uçlarının birebir karşılığı
    client.py            HttpUtsClient: Link/byte <-> JSON
    fake.py              FakeUtsClient: UTS olmadan geliştirme ve test
services/commlogger.py   mesajlaşma geçmişi (CSV)
project/                 projeye özel: types, channels, framing, project (proje + aileler), messages, testing
setups/                  düzeneğe özel: fake.toml, bench_a.toml
tests/                   unittest ve pytest ile çalışan testler
```

## Katmanlar
```
Test kodu        mesaj nesneleri + comm
Comm             kurar, açar/kapatır, baseline/reset, UTS işlevleri
TxScheduler      ne zaman gönderilir          RxPoller   ne zaman sorgulanır, zaman aşımı, taşma
                                               Dispatcher registry ile eşleme, decode, olay
EventBus         olayları abonelere dağıtır (CommLogger, test dinleyicileri, ileride simülasyon/UI)
Transport        kanal kuralları + envelope, Link splitter, kanal tespiti
UtsClient        HTTP (configs, messages, filters); sahte istemci aynı arayüzle
```

## Proje / setup ayrımı
| Seviye | Ne | Nerede |
|---|---|---|
| Proje | mesajlar, aileler, kanallar (`Channel("ETH1", envelope=...)`), framing | `project/` |
| Setup | Link'ler (bus, interface, UTS ayarları, config_mode), UTS adresi, loglama | `setups/*.toml` |

- Kanal, Link'i adıyla gösterir; `ChannelSet.bind` yüklemede eşler ve kontrol eder
  (Link var mı, aynı Link'te en fazla bir envelope'suz kanal). Aynı bus/interface iki Link'te olamaz.
- Birden fazla kanal aynı Link'i paylaşabilir. RX'te Link'in kanalları sırayla denenir: envelope'lular önce,
  envelope'suz en son. `Envelope.on_receive` paket kendisine ait değilse `None` döner.

## Framing ve ham kurallar
```
RX:  UTS GET -> link.splitter -> channel.envelope.on_receive -> channel.on_receive_raw kuralları
         -> Dispatcher (lookup, decode) -> msg.on_receive callout'ları -> olay
TX:  msg.on_send callout'ları -> msg.pack() -> channel.on_send_raw kuralları -> channel.envelope.on_send -> UTS POST
```
- Splitter Link'te (fiziksel akış), Envelope kanalda (paket). Varsayılanları bir şey yapmaz.
- Splitter setup dosyasından seçilir: `splitter = "project.framing:Rs422Splitter"`.
- Ham kural `None` dönerse paket düşürülür. RX kuralları RX thread'inde çalışır, kısa tutulmalı.

## UTS yapılandırması (config_mode)
- `auto`: setup ayarları `open()`'da UTS'ye yazılır, `GET` ile geri okunur.
- `manual`: UTS'deki ayarlar okunur, Link'e aktarılır; setup dosyasında yazılı ve farklı olan ayar uyarı olarak loglanır.
- `[uts] config_mode` varsayılandır, `[links.X] config_mode` ile Link bazında değişir.
- `deviceStatus.isOpen == false` ya da UTS hatası `open()`'ı durdurur (UtsError).
- `comm.configure(...)` her iki modda da çalışma sırasında UTS'ye yazar.

## Baseline ve reset
- `open()` sonunda `mark_baseline()` çağrılır; her testte geçerli olması gerekenler kurulduktan sonra tekrar çağrılır.
- `reset()`: baseline'dan sonra başlatılan periyodikleri durdurur, baseline periyodiklerini yeniden başlatır;
  sonradan eklenen dinleyici, callout ve ham kuralları kaldırır; alan değerlerini baseline'a döndürür
  (counter alanları korunur); RX/TX sayaçlarını ve unknown listesini sıfırlar; `clear_buffers=True` ile UTS buffer'larını boşaltır.
- Mesaj nesneleri ve altyapı servisleri (CommLogger) silinmez.

## Loglama
- Her modül `logging.getLogger(__name__)`; sınıflar isteğe bağlı `logger` parametresi alabilir (`UtsHttp`).
- Handler kök logger'a bağlı: yeni modüller ve dış kütüphaneler aynı dosyaya yazar. Seviyeler `[logging.levels]`'tan.
- Her çalıştırma `logs/<tarih-saat>/` klasörü açar:
  - `comm.log`: tüm katmanların işlem logu (UTS istekleri ve hataları, yapılandırma, zaman aşımları, taşmalar, geçersiz paketler)
  - `comm_history.csv`: gelen ve giden her paket (hattaki byte'lar, envelope dahil)

## Mesaj katmanı (özet)
- Hiyerarşi: BaseMessageStructure -> Proje -> Aile (`_signature`, kendi Registry'si) -> mesaj sınıfı -> nesne.
  Tek aileli projede `_signature` doğrudan projede tanımlanabilir.
- CRC her mesajın son alanı; değişken boylu mesaj `_variable_size` + `body_size()`.
- Aynı sınıf + kanal + signature + yön ile yeniden oluşturulan nesne eskisinin yerini alır.

## Açık konular
- UTS `GET /messages` öğesinin biçimi ve zaman damgası birimi (`comm/uts/client.py: _frame`).
- Ethernet IP / port ayarlarının UTS'de nasıl yapıldığı.
- Interface numaralarının 0'dan mı 1'den mi başladığı.
- Filtrede dış liste VEYA / iç liste VE varsayımı.
- Seri hatta `startOfHeader` ile UTS'nin paketleri kendisinin ayırıp ayırmadığı (ayırıyorsa Splitter gerekmez).
- `clear` şu an `GET /messages` ile buffer'ı boşaltarak yapılıyor; ayrı bir uç varsa oraya geçilir.
- `msg.on_receive` (RX thread'inde) ve `comm.on_receive` (kendi thread'inde) ikisi de duruyor.
- Aynı kanalı paylaşan ailelerde bir paket iki ailenin signature'ıyla eşleşebilir (ilk aile kazanır).
- Sonraki fazlar: simülasyon (CAPL benzeri on_message / on_timer), MDA benzeri ölçüm/analiz aracı.
