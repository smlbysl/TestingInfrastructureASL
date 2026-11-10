# Mesaj Geçmişi (Ring Buffer), Snapshot ve Thread Güvenliği — Devir Notu

> Bu dosya başka bir session'a aktarılmak için hazırlandı. Yeni session bu dosyayı okuyarak konuşmanın
> nereden geldiğini, ne istendiğini, hangi kararların verildiğini, hangi açıkların bulunduğunu ve önerilen
> tasarımı eksiksiz görebilmeli. Kodda henüz **hiçbir değişiklik yapılmadı**; aşağıdakiler analiz ve öneridir.

---

## 0. Bağlam

| Konu | Değer |
|---|---|
| Proje | TestingInfrastructure — Ethernet/RS422 ile haberleşen hedef donanım için Python test altyapısı |
| Repo | `smlbysl/TestingInfrastructureASL` (GitHub) |
| Çalışılan dal | `v2.1-base` (son commit `382f7d1`). `master` (v2.2) sadece referans. |
| Haberleşme | UTS (C++, Windows) — HTTPS: POST ile gönderim, GET ile interface başına buffer'ı döndürüp boşaltan mesaj listesi (timestamp'li) |
| Python | Test ortamında CPython 3.13 ile doğrulandı (GIL'li) |
| Kod yorumları | İngilizce olmalı |

### İlgili dosyalar (v2.1-base)

| Dosya | Rolü |
|---|---|
| `asl_testing/message/base.py` | `BaseMessageStructure`: `decode`, `validate`, `pack`, `has_new`, `rx_*` property'leri |
| `asl_testing/message/fields.py` | `FieldType` (gömülü ctypes Structure), `LengthType`, `CounterType`, `ChecksumType`, `AsciiType` |
| `asl_testing/message/state.py` | `RxState` / `TxState` (sayaçlar, zaman, `check_new`) |
| `asl_testing/runtime/rx.py` | `RxPoller`: tek thread, sabit aralıkla UTS'yi poll eder, her frame'i dispatcher'a verir |
| `asl_testing/runtime/dispatcher.py` | frame → lookup → `msg.decode` → `MessageReceived(…, image=bytes(msg))` |
| `asl_testing/runtime/transport.py` | `poll`: UTS fetch + RS422 splitter + envelope; batch'teki frame'lere aynı `host_time` |
| `asl_testing/runtime/tx.py` | `TxScheduler`: `send` tek kilit altında `pack` + `bytes(msg)` + UTS; periyodik thread |
| `asl_testing/events/types.py` | `MessageEvent` (`raw`, `image`, `snapshot()`), `MessageReceived`, `MessageSent` |
| `asl_testing/events/bus.py` | `EventBus`: abone başına kuyruk + thread |
| `asl_testing/comm.py` | Test API: `send`, `start`, `stop`, `wait_new`, `wait_sent`, `on_receive`, `subscribe` |
| `projects/example_project/*` | Örnek proje: `ProjectBase` (düz header alanları), `Family1/2`, `Serial2`, `motor_cmd`, `CmdByte` … |
| `docs/DESIGN.md` | Tasarım notları; "Açık konular" bölümünde bilinen bazı açıklar zaten var (bkz. §4.3) |

### Yapı hakkında doğru bilinmesi gerekenler

- **Ayrı bir header struct yok.** `sourceId`, `destinationId`, `messageId`, `messageLength`, `messageCounter`
  `ProjectBase._fields_` içinde **düz** alanlar. (Konuşmada bir ara `mesaj.header.counter` örneği verildi;
  bu yanlıştı, kullanıcı düzeltti.)
- Ancak **özel alanlar** (`messageLength: Length16`, `messageCounter: Counter8`, `checksum: CRC16`, `cmd: CmdByte`)
  ve **diziler** (`request: c_uint32 * 4`) gömülü ctypes nesneleridir: `msg.cmd`, `msg.messageCounter`,
  `msg.request` okunduğunda mesajla **aynı belleği paylaşan bir alt obje (view)** döner.
- Thread modeli: 1 `RxPoller` thread'i, 1 `TxScheduler` thread'i, bus'ta abone başına 1 thread, artı testin kendi
  thread'i. Mesaj objesine RX thread'i (decode), TX thread'i (periyodik pack) ve test thread'i (alan okuma/yazma)
  aynı anda dokunabilir.
- Altyapıda snapshot kavramı **zaten var**: `MessageEvent.image` (decode/pack sonrası ctypes görüntüsü) ve
  `event.snapshot()` (`type(msg).from_buffer_copy(image)`).

---

## 1. Kullanıcının isteği

Kullanıcının ifadesiyle (özet):

> Tasarımda aynı request içinde UTS'den aynı mesaj için aynı anda birden fazla paket gelebilir. Bu durumda
> mesaj objesi aynı fetch döngüsünde birden fazla kez güncellenir ve değerlerin çok hızlı güncellenmesinden
> dolayı bazı değerler kaybolabilir. Bunun için her mesaj için bir ring buffer tutma ihtiyacı olabilir. Bu yapı
> profesyonel olarak nasıl basit kurgulanabilir, analiz et.

Konuşma içinde eklenen sorular:

1. Bir thread yazarken diğerinin okuması (torn read) nasıl çözülür?
2. Var olan yapıya mutex eklemek mümkün değil mi?
3. Başka bir session'da konuşulan **alternatif field type yapısı**nın bu konuda avantajı olur mu?
   (O yapı bu session'da görülemedi; bkz. §8.)
4. Snapshot nasıl kullanılacak, buffer kullanımı nasıl olacak, kaç dosya değişecek, önerilen koruma güvenli mi?

### Kullanıcının önceden belirttiği ve bu tasarımı bağlayan tercihler

- Mesaj objeleri doğrudan kullanılmalı: `mesaj.speed = 10`, `print(status.speed)`.
- Mesaj tanımlarken/oluştururken wrap eden yapı (dekoratör, `with` bloğu) istenmiyor.
- Test yazan kişi mesaj objesini her testcase'de yeniden oluşturabilmeli; aynı sınıf+channel+signature+yön ile
  yeniden oluşturulan obje eskisinin yerini alır.
- Daha önce istenen: her mesaj için config edilebilir ring buffer; RX'te gelen paket timestamp ile buffer'a girsin
  ve "last" alanlar güncellensin, eski değerlere erişilebilsin; TX'te gönderim anındaki değerler buffer'a
  push'lansın; bazı mesajlar hem RX hem TX olabilir.
- Altyapı test ortamından bağımsız olmalı (pytest, unittest veya kendi altyapısı).
- Yapı sade, katmanlı, maintain edilebilir olmalı; örnekler varsayım eklenmeden, sadece istenenin sade hali olmalı.
- Değişiklikler v2.1-base üzerinde adım adım yapılacak.

---

## 2. Konuşmanın seyri (kısa)

1. **İlk analiz:** Sorun gerçek ama mekanizması "değerlerin ezilmesi" değil: RX tek thread'de çalıştığı için her
   paket sırayla decode edilir, döngü bitince sadece **son** paket objede görünür kalır. Ara değerler semantik olarak
   kaybolur. Çözüm: obje = "son değer görünümü", geçmiş = objenin yanında değişmez kayıtlardan oluşan ring buffer.
2. **Torn read sorusu:** İlk taslakta kilit sadece yazan tarafta vardı; okuyan taraf (`mesaj.speed`) kilitsizdi.
   Bu açıkça kabul edildi. Referans değiştirme (`mesaj.last`) önerildi.
3. **Mutex sorusu:** `__getattribute__`/`__setattr__` override ile mevcut yapıya kilit eklemek mümkün; fakat
   gömülü `FieldType` alanları ve dizilerde okuma kilit dışında kaldığı için yetersiz (§4, B3).
4. **Kod incelemesi (v2.1-base):** `decode`'un `memset(0)` + iki `memmove` ile yazdığı ve ctypes'ın bu çağrılarda
   GIL'i bıraktığı tespit edildi; ölçümle doğrulandı (§4, B1). Mutex yerine **tek kopyalı decode** önerildi.
5. **Son öneri:** tek kopyalı decode + `snapshot()` + mesaj başına history (ring buffer) + `comm.wait_for`,
   ayrıca TX tarafında `pack` düzeltmesi ve GIL koruması.

---

## 3. Temel kavram (tasarım ilkesi)

- **Canlı obje** = son geçerli paketin görünümü. Tek alan okuması her zaman tutarlı olmalı.
- **Snapshot** = tek bir paketin değişmez, bağımsız kopyası. Birden fazla alan birlikte değerlendirilecekse kullanılır.
- **History** = mesaj başına sınırlı sayıda snapshot görüntüsünün (image) sıralı kaydı. Batch içindeki ara
  değerler buradan okunur.
- **CommLogger** her şeyi loglar ve history'den değil event'ten beslenir (history sınırlıdır).

---

## 4. Bulunan açıklar (detaylı)

Her madde: **Nerede**, **Mekanizma**, **Etki**, **Kanıt/doğrulama düzeyi**, **Önerilen düzeltme**.

### 4.1 RX tarafı

#### B1 — `decode` okuyuculara yarım/sıfır durum gösteriyor  *(KRİTİK, ölçüldü)*
- **Nerede:** `asl_testing/message/base.py` → `decode()`
  ```python
  ctypes.memset(address, 0, ctypes.sizeof(self))
  ctypes.memmove(address, raw, body)
  ctypes.memmove(address + offset, raw[body:body + size], size)
  ```
- **Mekanizma:** Yazma üç ayrı adımda yapılıyor. `ctypes.memset`/`memmove` foreign function çağrısıdır ve ctypes
  bu çağrılarda **GIL'i bırakır**. Bu yüzden başka bir thread adımlar arasında, hatta bir adımın ortasında okuyabilir.
  `memset` ile `memmove` arasında tüm alanlar **0** görünür.
- **Etki:** Test thread'i `status.speed` okurken ne eski ne yeni değeri, çoğunlukla 0'ı görebilir. Assert'ler
  rastgele başarısız/başarılı olur; hata yeniden üretilemez görünür.
- **Kanıt:** Repodaki `motor_cmd` ile ölçüldü. Bir thread `speed=100` ve `speed=-100` paketlerini art arda 200.000 kez
  decode etti, diğer thread sürekli `m.speed` okudu:
  - mevcut decode: **11.449.865** tutarsız okuma (ne 100 ne -100)
  - tek kopyalı decode: **0**
  (Okuma sayısı decode sayısından büyük, çünkü okuyucu döngüsü decode sürerken defalarca dönüyor.)
- **Düzeltme:** Paketin son görüntüsü önce geçici bir buffer'da hazırlanır, sonra **tek** `memoryview` atamasıyla
  objeye yazılır. Bu atama foreign function değildir, GIL altında tek bir C işlemi olarak çalışır (§6.2).

#### B2 — Aynı poll içinde gelen birden fazla paketin ara değerleri kayboluyor  *(asıl istek)*
- **Nerede:** `RxPoller.poll_once` → her frame için `dispatcher.dispatch` → `msg.decode`.
- **Mekanizma:** UTS GET buffer'ını boşaltarak döndürdüğü için bir poll'de aynı mesajdan N paket gelebilir. Hepsi
  sırayla aynı objeye yazılır; testin göreceği tek değer sonuncusudur. `has_new()` N sayısını verir ama değerleri vermez.
  Bus aboneleri her paketin `image`'ını alır, fakat testin kendisi için kolay bir erişim yolu yok.
- **Etki:** "speed bir an 10 oldu mu?", "durum A→B→C sırasıyla geçti mi?" gibi kontroller yapılamıyor.
- **Düzeltme:** Mesaj başına history (ring buffer) + `comm.wait_for(msg, predicate, after=mark)` (§6.1, §6.6).

#### B3 — Gömülü `FieldType` alanları ve diziler kilit tabanlı korumayı boşa çıkarır  *(tasarım)*
- **Nerede:** `messageLength`, `messageCounter`, `checksum`, `cmd` (özel tipler) ve `request`, `entries`, `values` (diziler).
- **Mekanizma:** `msg.cmd` aynı belleği paylaşan bir alt obje döndürür; asıl okuma (`.mode`, `.val`, `[3]`) bu
  obje üzerinden **sonra** yapılır. `__getattribute__` ile eklenen bir kilit sadece alt objenin döndürülmesini kapsar.
- **Etki:** Mutex yaklaşımı (§5-a) bu alanlarda koruma sağlamaz. Alt objenin kopya döndürülmesi ise TX yazımlarını
  (`msg.cmd.mode = 2`) kırar.
- **Düzeltme:** B1'deki tek kopyalı yazım ile bellek hiçbir an yarım durumda olmadığından alt obje üzerinden yapılan
  tek okuma da tutarlı olur. Kilit gerekmez.

#### B4 — Canlı objeden çok alanlı okuma tutarlı değil  *(tasarım, beklenen davranış)*
- **Mekanizma:** `if s.speed == 10 and s.mode == 2` iki ayrı okumadır; arada yeni bir paket decode edilebilir.
- **Düzeltme:** `s = msg.snapshot()` ile tek kopya alınıp alanlar oradan okunur (§6.3). Dokümana kural olarak yazılmalı.

#### B5 — `RxState` güncellemesi veriyle atomik değil  *(düşük)*
- **Nerede:** `decode` önce belleği yazar, sonra `RxState.on_receive` `timestamp`, `last_time`, `host_time`, `count`
  alanlarını ayrı ayrı günceller.
- **Etki:** Okuyucu kısa bir an yeni veriyi eski `rx_timestamp` ile, ya da yeni `count`'u eski `timestamp` ile görebilir.
  Zaman aşımı kontrolü ve `rx_age` için genelde zararsız, ama "bu değer hangi zamana ait" sorusunda yanıltıcı.
- **Düzeltme:** Değer + zaman birlikte gerekiyorsa history kaydı kullanılır (kayıt `image` + `timestamp`'i birlikte
  taşır). `RxState` alanları "yaklaşık" bilgi olarak dokümante edilir.

#### B6 — `has_new()` tek ve paylaşılan bir okuma imleci  *(orta)*
- **Nerede:** `RxState.check_new` / `_seen`; `comm.wait_new` bunu kullanıyor.
- **Mekanizma:** `has_new()` sayacı sıfırlar. Testteki iki yardımcı fonksiyon (veya test + simülasyon) aynı mesaj için
  `has_new()` çağırırsa biri diğerinin paketini "tüketir".
- **Düzeltme:** History'de imleç çağırana aittir: `mark = msg.rx_history.mark()` → `since(mark)` / `wait_for(after=mark)`.
  Kimse kimsenin verisini tüketmez. `has_new` geriye uyumluluk için kalabilir.

#### B7 — Batch içindeki frame'lerin zaman damgaları sıralama için yetersiz  *(orta)*
- **Nerede:** `transport.poll`: bir fetch'teki tüm frame'lere aynı `host_time = now`; RS422 splitter ile bir UTS
  öğesinden çıkan frame'ler aynı `item.timestamp`'i paylaşır.
- **Etki:** Zamanla sıralama eşitlikte belirsiz kalır.
- **Düzeltme:** Her kayda dispatcher'ın verdiği **global, monoton `seq`** eklenir; sıra `seq` ile belirlenir.
  UTS'nin döndürdüğü sıranın kronolojik olduğu varsayılıyor (doğrulanmalı, bkz. §9).

#### B8 — `msg.on_receive` callout'u canlı objeyi değiştirebilir  *(düşük, dikkat)*
- **Nerede:** `decode` sonunda callout'lar RX thread'inde canlı obje üzerinde çalışır; dispatcher `image`'ı **callout'lardan
  sonra** `bytes(msg)` ile alır.
- **Etki:** Callout bir alanı değiştirirse event `image`'ı paketin kendisinden farklı olur. History kaydı decode içinde
  alınırsa paket değerini, dispatcher'da alınırsa callout sonrası değeri taşır.
- **Karar önerisi:** History ve event aynı görüntüyü taşısın: **decode'un hazırladığı paket görüntüsü** (callout öncesi).
  `docs/DESIGN.md`'de zaten "`msg.on_receive` kalacak mı" açık konusu var; bu madde oraya bağlanmalı.

### 4.2 TX tarafı

#### B9 — `pack()` checksum ile gönderilen byte'lar arasında yarış  *(YÜKSEK, kod okumasıyla bulundu, ölçülmedi)*
- **Nerede:** `BaseMessageStructure.pack()` → özel alanların `on_send`'i (length, counter, **checksum**) canlı obje
  üzerinde çalışır, ardından `data = bytes(self)` alınır.
- **Mekanizma:** Periyodik mesaj TX thread'inde pack edilirken test thread'i bir alanı yazarsa (ör. `motor.speed = 5`)
  ve bu yazım checksum hesabı ile `bytes(self)` arasına denk gelirse, hattan **yeni değer + eski CRC** gider.
  `TxScheduler._send_lock` sadece iki send'in çakışmasını önler, kullanıcının alan yazmasını kapsamaz.
- **Etki:** Hedef paketi CRC hatasıyla reddeder; aralıklı ve tekrar üretilemeyen hata.
- **Düzeltme:** `pack` tüm özel alan hesaplarını **tek bir kopya** üzerinde yapsın ve hattaki byte'ları o kopyadan
  üretsin (§6.4).

#### B10 — Değişken boylu mesajda `count` ile length/CRC/gövde tutarsızlığı  *(B9'un özel hali)*
- **Nerede:** `LengthType.on_send` → `msg.wire_size()` → `body_size()` (ör. `self.count` okur), sonra checksum,
  sonra `pack` yine `body_size()` çağırır.
- **Mekanizma:** `body_size()` pack içinde birden fazla kez canlı objeden okunur. Arada `count` değişirse length alanı,
  CRC kapsamı ve kesilen gövde birbirini tutmaz.
- **Düzeltme:** §6.4'teki tek kopya yaklaşımı bunu da çözer (tüm hesaplar aynı kopyadan).

#### B11 — `MessageSent.image` ile `raw` farklı olabilir  *(düşük)*
- **Nerede:** `TxScheduler.send`: `raw = msg.pack()` ve ardından ayrıca `image = bytes(msg)`.
- **Etki:** İki okuma arasında yazım olursa log/monitor'daki image gönderilen paketle uyuşmaz.
- **Düzeltme:** `pack` hem wire'ı hem image'ı aynı kopyadan döndürsün (§6.4).

#### B12 — Bilinen: periyodik gönderimde `after_send` yarışı  *(DESIGN.md'de mevcut)*
- Test thread'i istek bitini pack ile `after_send` arasında yazarsa sıfırlama bu değeri siler. §6.4 bu yarışı
  **çözmez**; ayrı bir "bir sonraki gönderimde bir kez" yardımcısı gerekir.

### 4.3 Genel / ortam

#### B13 — Koruma GIL'e bağlı  *(sınırlama)*
- Önerilen tek kopya yaklaşımı GIL'li CPython'da güvenlidir. Free-threaded derlemede (3.13t/3.14t, GIL kapalı)
  `memoryview` ataması ile okuma aynı anda çalışabilir ve garanti kalmaz.
- **Düzeltme:** Import sırasında kontrol edilip açık hata verilsin (§6.7). İleride free-threaded'a geçilirse
  mesaj başına kilit (yazma + snapshot alma) eklenir.

#### B14 — RX ve TX aynı objeyi paylaşan iki yönlü mesajlar  *(tasarım)*
- **Mekanizma:** Aynı obje hem RX hem TX ise, RX decode testin TX için set ettiği alanların üzerine yazar. Bu thread
  güvenliğinden bağımsız, anlamsal bir çakışma.
- **Durum:** Karar bekliyor (§9). Seçenekler: (a) iki yönlü mesajda RX değerlerini sadece history/snapshot'tan okumak,
  canlı objeyi TX'e bırakmak; (b) RX ve TX için ayrı obje; (c) mevcut haliyle bırakıp dokümante etmek.

#### B15 — `snapshot()` ile üretilen objenin metadata'sı yok  *(düşük)*
- `from_buffer_copy` `__init__` çağırmaz: snapshot objede `_channel`, `_rx`, `_tx`, `_signature_id` yoktur.
  `snap.channel` veya `snap.rx_timestamp` `AttributeError` verir.
- **Düzeltme:** Snapshot sadece alan değerleri için kullanılmalı; zaman ve kanal bilgisi kayıttan (`Record`) okunur.
  Gerekirse `snapshot()` minimal metadata'yı kopyalayan bir yardımcı ile genişletilir. Dokümante edilmeli.

#### Referans: DESIGN.md'de zaten kayıtlı ilgili açıklar
- Değişken boyda length alanı checksum boyundan küçük gelirse `ChecksumType.on_receive` negatif ofsetle
  `ValueError` fırlatıyor, yakalanmadığı için **RxPoller thread'i ölüyor**. History eklendiğinde bu daha görünür olur;
  öncelikli düzeltilmeli (DESIGN.md'deki 4 maddelik öneri).
- Paket sonundaki fazla baytlar şu an kabul ediliyor (`validate` sadece `len(raw) < size` kontrol ediyor).

---

## 5. Değerlendirilen alternatifler

| Seçenek | Açıklama | Sonuç |
|---|---|---|
| a) Mesaj başına mutex | `__getattribute__`/`__setattr__` override, decode kilit altında, çok alan için `with msg:` | **Reddedildi.** B3 nedeniyle özel alan/dizi okumalarını korumuyor; okuyanın kilit kullanmasını gerektiriyor (unutulur). |
| b) Referans değiştirme (`msg.last`) | Her paket için yeni obje oluştur, referansı atomik değiştir | **Seçilmedi.** API'yi ikiye ayırıyor (`msg.last.speed` vs `msg.speed`); kullanıcı `msg.speed` ile doğrudan erişim istiyor. |
| c) **Tek kopyalı yazım + snapshot + history** | Bellek tek atamayla yazılır; çok alan için snapshot; ara değerler history'de | **Önerilen.** Kilit yok, mevcut API aynı kalıyor, ölçümle doğrulandı. |
| d) Descriptor tabanlı alan tipleri | Alanlar ctypes `_fields_` yerine kendi descriptor'larıyla; tüm erişim tek noktadan | **İleride.** Erişim noktası tek olduğu için kilit/snapshot yönlendirmesi doğal yerleşir; ama büyük bir değişiklik ve başka session'daki tasarıma bağlı (§8). |

