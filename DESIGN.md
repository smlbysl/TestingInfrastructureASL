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
  channel.py             Channel(protocol, interface)
  enumerations.py        ProtocolType, Direction (Flag), Endian
events/
  types.py               olaylar: MessageReceived/Sent, Invalid/UnknownReceived, RxTimeout/Restored, LinkError
  bus.py                 EventBus: abone başına kuyruk + thread, where= filtresi
comm/                    haberleşme katmanı
  uts.py                 UtsClient (soyut), HttpUtsClient (yer tutucu), FakeUtsClient
  transport.py           Transport: channel <-> UTS, send / poll, sadece byte
  dispatcher.py          lookup + decode + olay, unknown listesi
  clock.py               UtsClock: tahmini UTS "şimdi"si
  rx.py                  RxPoller thread'i + periyodik RX zaman aşımı
  tx.py                  TxScheduler: send (kilit) + tek thread'te periyodik gönderim
  comm.py                Comm: test tarafına açık tek sınıf
services/
  commlogger.py          CommLogger: mesajlaşma geçmişi (CSV)
  errorlog.py            ErrorLog: UTS hataları, RX zaman aşımı, abone hataları (ayrı dosya)
project/                 projeye özel (ICD): types, project (proje + aileler), messages
example.py               sahte UTS ile uçtan uca örnek
```

## Katmanlar
```
Test kodu        mesaj nesneleri + Comm (send, start/stop, on_receive, unknown)
Comm             katmanları kurar, open/close
TxScheduler      ne zaman gönderilir        RxPoller   ne zaman sorgulanır + zaman aşımı
                                            Dispatcher registry ile eşleme, decode, olay
EventBus         olayları abonelere dağıtır (CommLogger, ErrorLog, test dinleyicileri, ileride simülasyon/UI)
Transport        channel <-> protocol/interface, byte
UtsClient        HTTP (POST transfer, GET mesaj listesi); UTS'ye özgü her şey burada
```

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
- Alt sınıfın alanları checksum'ın arkasına düşüyor; CRC payload'ı kapsamıyor.
- `Counter8` 16 bitlik alanda tutuluyor; ICD ile kontrol edilmeli.
- Sonraki fazlar: sinyal geçmişi + UI köprüsü, CAPL benzeri SimulationNode (on_message, on_timer).
