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
comm = Comm(uts, [ProjectBase])        # birden fazla bus: Comm(uts, [ProjectBase, Mil1553Base, CanBase])
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

Mesajın kanalının protokolü bir adres (PCI) istiyorsa, nesne oluşturulurken verilir. Eksikse `TypeError`, aralık dışındaysa `ValueError` alırsın:

```python
report = bit_report(node=5, subnet=3)            # MIL-STD-1553: node ve subnet zorunlu (1..32)
wheel  = wheel_speed()                           # CAN: id sınıfta (_address = {"can_id": 0x123})
brake  = brake_cmd(can_id=0x201, direction=Direction.TX)   # ya da nesnede
report.pci                                       # node=5 subnet=3
```

Ethernet ve RS422'de adres yok; bugünkü gibi oluşturulur.

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

Kanca gönderimden hemen önce çalışır. Sayaç ve CRC gibi alanlar kancadan sonra, değerlerin tek bir kopyası üzerinde hesaplanır. Bu yüzden başka bir thread'in o anda yazdığı bir alan, eski CRC ile hatta gitmez.

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

### Geçmiş: aynı poll'de gelen bütün paketler

UTS bir sorguda aynı mesajdan birden fazla paket döndürebilir. Canlı nesne yalnızca sonuncusunu gösterir, ama her geçerli paket mesajın geçmişine (`rx_history`) kaydedilir:

```python
mark = status.rx_history.mark()                 # bu noktadan sonraki paketler sayılır
comm.send(req)
rec = comm.wait_for(status, lambda s: s.comut[0] == 10, timeout=1.0, after=mark)
assert rec is not None                           # 10 değeri bir poll'ün ortasında gelse de bulunur

for r in status.rx_history.since(mark):          # mark'tan beri gelen her paket, sırayla
    print(r.seq, r.timestamp, r.snapshot().comut[0])

assert status.rx_history.dropped == 0            # kapasite yetti mi
```