---

## 6. Önerilen tasarım (taslak kod)

> Kodlar taslaktır; uygulanırken mevcut testlerle doğrulanmalıdır.

### 6.1 Yeni dosya: `asl_testing/message/history.py`

```python
"""Bounded history of message images (ring buffer).

A record holds one packet as the ctypes layout of the message (image), so any field can be read later
with snapshot(). Records never change. Readers keep their own position (seq), nobody consumes data.
"""
import itertools
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

_seq = itertools.count(1)               # global, monotonic; next() is atomic under the GIL


def next_seq() -> int:
    return next(_seq)


@dataclass(frozen=True, slots=True)
class Record:
    seq: int                            # global order (ties in timestamp are resolved by seq)
    timestamp: Optional[float]          # UTS time (RX) or None (TX)
    host_time: float                    # wall clock of this host (time.time)
    image: bytes                        # ctypes layout of the message
    cls: type                           # message class, to decode the image

    def snapshot(self):
        """A separate, unregistered object holding the values of this packet."""
        return self.cls.from_buffer_copy(self.image)


class MessageHistory:
    def __init__(self, capacity: int):
        self._buf: deque[Record] = deque(maxlen=capacity)
        self._cond = threading.Condition()
        self.dropped = 0                # records pushed out by newer ones

    def push(self, record: Record) -> None:
        with self._cond:
            if len(self._buf) == self._buf.maxlen:
                self.dropped += 1
            self._buf.append(record)
            self._cond.notify_all()

    def mark(self) -> int:
        """Position to wait or read from: only records after it count."""
        with self._cond:
            return self._buf[-1].seq if self._buf else 0

    def since(self, seq: int) -> list[Record]:
        with self._cond:
            return [r for r in self._buf if r.seq > seq]

    def last(self) -> Optional[Record]:
        with self._cond:
            return self._buf[-1] if self._buf else None

    def wait_for(self, predicate: Callable[[object], bool], after: int, timeout: float) -> Optional[Record]:
        """First record after `after` whose snapshot satisfies predicate; None on timeout."""
        found: list[Record] = []

        def check() -> bool:
            for r in self._buf:
                if r.seq > after and predicate(r.snapshot()):
                    found.append(r)
                    return True
            return False

        with self._cond:
            self._cond.wait_for(check, timeout)
        return found[0] if found else None

    def clear(self) -> None:
        with self._cond:
            self._buf.clear()
            self.dropped = 0
```

