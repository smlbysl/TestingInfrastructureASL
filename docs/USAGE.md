# Kullanım kılavuzu

Yazar: İsmail Baysal

Bu belge nasıl yazılacağını gösterir. Her arayüzün ayrıntılı listesi, test için anlamlı olup olmadığı ve açık tasarım soruları için `docs/TEST_API.md`'ye bak.

Test yazarken bütün isimler tek bir yerden gelir:

```python
from asl_testing import Comm, FakeUtsAdapter, Timing, Direction, MessageReceived
```

Kütüphanenin iç modüllerine (`asl_testing.runtime`, `asl_testing.message.state` ...) test kodunda gerek yoktur. Mesaj tanımları (`comut`, `request` gibi) ve kanallar proje tarafında tanımlanır ve proje modülünden import edilir. Örnek proje `projects/example_project/` altındadır.

Bu belge, sık yapılan işler için ne yazacağını gösterir. Tam isim listesi için `asl_testing/__init__.py` içindeki `__all__` listesine bak.

---

## 1. Kurulum

```python
from asl_testing import Comm, FakeUtsAdapter
from projects.example_project.header import ProjectBase

adapter = FakeUtsAdapter()             # gerçek cihazda kendi UtsAdapter alt sınıfınız (bkz. bölüm 6)
comm = Comm(adapter, [ProjectBase])
comm.open()                            # RX ve TX thread'leri başlar (kanal başına)
...
comm.close()
```

`with` ile de kullanılabilir:

```python
with Comm(adapter, [ProjectBase]) as comm:
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

Bir kanaldaki (ya da hepsindeki) bütün periyodik mesajları birlikte başlatmak ve durdurmak:

```python
comm.start_all(MyChannels.CONTROL)      # CONTROL'de tx=Timing(periyot) tanımlı bütün TX mesajları
comm.start_all()                        # bütün kanallar
comm.stop_all(MyChannels.CONTROL)
comm.stop_all()
```

- `start_all` çağrıldığı anda kayıtlı olan mesajları başlatır; sonradan tanımlanan mesaj kendiliğinden başlamaz.
- Zaten çalışan mesaj yeniden başlatılmaz, zamanı kaymaz. Periyodik `tx` zamanlaması olmayan mesaj başlatılmaz.
- İkisi de başlattığı / durdurduğu mesajların listesini döndürür.
- Bir sonraki gönderim, bir öncekinin başladığı andan bir periyot sonra. Bir gönderim geç kalırsa kaçan periyotlar
  peş peşe gönderilmez; her gönderim sıradaki sayaçla gider. Saniyedeki gönderim sayısı periyodun verdiğinden
  biraz az olabilir (ör. 200 Hz'de ~190–195).
- Windows: `Comm` açıkken zamanlayıcı çözünürlüğü 1 ms'ye alınır (`timeBeginPeriod(1)`, kapanınca geri verilir) ve
  TX zamanı `time.perf_counter()` ile ölçülür. Aksi halde Windows'ta uyuma ve `time.monotonic()` (Python 3.12 ve öncesi)
  15,6 ms adımlarla ilerler; 5 ms periyot ~64 Hz'de kalır.

Alanları gönderimden önce değiştirmek:

```python
motor.speed = 120
motor.cmd.startReq = 1          # bit alanı
req.request[1] = 50             # dizi elemanı
```

Düz yazma kilitsizdir: periyodik gönderilen bir mesajda iki alanın arasına bir paket girebilir ve gönderim sırasında
yazılan istek biti `after_send` tarafından silinebilir (B12). Birlikte gitmesi gereken alanlar ve istek bitleri
mesajın kilidi altında yazılır:

```python
with motor.locked_update():
    motor.speed = 3
    motor.cmd.mode = 1
    motor.cmd.startReq = 1
