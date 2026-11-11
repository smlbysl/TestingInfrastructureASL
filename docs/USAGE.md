# Kullanım kılavuzu

Yazar: İsmail Baysal

Bu belge nasıl yazılacağını gösterir. Her arayüzün ayrıntılı listesi, test için anlamlı olup olmadığı ve açık tasarım soruları için `docs/TEST_API.md`'ye bak.

Test yazarken bütün isimler tek bir yerden gelir:

```python
from asl_testing import Comm, FakeUtsClient, Timing, Direction, MessageReceived
```

Kütüphanenin iç modüllerine (`asl_testing.runtime`, `asl_testing.message.state` ...) test kodunda gerek yoktur. Mesaj tanımları (`comut`, `request` gibi) ve kanallar proje tarafında tanımlanır ve proje modülünden import edilir. Örnek proje `projects/example_project/` altındadır.

Bu belge, sık yapılan işler için ne yazacağını gösterir. Tam isim listesi için `asl_testing/__init__.py` içindeki `__all__` listesine bak.

---

## 1. Kurulum

```python
from asl_testing import Comm, FakeUtsClient
from projects.example_project.header import ProjectBase

uts = FakeUtsClient()                  # gerçek cihazda HttpUtsClient
comm = Comm(uts, [ProjectBase])
comm.open()                            # RX ve TX thread'leri başlar
...
comm.close()
```

`with` ile de kullanılabilir:

```python
with Comm(uts, [ProjectBase]) as comm:
    ...
```

`Comm`, test kodunun konuştuğu tek nesnedir. Gönderim, alım, olay aboneliği, UTS yönetimi ve izleme servisleri bu nesneden bağlanır.

---

## 2. Mesajı göndermek

Mesajlar proje tanımından oluşturulur. Gönderim yönü ve periyot tanımda ya da oluşturma sırasında verilir.

```python
req = request(SRC, DEST, 0x10, direction=Direction.TX)
comm.send(req)                  # bir kez; başarılıysa True
```

Periyodik gönderim:

```python
motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05))
comm.start(motor)               # 50 ms'de bir
...
comm.stop(motor)
```

Alanları gönderimden önce değiştirmek:

```python
motor.speed = 120
motor.cmd.startReq = 1          # bit alanı
req.request[1] = 50             # dizi elemanı
```

Her gönderimde bir değeri o an hesaplamak için `on_send` kancası kullanılır:

```python
def update_speed(m):
    m.speed = setpoint_now()        # setpoint_now: test kodunun kendi fonksiyonu

motor.on_send(update_speed)         # ya da dekoratör: @motor.on_send
comm.start(motor)                   # her periyodik gönderimde önce update_speed çalışır
```

- Kanca her `pack()` çağrısında, yani her gönderimde (tek seferlik ya da periyodik) çalışır.
- Kancanın yazdığı değerler pakete girer: uzunluk, sayaç ve CRC kancadan **sonra** hesaplanır.
- Periyodik mesajda kanca TX thread'inde çalışır; kısa tutulmalı, beklememeli.
- Kanca checksum'a dokunmamalıdır; `pack()` onu en son hesaplar.
- Gelen paket için karşılığı `msg.on_receive(fn)`: geçerli paket nesneye yazıldıktan sonra RX thread'inde çalışır.

---

## 3. Cevap beklemek

Tipik istek-cevap testi:

```python
status.has_new()                # önce eski paketleri temizle
comm.send(req)
if comm.wait_new(status, timeout=0.5):
    assert status.comut[0] == expected
else:
    raise AssertionError("cevap gelmedi")
```

- `has_new()` sayacı okur ve sıfırlar. Gönderimden **önce** çağrılması, eski bir paketin cevap sayılmasını önler.
- `wait_new(msg, timeout)` yeni geçerli paket gelene kadar bekler. Dönüş değeri yeni paket sayısıdır, zaman aşımında `0`.
- `peek_new()` aynı sayıyı verir ama sayacı sıfırlamaz. Bir kontrolü tekrarlamak için kullan.

Gönderim tarafı için aynı yapı:

```python
motor.has_sent()
comm.wait_sent(motor, timeout=0.2)   # periyodik mesajın bir sonraki karesi
motor.peek_sent()                    # sıfırlamadan bak
```

`wait_sent` yalnızca başarılı UTS gönderimlerini sayar. Hedefin paketi aldığını doğrulamaz; bunun için cevabı `wait_new` ile beklemek gerekir.