Notlar:
- `wait_for` polling yapmaz; `Condition` ile yeni kayıt geldiğinde uyanır (mevcut `_wait` 5 ms uyuyarak poll ediyor).
- Predicate snapshot üzerinde çalışır, bu yüzden alan adlarıyla yazılır: `lambda s: s.speed == 10`.
- Taşma sessiz değildir: `dropped`. Teardown'da `dropped > 0` ise uyarı verilmesi önerilir.

### 6.2 `base.py` → tek kopyalı `decode`

```python
def decode(self, raw: bytes, timestamp: Optional[float] = None) -> bool:
    if not self.validate(raw):
        if self._rx is not None:
            self._rx.on_error()
        return False
    body, offset, size = self._rx_body(raw), self._trailer_offset(), self._trailer_size()
    image = bytearray(ctypes.sizeof(self))             # unused part of a variable-size message stays zero
    image[:body] = raw[:body]
    image[offset:offset + size] = raw[body:body + size]
    memoryview(self).cast("B")[:] = image              # one copy under the GIL: readers see old or new, never half
    image = bytes(image)
    if self._rx is not None:
        self._rx.on_receive(timestamp)
        self._rx.history.push(Record(next_seq(), timestamp, time.time(), image, type(self)))
    self._last_rx_image = image                        # dispatcher puts this into MessageReceived
    for callout in self._on_receive:
        callout(self)
    return True
```

