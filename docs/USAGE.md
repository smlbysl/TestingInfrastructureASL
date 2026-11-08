# Kullanım kılavuzu

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

Her gönderimde değer hesaplamak için kanca (değer test kodunda hesaplanır):

```python
motor.on_send(lambda m: setattr(m, "speed", setpoint_now()))   # setpoint_now: test kodunun kendi fonksiyonu
```

Kanca gönderimden hemen önce çalışır. Sayaç ve CRC gibi alanlar kancadan sonra hesaplanır.

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
uts.inject(ch.protocol, ch.interface, wire)
```

Bozuk paket göndermek için baytları değiştirip enjekte edersin:

```python
bad = bytearray(wire)
bad[-1] ^= 0xFF                                        # son bayt (CRC) bozuk
uts.inject(ch.protocol, ch.interface, bytes(bad))
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

## 8. Çerçeveleme (özel başlık, akış)

Bu bölüm yalnızca kanal tanımında kullanılır, test kodunda değil. Proje tanımında:

```python
from asl_testing import Envelope, Framing, Splitter, EthernetChannel, Rs422Channel, ChannelSet

class MyChannels(ChannelSet):
    CONTROL = Rs422Channel(0)
    DIAG    = EthernetChannel(1, Framing(envelope=EthHeader()))   # başlığı olan
    RAW     = EthernetChannel(1)                                   # başlıksız
```

- `Envelope.on_send` gönderimde başlık ekler.
- `Envelope.on_receive` yalnızca kendi paketini kabul eder, diğerlerinde `None` döner. Böylece paket sıradaki kanala geçer.
- `Splitter` UTS'ten gelen akışı paketlere böler. Bir adreste en fazla bir tane olabilir.

Kanal kuralları tanım sırasında kontrol edilir: bir adreste en fazla bir başlıksız kanal olabilir.

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
- **Gerçek HTTP UTS istemcisi:** `HttpUtsClient` henüz taslak.