```

- Blok başlarken bu mesajın süren bir gönderimi varsa (`after_send` dahil) bitmesi beklenir; blok sürerken bu
  mesajın gönderimi (periyodik ya da `comm.send`) başlamaz. Yazılanlar aynı pakette, birlikte gider.
- İstek biti blok içinde yazılırsa `after_send` onu gönderilmeden silemez (B12).
- Blok kısa tutulur: içinde `sleep`, `wait_new`, `wait_for` olmaz. Blok sürerken bu mesajın periyodik gönderimi
  bekler; aynı kanaldaki diğer mesajlar etkilenmez.
- Blokları arada hiç beklemeden arka arkaya açan bir döngü, periyodik gönderimin kilidi almasını geciktirebilir
  (Python kilidi bekleyenler arasında sıra garantisi vermez).
- Blok içinden `comm.send(motor)` çağrılabilir. Düz atama olduğu için yanlış alan adı hata vermez.

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
- Kanca mesajın kilidi altında çalışır. Kanca başka bir mesajı `comm.send` ile gönderebilir; ama iki mesajın
  kancası birbirini göndermemeli (ikisi aynı anda gönderilirse birbirini bekleyip kilitlenir).
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
| `MessageSent` | Mesaj gönderildi (`ev.timestamp`: UTS'in POST cevabındaki gönderim zamanı) |
| `InvalidReceived` | Paket geldi ama doğrulanamadı (bozuk CRC, yanlış boy ...) |
| `UnknownReceived` | Hiçbir mesajla eşleşmeyen paket (`ev.channel` ile kanalı belli) |
| `WireReceived` / `WireSent` | Tel üzerindeki ham bayt |
| `RxTimeout` / `RxRestored` | Periyodik RX kesildi / geri geldi |
| `RxOverflow` | UTS'in alım tamponu taştı, önceki paketler kayboldu (o GET'in paketleri yine işlenir) |
| `LinkError` | UTS hatası (gönderim veya alım; hata cevabında `ev.error.status`, `ev.error.code`) |

Olayın içinde `ev.message`, `ev.raw` (envelope'suz mesaj baytları; tel üzerindeki hali için `WireReceived` / `WireSent`), `ev.host_time`, `ev.image` ve `ev.snapshot()` bulunur. `snapshot()` olayın anındaki değerleri ayrı bir nesne olarak verir; sonraki paketlerden etkilenmez.

---

## 5. Hedefi taklit etmek (simülasyon)

`FakeUtsAdapter` gerçek cihazın yerine geçer. Cihazın ürettiği paketi `inject` ile verirsin:

Cihazın gönderdiği paket, kanalın başlığıyla birlikte enjekte edilir:

```python
ch = status.channel
wire = ch.framing.envelope.on_send(status.pack())      # başlık varsa eklenir, yoksa değişmez
adapter.inject(ch, wire)
```

`inject` paketi kanalın protokol tanımına (`UtsAdapter`'daki) göre UTS'in döndüreceği biçime çevirir (Ethernet / RS422: bayt listesi,
1553: 16 bitlik değer listesi). Gönderilenleri kontrol etmek için `adapter.posted` kullanılır:

```python
comm.send(req)
path, interface, body = adapter.posted[-1]                 # ("serials", 0, {"message": [...]})
```

Bozuk paket göndermek için baytları değiştirip enjekte edersin:

```python
bad = bytearray(wire)
bad[-1] ^= 0xFF                                        # son bayt (CRC) bozuk
adapter.inject(ch, bytes(bad))
```

Sonuç `InvalidReceived` olarak görülür.

Periyodik cihaz davranışı için bir thread yazıp `inject` çağırmak yeterlidir. `examples/monitor_demo.py` bunun örneğidir.

### Bir düğümü taklit etmek: abonelerle simülasyon

Test sistemi bir düğümün yerine geçebilir (CAPL düğümü gibi): gelen mesaja tepki verir, kendi durumunu periyodik gönderir.
`examples/simulation.py` tam bir örnek; özü:

```python
class NodeSimulator:
    def __init__(self, comm):
        self.command = request(DUT, SIM, 0x10, rx=Timing(0.02, tolerance=5))           # DUT'tan gelen
        self.status = comut(SIM, DUT, 0x20, direction=Direction.TX, tx=Timing(0.05))  # bizim durumumuz
        self.status.on_send(self._fill_status)                     # her gönderimden hemen önce
        comm.on_receive(self.command, self._on_command)            # her geçerli istekte
        comm.subscribe(RxTimeout, self._on_timeout, where=self.command)   # istekler kesilince

    def _on_command(self, event):
        self.mode = event.snapshot().request[0]                    # o paketin değeri
        self.comm.send(self.status)                                # hemen cevap

    def _fill_status(self, msg):
        msg.comut[0] = self.mode