- `memoryview(...).cast("B")` little-endian, **big-endian** ve **bitfield** içeren yapılarda test edildi; doğru yazıyor.
- `ctypes.memset`/`memmove` artık kullanılmıyor.

### 6.3 `base.py` → `snapshot()` ve history erişimi

```python
def snapshot(self):
    """A consistent copy of the current values (one copy under the GIL). Not registered."""
    return type(self).from_buffer_copy(bytes(self))

@property
def rx_history(self) -> Optional[MessageHistory]:
    return self._rx.history if self._rx is not None else None

@property
def tx_history(self) -> Optional[MessageHistory]:
    return self._tx.history if self._tx is not None else None
```

Kapasite: sınıf ayarı `_history: ClassVar[int] = 64` (proje/aile/mesaj sınıfında override edilebilir) ve
`__init__`'te isteğe bağlı `history=` parametresi. Boyutlandırma için kaba kural:
`frekans × en uzun poll aralığı × 4–5` (ör. 100 Hz, 200 ms → 20 → 64 yeterli).

### 6.4 `base.py` → tutarlı `pack` (B9, B10, B11)

Fikir: kullanıcı callout'ları canlı objede çalışır; ardından **tek kopya** alınır, length/counter/checksum o kopya
üzerinde hesaplanır, hattaki byte'lar ve image o kopyadan üretilir, özel alanların yeni değerleri canlı objeye geri yazılır.