Bir yanıtta **belirli bir değeri** beklemek için `wait_for` kullan. `has_new` sadece "paket geldi mi" der;
`wait_for` gelen her paketin değerine bakar:

```python
mark = status.rx_history.mark()            # bundan önceki paketler sayılmaz
comm.send(req)
rec = comm.wait_for(status, lambda s: s.speed == 10, timeout=1.0, after=mark)
assert rec is not None, "speed 10 olmadı"
```

### Bütün paketleri görmek: mesaj geçmişi

UTS her yoklamada o ana kadar biriken paketlerin hepsini verir. Aynı mesajdan birkaç paket gelirse hepsi
sırayla nesneye yazılır ve `status.speed` sadece sonuncusunu gösterir. Aradaki değerler mesajın geçmişinde durur:

```python
mark = status.rx_history.mark()
comm.start(motor)
...
values = [r.snapshot().speed for r in status.rx_history.since(mark)]
assert values == [0, 10, 20, 30]           # sıra kontrolü
assert status.rx_history.dropped == 0      # kapasite yetti mi
```

- `rx_history.mark()` şu anki konumu verir. `since(mark)` ve `wait_for(..., after=mark)` sadece sonrasına bakar.
- Okumak hiçbir şeyi silmez. İki ayrı yer kendi `mark`'ıyla aynı geçmişi bağımsız okuyabilir (`has_new`'den farkı).
- Her kayıt (`Record`): `seq` (geliş sırası, bütün mesajlar arasında), `timestamp` (UTS zamanı), `host_time`,
  `snapshot()` (o paketin değerleri).
- Kapasite mesaj başına son 64 paket. Sınıfta `_history = 256` ya da nesnede `motor_status(..., history=256)`.
  Dolunca en eski düşer, `dropped` artar ve log'a bir kez uyarı yazılır.
- Mesaj nesnesi yeniden oluşturulunca geçmiş boş başlar. Sadece gelen (RX) paketler kaydedilir.

**Birden fazla alanı birlikte okumak:** `status.speed` ve `status.mode` iki ayrı okumadır, arada yeni paket
gelebilir. Aynı paketin değerleri için tek kopya al:

```python
s = status.snapshot()
assert s.speed == 10 and s.mode == 2
```

Zamanla ilgili bilgiler:

```python
status.rx_age          # son geçerli paketten bu yana saniye (yoksa None)
status.rx_timestamp    # UTS'in verdiği zaman
status.rx_host_time    # bu makinenin saatine göre zaman
```

Periyodik RX mesajı kesilirse `RxTimeout` olayı gelir; geri gelirse `RxRestored`.

---

## 4. Olaylarla izlemek

Her paket bir olay olarak yayınlanır. Olayı kendi thread'inde işleyen bir handler yazabilirsin.

```python
def on_status(ev: MessageReceived):
    print(ev.host_time, ev.message.comut[0], ev.raw.hex())

sub = comm.on_receive(status, on_status)     # yalnızca bu mesaj
```

Her mesaja değil, bir olay tipinin tamamına abone olmak:

```python
from asl_testing import WireReceived, InvalidReceived

comm.subscribe(InvalidReceived, lambda ev: print("bozuk:", ev.raw.hex()))
comm.subscribe(WireReceived, lambda ev: wires.append(ev.wire))
```

Abonelik bitince:

```python
comm.bus.unsubscribe(sub)
```

Olay tipleri:

| Olay | Ne zaman |
|---|---|
| `MessageReceived` | Geçerli paket alındı |
| `MessageSent` | Mesaj gönderildi |
| `InvalidReceived` | Paket geldi ama doğrulanamadı (bozuk CRC, yanlış boy ...) |
| `UnknownReceived` | Hiçbir mesajla eşleşmeyen paket (`ev.channel` ile kanalı belli) |
| `WireReceived` / `WireSent` | Tel üzerindeki ham bayt |
| `RxTimeout` / `RxRestored` | Periyodik RX kesildi / geri geldi |
| `LinkError` | UTS hatası (gönderim veya alım) |

Olayın içinde `ev.message`, `ev.raw` (envelope'suz mesaj baytları; tel üzerindeki hali için `WireReceived` / `WireSent`), `ev.host_time`, `ev.image` ve `ev.snapshot()` bulunur. `snapshot()` olayın anındaki değerleri ayrı bir nesne olarak verir; sonraki paketlerden etkilenmez.

---

## 5. Hedefi taklit etmek (simülasyon)

`FakeUtsClient` gerçek cihazın yerine geçer. Cihazın ürettiği paketi `inject` ile verirsin:

Cihazın gönderdiği paket, kanalın başlığıyla birlikte enjekte edilir:

```python
ch = status.channel
wire = ch.framing.envelope.on_send(status.pack())      # başlık varsa eklenir, yoksa değişmez
uts.inject(ch, wire)
```

`inject` paketi kanalın protokolüne göre UTS'in döndüreceği biçime çevirir (Ethernet / RS422: bayt listesi,
1553: 16 bitlik değer listesi). Gönderilenleri kontrol etmek için `uts.posted` kullanılır:

```python
comm.send(req)
path, interface, body = uts.posted[-1]                 # ("rs422", 0, {"message": [...]})
```

Bozuk paket göndermek için baytları değiştirip enjekte edersin:

```python
bad = bytearray(wire)
bad[-1] ^= 0xFF                                        # son bayt (CRC) bozuk
uts.inject(ch, bytes(bad))
```

Sonuç `InvalidReceived` olarak görülür.

Periyodik cihaz davranışı için bir thread yazıp `inject` çağırmak yeterlidir. `examples/monitor_demo.py` bunun örneğidir.

---

## 6. UTS yapılandırması ve filtreler

`comm.control` UTS'in ayarlarına ve filtrelerine doğrudan erişir:

```python
comm.control.set_config(channel, ...)        # hedefin yapılandırması (alan adları örnekte)
comm.control.get_config(channel)
comm.control.add_filter(status)              # mesajın imzası UTS filtresine eklenir
comm.control.remove_filter(status)
comm.control.get_filter(channel)
comm.control.clear_filter(channel)
```

Hedef olarak kanal ya da mesaj verilebilir.

Hatalar `UtsError` olarak fırlatılır:

```python
from asl_testing import UtsError
try:
    comm.control.set_config(channel, ...)
except UtsError as e:
    ...
```

---

## 7. Kayıt ve izleme

CSV'ye kayıt (sonradan analiz veya izleme için):

```python
from asl_testing import CommLogger
history = CommLogger(comm, "run.csv")
...
history.close()
```

Hataları ayrı dosyaya yazmak:

```python
from asl_testing import ErrorLog
errors = ErrorLog(comm, "errors.log")
```

Tarayıcıda canlı izleme (`http://127.0.0.1:8050`):

```python
from asl_testing import MonitorService
monitor = MonitorService(comm, [ProjectBase], port=8050)
monitor.start()
...
monitor.stop()
```

Kayıtlı bir CSV'yi testsiz açmak:

```
python -m asl_testing.services.monitor projects.example_project.header:ProjectBase projects.example_project.messages
```

Logging standart `logging` modülüyle yapılır: `asl_testing.*` logger'ları. `Comm(..., logger=x)` ile hepsini tek bir logger'a yönlendirebilirsin.

---

## 8. Kanallar ve protokoller (interface kullanımı)

Bu bölüm proje tanımında kullanılır, test kodunda değil.

### Kanal tanımı

Kanal, UTS'teki bir interface'tir. Her protokolün kendi kanal sınıfı vardır:

```python
from asl_testing import ChannelSet, EthernetChannel, Rs422Channel, Mil1553Channel, Framing

class MyChannels(ChannelSet):
    CONTROL = Rs422Channel(0)                                   # RS422, interface 0
    DIAG    = EthernetChannel(1, Framing(envelope=EthHeader()))  # Ethernet 1, 8 baytlık başlıkla
    BUS_A   = Mil1553Channel(1)                                 # 1553, interface 1
```

- Bir interface'in tek kanalı vardır. Aynı interface iki kez tanımlanırsa `ChannelSet` tanımlanırken hata verir.
  Farklı protokollerde aynı numara (Ethernet 1, 1553 1) farklı interface'tir.
- Mesaj kanalını sınıf varsayılanından (`_channel = MyChannels.CONTROL`) ya da nesne oluştururken (`channel=`) alır.

### Protokol: UTS'e ne gider

Her kanal tipinin bir protokol nesnesi vardır. Protokol, hattaki baytları UTS isteğine çevirir ve UTS'ten geleni geri baytlara çevirir.
Test kodu bunu görmez; `comm.send` / `comm.start` / `wait_for` her protokolde aynıdır.

| Kanal | Protokol | UTS'e giden / UTS'ten gelen |
|---|---|---|
| `EthernetChannel` | `EthernetProtocol` | `{"message": [b0, b1, ...], "timestamp": t}` |
| `Rs422Channel` | `Rs422Protocol` | `{"message": [b0, b1, ...], "timestamp": t}` |
| `Mil1553Channel` | `Mil1553Protocol` | `{"message": [rt, subnet, word_count, word, ...], "timestamp": t}` |