```

- Her handler kendi abone thread'inde çalışır; `on_send` hook'u gönderen thread'de, mesaj kilidi altında çalışır.
- Değerler `event.snapshot()` ile okunur (o paketin değerleri, sonradan gelen paketin değil).
- Gerçek düzenekte örnekteki "fake DUT" kısmı çıkarılır, adaptör olarak `UtsAdapter` alt sınıfı kullanılır.

---

## 6. UTS yapılandırması ve filtreler

`comm.adapter` UTS'in ayarlarına ve filtrelerine doğrudan erişir:

```python
comm.adapter.set_config(channel, ...)        # hedefin yapılandırması (alan adları örnekte)
comm.adapter.get_config(channel)
comm.adapter.add_filter(status)              # mesajın imzası UTS filtresine eklenir
comm.adapter.remove_filter(status)
comm.adapter.get_filter(channel)
comm.adapter.clear_filter(channel)
```

Hedef olarak kanal ya da mesaj verilebilir.

**İstek timeout'u.** Her UTS isteği cevabı sınırlı süre bekler: Ethernet ve 1553'te 2 sn, RS422'de 3 sn (GET için
de aynı). Süre dolarsa istek başarısız sayılır (`AdapterError`); tekrar denenmez. Gönderimde `comm.send` `False` döner ve
`LinkError` yayınlanır. Hepsi için tek değer vermek istersen:

```python
adapter = FakeUtsAdapter(timeout=5.0)   # gerçek adaptör için de aynı parametre
```

Gerçek `UtsAdapter`'ı yazarken `post` ve `get` bu süreyi `timeout` parametresi olarak alır; süre içinde cevap gelmezse
`AdapterError` fırlatmalıdır.

Hatalar `AdapterError` olarak fırlatılır:

```python
from asl_testing import AdapterError
try:
    comm.adapter.set_config(channel, ...)
except AdapterError as e:
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

Kanal sadece protokolünün adını taşır (`ch.protocol`: `"ethernet"`, `"rs422"`, `"mil1553"`). O protokolün UTS'te
nasıl yazıldığı `UtsAdapter`'daki tanımdadır: hattaki baytları UTS isteğine çevirir, UTS'ten geleni geri baytlara çevirir.
Test kodu bunu görmez; `comm.send` / `comm.start` / `wait_for` her protokolde aynıdır.

| Kanal | Protokol tanımı (`UtsAdapter`) | UTS yolu | UTS'e giden / UTS'ten gelen |
|---|---|---|---|
| `EthernetChannel` | `EthernetProtocol` | `/ethernet` | `{"message": [b0, b1, ...]}` |
| `Rs422Channel` | `Rs422Protocol` | `/serials` | `{"message": [b0, b1, ...]}` |
| `Mil1553Channel` | `Mil1553Protocol` | `/mil1553` | `{"message": [rt, subnet, word_count, word, ...]}` |

UTS'in cevapları (seri port için belgelenmiş; diğerlerinde aynı biçim varsayılıyor):

```
POST 200: {"statusInfo": {"status": "OK", "code": 200, "message": "..."}, "timestamp": t}
GET  200: {"statusInfo": {...}, "messages": [{"message": [...], "timestamp": t}, ...], "isBufferOverflow": false}
Hata    : aynı statusInfo; ör. 400 (boş mesaj / port kapalı), 404 (geçersiz interface), 500 (HAL timeout), 503 (eINIT)
```

- `t` mikrosaniyedir; adaptör saniyeye çevirir (`time_unit=1e-6`, varsayılan).
- POST cevabındaki zaman `MessageSent.timestamp` olur.
- GET tamponu boşaltır. Tampon taşarsa UTS en yeni paketleri tutar ve `isBufferOverflow` verir; RX thread'i bir uyarı
  loglar ve `RxOverflow` yayınlar, gelen paketler yine işlenir.
- 200 olmayan cevap `AdapterError` olur (`status`, `code`, mesaj); gönderim başarısız sayılır, `LinkError` yayınlanır.

Ayarın yeri, neye bağlı olduğuna göre:

- 1553 kelime sırası projenin mesaj yapısına bağlıdır, kanalda verilir.
- UTS zaman birimi UTS'e bağlıdır, adaptörde verilir (varsayılan mikrosaniye).