```python
def pack(self) -> bytes:
    for callout in self._on_send:
        callout(self)
    snap = self.snapshot()                             # one consistent copy of the user's values
    for field in snap._special_fields():
        field.on_send(snap)                            # length, counter, checksum computed on the copy
    image = bytes(snap)
    self._write_special_fields(image)                  # counter/length/checksum persist on the live object
    self._last_tx_image = image
    return image[:snap.body_size()] + image[snap._trailer_offset():]
```

- `_write_special_fields(image)`: her özel alanın byte aralığını `memoryview(self).cast("B")[a:b] = image[a:b]` ile yazar.
- Dikkat: snapshot objede `__init__` çalışmadığı için (B15) hook'lar ve `body_size()` override'ları instance
  metadata'sına (`_channel`, `_rx` …) dokunmamalı. Mevcut hook'lar dokunmuyor; kural olarak dokümante edilmeli.
- `TxScheduler.send` `image = bytes(msg)` yerine `msg._last_tx_image` kullanır ve `tx_history`'ye kayıt push eder.
- B12 (`after_send` yarışı) bu değişiklikle çözülmez.

### 6.5 `dispatcher.py`

`MessageReceived(msg, frame.data, frame.host_time, bytes(msg), frame.timestamp)` →
`bytes(msg)` yerine `msg._last_rx_image`. Böylece event, history ve canlı obje aynı paket görüntüsünü taşır (B8).