- `wait_for` her paketin anlık görüntüsüyle (`snapshot`) predicate'i çağırır ve yeni paket gelince uyanır.
- `mark()` okuyana aittir; iki yer aynı mesajı okusa da birbirinin verisini tüketmez (`has_new`'den farkı).
- Kapasite sınıf ayarı `_history` (varsayılan 64) ya da nesnede `history=` ile değişir; taşan en eski kayıt düşer.
- Gönderilenler de `tx_history`'de tutulur.

### Birden fazla alanı aynı paketten okumak

```python
s = status.snapshot()                            # o anki değerlerin tek bir kopyası
assert s.comut[0] == 1 and s.comut[1] == 2       # iki alan da aynı paketten
```

`status.comut[0]` gibi tek alan okuması her zaman tutarlıdır (yarım paket görülmez). İki ayrı okuma arasında yeni bir paket gelebileceği için birden fazla alan için `snapshot()` kullan.

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
| `UnknownReceived` | Hiçbir mesajla eşleşmeyen paket (`ev.channel` kanalı, `ev.pci` adresi) |
| `WireReceived` / `WireSent` | Tel üzerindeki ham bayt |
| `RxTimeout` / `RxRestored` | Periyodik RX kesildi / geri geldi |
| `LinkError` | UTS hatası (gönderim, alım ya da UTS'ten gelen bozuk biçimli öğe) |

Olayın içinde `ev.message`, `ev.raw` (mesaj baytları, protokol başlığı olmadan; hattaki hali için `WireReceived` / `WireSent`), `ev.host_time`, `ev.image` (paketin kendisi, `on_receive` kancalarından önce) ve `ev.snapshot()` bulunur. `snapshot()` olayın anındaki değerleri ayrı bir nesne olarak verir; sonraki paketlerden etkilenmez.

---

## 5. Hedefi taklit etmek (simülasyon)

`FakeUtsClient` gerçek UTS'in yerine geçer ve cihazın gönderdiği paketleri üç düzeyde üretebilir:

```python
device = comut(DEST, SRC, 0x20, direction=Direction.TX)   # cihazın kopyası
uts.device_sends(device)                                 # mesaj nesnesi: PCI ve başlık protokolden eklenir

bad = bytearray(device.pack())
bad[-1] ^= 0xFF                                          # son bayt (CRC) bozuk
uts.device_sends_bytes(status.channel, bytes(bad))       # mesaj baytları: başlık yine eklenir -> InvalidReceived

uts.inject("1553", 1, {"message": [5, 3, 2, 0x0001, 0x0014]})   # ham UTS öğesi (JSON)
```

- `device_sends` en sık kullanılan yol; mesajın kanalı, adresi (PCI) ve protokol başlığı otomatik gelir.
- `device_sends_bytes(kanal, baytlar, pci=None)` bozuk ya da elle yazılmış paketler için.
- `inject(path, interface, öğe)` UTS'in tam olarak ne döndüreceğini yazmak için; bozuk biçimli bir öğe `LinkError` olur.
- `uts.sent` gönderilenleri `(path, interface, gövde)` olarak tutar.

Periyodik cihaz davranışı için bir thread yazıp `device_sends` çağırmak yeterlidir. `examples/monitor_demo.py` bunun örneğidir.

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

## 8. Kanallar ve protokoller

Bu bölüm proje tanımında kullanılır, test kodunda değil:

```python
from asl_testing import CanChannel, ChannelSet, EthernetChannel, Mil1553Channel, Rs422Channel

class MyChannels(ChannelSet):
    CONTROL = Rs422Channel(0)
    DIAG    = EthernetChannel(1, header=EthHeader())     # başlığı olan
    RAW     = EthernetChannel(1)                         # aynı interface, başlıksız
    BUS_A   = Mil1553Channel(1)                          # node + subnet
    CAN0    = CanChannel(0)                              # can_id
```

Her kanal bir protokol nesnesi taşır. Protokol, mesajın o bus'taki adresini (PCI) ve kurallarını bilir; UTS'e nasıl yazılacağı ise ayrı bir adaptörün işidir.

**Bayt akışında başlık (`Header`):**

```python
from asl_testing import NO_PCI, Header

class EthHeader(Header):
    offset = 8                                           # mesajın önündeki bayt sayısı (UTS filtreleri için)

    def encode(self, pci, sdu) -> bytes:                 # gönderim: başlık + mesaj
        return b"\x55\xAA" + struct.pack("<H", 8 + len(sdu)) + bytes(4) + sdu

    def decode(self, data):                              # alım: (pci, mesaj) ya da None
        if data[:2] != b"\x55\xAA":
            return None                                  # bu kanalın paketi değil: sıradaki kanal denenir
        return NO_PCI, data[8:]
```

`decode` yalnızca kendi paketini kabul etmeli. Her paketi kabul eden bir başlık, aynı interface'teki başlıksız kanalın paketlerini yutar.

**Tanıma sırası** (bir kanala gelen paket için):
1. Adres (PCI): 1553'te node + subnet, CAN'da id. Ethernet/RS422'de adres yoksa kanalın bütün mesajları adaydır.
2. O adreste signature'sız tek bir mesaj varsa, adresin bütün paketleri onundur.
3. Değilse mesajın içindeki signature alanları eşleşen mesaj.
4. Hiçbiri: `UnknownReceived`.

Belirsizlikler tanım sırasında hata verir: aynı adreste signature'sız bir mesajın yanına başka mesaj tanımlanamaz, aynı signature iki mesajda olamaz. Bir adreste en fazla bir başlıksız kanal ve en fazla bir splitter olabilir.

**Aynı adreste birden fazla mesaj (1553 örneği):**

```python
class ModeFamily(Mil1553Base):
    _signature = Signature("kind")                       # ilk word hangi mesaj olduğunu söyler

class mode_a(ModeFamily):
    _fields_ = [("kind", c_uint16), ("value", c_uint16)]
    _defaults = {"kind": 1}
```

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

**Bir değerin bir an görülüp görülmediği (poll'ün ortasında bile):**
```python
mark = report.rx_history.mark()
comm.send(start_cmd)
assert comm.wait_for(report, lambda s: s.temperature > 80, timeout=2.0, after=mark)
```

---

## Henüz olmayanlar

- **Hata enjeksiyonu** (CRC, uzunluk, bit bozma): tasarlandı, henüz eklenmedi. Önerilen yapı: mesaja bağlı `msg.fault` ve `Fault.corrupt / resize / flip / raw`. Gönderim sırası `pack()` → fault → adaptör → UTS.
- **Gerçek UTS biçimleri:** 1553 ve bayt akışı gövdeleri bildiğimiz kadarıyla yazıldı, CAN gövdesi varsayım; UTS zaman biriminin saniye karşılığı `Comm(..., time_unit=...)` ile verilir.
- **Kanal config'i** (RS422 / Camera Link seçimi, CANopen ayarları) henüz `comm.open()` sırasında gönderilmiyor; şimdilik `comm.control.set_config(...)`.
- **`comm.unsubscribe`** kısayolu: şimdilik `comm.bus.unsubscribe(sub)`.
- **Gerçek HTTP UTS istemcisi:** `HttpUtsClient` henüz taslak.