```python
class MyChannels(ChannelSet):
    BUS_A = Mil1553Channel(1, byte_order="big")    # proje endian="big"

adapter = FakeUtsAdapter(time_unit=1e-3)            # UTS zamanı milisaniye olsaydı (varsayılan 1e-6)
```

Gönderim, alım ve sahte UTS (`adapter.inject(kanal, ...)`) aynı tanımı adaptörden, kelime sırasını kanaldan alır.

### Bayt sırası (endian)

Projenin bayt sırası tek yerde, projenin `settings.py` dosyasında tutulur; proje sınıfı ve projenin bütün özel alan
tipleri onu `endian=ENDIAN` ile alır. Verilmezse little-endian'dır.

```python
# projects/<proje>/settings.py
ENDIAN = "big"

# types.py
class Counter8(CounterType, endian=ENDIAN):
    _fields_ = [("value", c_uint16)]

# header.py
class ProjectBase(BaseMessageStructure, endian=ENDIAN):
    ...

class motor_cmd(Family1):                           # alt sınıflar endian'ı miras alır, yazılmaz
    ...
```

- Big-endian mesaja little-endian bir özel tip konursa (ya da tersi) sınıf tanımlanırken `TypeError` verir. Bir tipte
  `endian=ENDIAN` unutulursa hata bu şekilde hemen görünür.
- Big-endian'da bit alanları baytın en yüksek bitinden başlar: `CmdByte.startReq = 1` big'de `0x80`, little'da `0x01`.
- Eski yazım `class X(BaseMessageStructure, BigEndianStructure)` artık hata verir (`metaclass conflict`);
  `endian="big"` yazılır.
- Bir bit grubu tek tiple yazılır (ör. hepsi `c_uint8`). `c_uint8` bitlerinin hemen arkasından `c_uint16` bitleri
  gelirse yerleşim Python sürümüne göre değişir: Linux'ta 3.13 ikisini aynı bayta sıkıştırır, 3.14 `c_uint16`'yı
  kendi kelimesinde başlatır. Kütüphane `_layout_ = "ms"` (MSVC kuralları) kullanır, Windows ve Linux'ta aynıdır.

### 1553 mesajı tanımlamak

`rt`, `subnet` ve `word_count` mesajın ilk üç alanıdır ve `c_uint16` tanımlanır. Liste bu alanların değerleriyle başlar:

```python
class Bus1553(BaseMessageStructure, endian=ENDIAN):
    _fields_ = [("rt", c_uint16), ("subnet", c_uint16), ("wordCount", c_uint16)]
    _signature = Signature("rt", "subnet")          # gelen paket rt + subnet ile tanınır
    _channel = MyChannels.BUS_A

class rt30_status(Bus1553):
    _fields_ = [("mode", c_uint16), ("speed", c_uint32)]
    _defaults = {"rt": 30, "subnet": 1, "wordCount": 3}

# mode=1, speed=0x11223344 -> {"message": [30, 1, 3, 0x0001, 0x3344, 0x1122]}
```

- Değerleri protokol tanımı kontrol etmez; `rt`, `subnet` ve `wordCount` mesaj tanımından ve testten gelir.
- Her alan 16 bitlik sınırda başlamalı ve boyu çift bayt olmalı (`c_uint16`, `c_uint32`, `c_uint16` bit alanı).
  Aksi halde bir kelime iki alanın parçalarını taşır ve liste yanlış olur; kod bunu kontrol etmez.
- `Mil1553Channel(..., byte_order=...)` projenin `ENDIAN` değeriyle aynı olmalı: `"little"` (32 bitlik alanda düşük kelime önce),
  `"big"` (yüksek kelime önce). Uyuşmazsa her değerin baytları ters gider: `30` → `7680`.

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
- **1553 RX etkinleştirme**: periyodik olmayan 1553 RX mesajı için UTS'e önce bir kez `[rt, subnet, wordCount]` gönderilmesi. Tasarlandı (DESIGN.md, Tasarım 4), henüz eklenmedi.
- **`comm.unsubscribe`** kısayolu: şimdilik `comm.bus.unsubscribe(sub)`.
- **Gerçek UTS adaptörü:** `UtsAdapter`'ın alt sınıfı olarak yazılacak (`post` / `get` eldeki `ApiWrapper` ile).
- **CAN:** kanal sınıfı ve protokol tanımı yok.