### 6.6 `comm.py` → `wait_for`

```python
def wait_for(self, msg, predicate, timeout: float = 1.0, after: Optional[int] = None):
    """Waits for a received packet of msg whose values satisfy predicate.

    after: a position from msg.rx_history.mark(); by default only packets from now on count.
    Returns the Record (record.snapshot() gives the values) or None on timeout.
    """
    history = msg.rx_history
    start = history.mark() if after is None else after
    return history.wait_for(predicate, start, timeout)
```

### 6.7 GIL koruması (`asl_testing/__init__.py`)

```python
import sys

if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled():
    raise RuntimeError("asl_testing relies on the GIL for consistent message reads; "
                       "run on a standard (GIL-enabled) CPython build")
```

### 6.8 Test yazan için kullanım

```python
status.speed                                   # single field from the live object: safe

s = status.snapshot()                          # several fields from the same packet
assert s.speed == 10 and s.cmd.mode == 2

mark = status.rx_history.mark()                # older packets are not the answer
comm.send(request)
rec = comm.wait_for(status, lambda s: s.speed == 10, timeout=1.0, after=mark)
assert rec is not None                         # also true if speed was 10 only in the middle of a batch

for r in status.rx_history.since(mark):        # every packet since mark, in order
    print(r.seq, r.timestamp, r.snapshot().speed)

assert status.rx_history.dropped == 0          # capacity was enough
```