Protokol nesnesi kanalın parçasıdır. Verilmezse kanal tipinin varsayılanı kullanılır. UTS'in zamanı saniye değilse
ya da 1553 projesi big-endian ise nesne kanal tanımında verilir:

```python
from asl_testing import EthernetProtocol, Mil1553Protocol

class MyChannels(ChannelSet):
    DIAG  = EthernetChannel(1, Framing(envelope=EthHeader()), protocol=EthernetProtocol(time_unit=1e-6))
    BUS_A = Mil1553Channel(1, protocol=Mil1553Protocol(byte_order="big", time_unit=1e-6))
```

Gönderim, alım ve sahte UTS (`uts.inject(kanal, ...)`) aynı nesneyi kanaldan alır; ayrıca bir yere verilmez.

### 1553 mesajı tanımlamak

`rt`, `subnet` ve `word_count` mesajın ilk üç alanıdır ve `c_uint16` tanımlanır. Liste bu alanların değerleriyle başlar:

```python
class Bus1553(BaseMessageStructure, LittleEndianStructure):
    _fields_ = [("rt", c_uint16), ("subnet", c_uint16), ("wordCount", c_uint16)]
    _signature = Signature("rt", "subnet")          # gelen paket rt + subnet ile tanınır
    _channel = MyChannels.BUS_A

class rt30_status(Bus1553):
    _fields_ = [("mode", c_uint16), ("speed", c_uint32)]
    _defaults = {"rt": 30, "subnet": 1, "wordCount": 3}

# mode=1, speed=0x11223344 -> {"message": [30, 1, 3, 0x0001, 0x3344, 0x1122]}
```

- Değerleri protokol kontrol etmez; `rt`, `subnet` ve `wordCount` mesaj tanımından ve testten gelir.
- `Mil1553Protocol(byte_order=...)` mesaj yapısının endian'ıyla aynı olmalı. `LittleEndianStructure` için `"little"` (32 bitlik alanda düşük kelime önce),
  `BigEndianStructure` için `"big"` (yüksek kelime önce). Uyuşmazsa her değerin baytları ters gider: `30` → `7680`.

### Başlık ve akış (framing)

- `Envelope.on_send` gönderimde başlık ekler, `Envelope.on_receive` alımda başlığı kontrol edip çıkarır. Paket bu kanala ait değilse `None` döner.
- `Splitter` UTS'ten gelen akışı paketlere böler (ör. RS422'de bir GET öğesinde birden fazla paket). Protokol çözdükten sonra çalışır.
- Envelope'u kabul etmeyen paket, geldiği kanalda bilinmeyen paket olur (`UnknownReceived`, `comm.unknown`).
- RX mesajı olmayan bir kanalın paketlerini görmek için `comm.listen(kanal)`.

---

## 9. Sık yapılan işler

**Periyodik cihaz, komut tepkisi:**
```python
comm.start(motor)
status.has_new()
assert comm.wait_new(status, timeout=0.3) > 0
assert status.comut[0] > 0
comm.stop(motor)
```

**Cevap gelmeyince hata:**
```python
status.has_new()
comm.send(req)
assert comm.wait_new(status, timeout=0.5), "cevap yok"
```

**Bir değerin kısa süreliğine oluştuğunu yakalamak:**
```python
mark = status.rx_history.mark()
comm.send(req)
assert comm.wait_for(status, lambda s: s.errorBit == 1, timeout=0.5, after=mark), "hata biti hiç 1 olmadı"
```

**Bozuk cevabı görmek:**
```python
invalid = []
comm.subscribe(InvalidReceived, lambda ev: invalid.append(ev))
...
assert len(invalid) == 1
```

**Bilinmeyen paketleri saymak:**
```python
assert len(comm.unknown) == 0
```

---

## Henüz olmayanlar

- **Hata enjeksiyonu** (CRC, uzunluk, bit bozma): tasarlandı, henüz eklenmedi. Önerilen yapı: mesaja bağlı `msg.fault` ve `Fault.corrupt / resize / flip / raw`. Gönderim sırası `pack()` → fault → envelope → UTS.
- **`comm.unsubscribe`** kısayolu: şimdilik `comm.bus.unsubscribe(sub)`.
- **Gerçek HTTP UTS istemcisi:** `HttpUtsClient` henüz taslak (`post` / `get` UTS API'si netleşince yazılacak).
- **CAN:** kanal sınıfı ve protokol nesnesi yok.