---

## 7. Dosya değişiklik planı

| Dosya | Tür | Değişiklik |
|---|---|---|
| `asl_testing/message/history.py` | **yeni** | `Record`, `MessageHistory`, `next_seq` (~70 satır) |
| `asl_testing/message/base.py` | değişir | tek kopyalı `decode`, `snapshot()`, `rx_history`/`tx_history`, `_history` ayarı ve `history=` parametresi, tutarlı `pack`, `_write_special_fields` |
| `asl_testing/message/state.py` | değişir | `RxState`/`TxState` içine `history: MessageHistory` |
| `asl_testing/runtime/dispatcher.py` | değişir | event image'ı `msg._last_rx_image`'dan |
| `asl_testing/runtime/tx.py` | değişir | image `msg._last_tx_image`'dan, `tx_history` push |
| `asl_testing/comm.py` | değişir | `wait_for` |
| `asl_testing/__init__.py` | değişir | `MessageHistory`, `Record` export, GIL kontrolü |
| `tests/test_history.py` | **yeni** | §8'deki testler |
| `docs/DESIGN.md`, `docs/TEST_API.md` | değişir | thread modeli, snapshot kuralı, history API, bu dosyadaki açıklar |

Mesaj tanımları, proje dosyaları (`projects/…`), channel ve UTS katmanı **değişmiyor**.

---

## 8. Test planı

1. **Torn read testi (B1):** iki paket arasında 100k+ decode, paralel okuyucu; tutarsız okuma sayısı 0 olmalı.
   (Bu session'da kullanılan betik: yazıcı `A`/`B` paketlerini sırayla decode eder, okuyucu `m.speed`'in sadece
   `100` veya `-100` olduğunu kontrol eder.)
2. **Batch testi (B2):** fake UTS tek fetch'te aynı mesajdan 5 paket döndürsün; history'de 5 kayıt, doğru sıra,
   `wait_for` ortadaki değeri bulmalı.
3. **Taşma:** kapasiteden fazla paket → en eskiler düşer, `dropped` doğru.
4. **İmleç:** iki bağımsız `mark` ile okuyan iki tüketici birbirinin verisini kaybetmemeli.
5. **Endian/bitfield:** big-endian ve bitfield'lı mesajda decode + snapshot doğru.
6. **Değişken boy:** kullanılmayan bölge sıfır, CRC alanı doğru yerde.
7. **TX tutarlılığı (B9):** periyodik gönderim sürerken test thread'i alanları sürekli değiştirsin; gönderilen her
   paketin CRC'si kendi gövdesiyle uyuşmalı ve `MessageSent.image` `raw` ile tutarlı olmalı.
8. **Yeniden oluşturma:** aynı mesaj yeniden oluşturulunca history boş başlamalı (bkz. §9 karar).
9. **GIL kontrolü:** `_is_gil_enabled` False döndüğünde import hata vermeli (monkeypatch ile).

---

## 9. Açık kararlar / doğrulanması gerekenler

1. **History sahipliği:** Obje yeniden oluşturulunca history sıfırlansın mı (önerilen: evet, obje durumunda tutulur,
   testcase'ler temiz başlar) yoksa registry slotunda kalıcı mı tutulsun?
2. **Varsayılan kapasite** (öneri 64) ve proje/mesaj bazında override biçimi.
3. **İki yönlü mesajlar (B14):** canlı objeyi kim kullanacak?
4. **`msg.on_receive` callout'u (B8):** kalacak mı; kalırsa canlı objeyi değiştirmesine izin var mı?
5. **UTS sırası:** GET'in döndürdüğü liste kronolojik mi? Timestamp birimi? (`seq` buna dayanıyor.)
6. **`has_new` / `wait_new`:** history geldikten sonra kalacak mı, `wait_for` ile mi değiştirilecek?
7. **Taşma politikası:** sadece sayaç mı, yoksa log/olay (`HistoryOverflow`) da üretilsin mi?
8. **TX history:** her periyodik gönderim kaydedilsin mi (yüksek frekansta kapasiteyi hızla doldurur)?
9. **Free-threaded Python:** desteklenecekse kilit tasarımı ayrıca yapılmalı.

---

## 10. Field type alternatifi hakkında

Kullanıcı başka bir session'da `FieldType`'a alternatif bir alan tipi yapısı konuştuğunu belirtti. O yapı bu
session'da görülemedi (repo dallarında da yok). Değerlendirme için gereken:

- O yapı alanları **descriptor** ile tanımlıyorsa (her erişim tek bir `__get__`/`__set__` noktasından geçiyorsa):
  kilit veya snapshot yönlendirmesi oraya doğal yerleşir, alt obje (view) sorunu (B3) ortadan kalkar, bit-wise/ASCII/
  endian dönüşümleri de aynı noktada yönetilir. Bu durumda tek kopyalı decode yine geçerli kalır.
- Bu session'daki öneri (§6) mevcut `FieldType` yapısıyla çalışır ve o alternatife geçişi engellemez.

Yeni session'da o yapının kodu paylaşılarak §6 ile uyumu değerlendirilmeli.

---

## 11. Yeni session için başlangıç

1. `smlbysl/TestingInfrastructureASL` reposunu `v2.1-base` dalında aç.
2. Bu dosyayı ve `docs/DESIGN.md` → "Thread modeli" ve "Açık konular" bölümlerini oku.
3. §9'daki kararları kullanıcıyla netleştir (özellikle 1, 3, 4).
4. Önce B1 (tek kopyalı decode) + testini uygula; sonra history (§6.1–6.6); sonra TX düzeltmesi (§6.4);
   en son GIL kontrolü ve dokümantasyon.
5. DESIGN.md'deki RxPoller'ı öldüren length hatasını history'den önce düzeltmek önerilir.
