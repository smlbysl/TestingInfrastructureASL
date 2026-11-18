---
name: asl-test-migration
description: Mevcut proje ve test dosyalarını asl_testing altyapısına uyarlar; her referans test için bir unittest ve bir pytest dosyası üretir, test başındaki attribute bloklarını aynen korur.
---

# asl_testing test ve proje uyarlama

Bu skill, eski yapıyla yazılmış proje tanımlarını (mesajlar, header, CRC, kanallar) ve testleri
`asl_testing` altyapısına uyarlar. Her referans test dosyası için **iki dosya** üretir: biri `unittest`,
biri `pytest`. Test mantığı, test adları ve her testin başındaki attribute bloğu (gereksinim, açıklama,
yorum vb.) **değişmeden** korunur.

## 0. Önce oku (her oturumda)

Altyapıyı tahmin etme; şu dosyaları oku ve oradaki API'yi kullan:

| Dosya | Neden |
|---|---|
| `docs/USAGE.md` | Kullanım: gönderme, bekleme, geçmiş, olaylar, simülasyon, kanallar, endian |
| `docs/TEST_API.md` | Bütün API'nin tablosu |
| `tests/base.py` | `CommTestCase`, `HardwareTestCase`, `open_comm`, yardımcılar (`send`, `start`, `expect_new`, `expect_sent`, `device_sends`) |
| `tests/conftest.py` | pytest fixture'ları (`adapter`, `comm`, `timeout`), `hardware` marker'ı |
| `tests/settings.py` | `PROJECTS`, `make_adapter()` |
| `projects/example_project/*.py` | Proje dosyalarının hedef biçimi |
| `tests/test_comm.py` | Örnek test yazımı |

Kullanıcının verdiği şunları da oku:
- **Referans testler:** dönüştürülecek test dosyaları.
- **Kullanıcının test base'i:** `setUp` / `tearDown` vb. metodları olan sınıf. Adı ve yeri kullanıcıdan alınır.
- **Eski proje dosyaları:** mesaj tanımları, header / footer, CRC, kanal / protokol bilgisi.

Bir şey belirsizse tahmin etme; listeye yaz ve kullanıcıya sor (bkz. adım 1).

## 1. Envanter ve eşleme raporu (dosya yazmadan önce)

Önce hiçbir dosya yazma. Şu raporu çıkar ve kullanıcının onayını bekle:

1. **Referans test listesi:** dosya → sınıflar → test metodları (sırasıyla), her testin attribute bloğu
   (biçimiyle birlikte: decorator, docstring, yorum bloğu, sınıf özniteliği, sözlük...).
2. **Kullanıcının test base'i:** metodları, `setUp` / `tearDown` içinde ne yapıldığı, testlerin ondan
   kullandığı yardımcılar.
3. **Eski proje → yeni proje eşlemesi** (bölüm 3'teki tablo): her eski sınıf / kavram için yeni karşılığı.
4. **Eski test API'si → yeni API eşlemesi** (bölüm 4'teki tablo): testlerde kullanılan her eski çağrı.
5. **Eşleşmeyenler:** karşılığı bulunamayan her şey, nedeniyle birlikte.
6. **Sorular:** kullanıcıya sorulacaklar.

## 2. Çıktılar ve dosya düzeni

```
projects/<proje>/                 # uyarlanmış proje (bölüm 3)
    __init__.py  settings.py  types.py  framing.py  header.py  channels.py  messages.py
tests/
    support/
        <proje>_base.py           # kullanıcının test base'i + CommTestCase birleşimi (unittest)
        <proje>_fixtures.py       # aynı hazırlık pytest fixture'ları olarak
    unittest_suite/
        __init__.py
        test_<referans>.py        # her referans için unittest dosyası
    pytest_suite/
        __init__.py
        conftest.py               # <proje>_fixtures'ı yükler
        test_<referans>.py        # her referans için pytest dosyası
MIGRATION_REPORT.md               # bölüm 7
```

- Her referans dosya için **tam olarak iki** dosya: `tests/unittest_suite/test_<ad>.py` ve
  `tests/pytest_suite/test_<ad>.py`. `<ad>`, referans dosyanın adından gelir.
- İki klasör ayrı koşulur; unittest sınıfları pytest altında da koştuğu için aynı testler iki kez sayılmaz:
  ```
  python -m unittest discover -s tests/unittest_suite -t .
  python -m pytest tests/pytest_suite
  ```
  `pytest.ini` içindeki `testpaths` buna göre güncellenir (`tests` + `tests/pytest_suite` ayrımı,
  `tests/unittest_suite` hariç tutulur: `--ignore=tests/unittest_suite` ya da `norecursedirs`).
- `tests/settings.py` içindeki `PROJECTS` uyarlanan projeyi gösterir.

## 3. Proje dosyalarını uyarlama

### Hedef yapı (örnek: `projects/example_project/`)

| Dosya | İçerik |
|---|---|
| `settings.py` | `ENDIAN = "little"` ya da `"big"`: projenin bayt sırası, tek yer |
| `types.py` | Özel alanlar: `class Length16(LengthType, endian=ENDIAN)`, `class Counter8(CounterType, endian=ENDIAN)`, `class CRC16(ChecksumType, endian=ENDIAN)` + `compute()`, `AsciiType`, bit alanlı `FieldType` (`on_init`, `after_send`) |
| `framing.py` | Gerekirse mesajın dışındaki zarf (`Envelope`: `on_send`, `on_receive`, `offset`) |
| `channels.py` | `class XChannels(ChannelSet)`: `Rs422Channel(n)`, `EthernetChannel(n, Framing(...))`, `Mil1553Channel(n, byte_order=...)`; bir kanal = bir UTS interface'i |
| `header.py` | `class ProjectBase(BaseMessageStructure, endian=ENDIAN)`: ortak header alanları, `_channel`, `_direction`, `_timing`, `__init__`; aileler: `_signature = Signature("alan1", "alan2")` ya da `_signature = None` (kanala göre bulunur) |
| `messages.py` | Mesaj sınıfları: `_fields_` (CRC en sonda), `_defaults`, gerekirse `_direction`, `_channel`, `_variable_size` + `body_size()`, `_history` |

### Kurallar

- **Bayt düzeni birebir korunur.** Her mesajın alan sırası, tipi, bit genişliği ve toplam boyu eski
  tanımla aynı olmalı. Doğrulama: aynı değerlerle eski ve yeni nesnenin `bytes(...)` çıktısı aynı (bölüm 6).
- **Endian sadece `settings.py` → `ENDIAN`**; proje sınıfı ve bütün özel tipler `endian=ENDIAN` alır.
  `BigEndianStructure` / `LittleEndianStructure` tabanı yazılmaz (`metaclass conflict` verir).
- **Bir bit grubu tek tiple yazılır** (ör. hepsi `c_uint8`); karışık tip Python sürümüne göre farklı yerleşir.
- **CRC her mesajın son alanıdır** (header'da değil). Algoritma `ChecksumType.compute()` içinde.
- **Length** header + gövde + CRC toplamıdır; **Counter** her gönderimde artar. İkisi de elle hesaplanmaz.
- **1553:** her alan 16 bit sınırında; `Mil1553Channel(..., byte_order=...)` `ENDIAN` ile aynı.
- **Kimlik (signature):** paketi tanıyan alanlar ailenin `Signature(...)`'ına yazılır; değerleri mesaj
  nesnesi oluşturulurken verilir (ör. `ProjectBase.__init__` parametreleri).
- Eşleşmeyen bir eski davranış varsa sessizce atlama: `# TODO(migration): ...` ve rapora yaz.

### Eski yapı → yeni yapı (genel eşleme; eski projeye göre düzelt)

| Eski kavram (ör. v1) | Yeni karşılık |
|---|---|
| `BaseMessage` + `BaseHeader` / `BaseFooter` | `ProjectBase(BaseMessageStructure, endian=ENDIAN)` + aileler; footer'daki CRC mesajın son alanı |
| `Header1` (header alanları) | `ProjectBase._fields_` |
| `CRC16` (footer / checksum sınıfı) | `types.py` → `class CRC16(ChecksumType, endian=ENDIAN)` + `compute()` |
| Length / counter alanının header'daki yeri | `LengthType` / `CounterType` alt sınıfı, header alanının tipi olarak |
| `MessageMetadata(protocol, interface, direction, periodic, period_ms)` | `_channel = XChannels.Y`, `_direction = Direction.TX/RX`, `_timing = Timing(period_s)` (ms → s) |
| `@message(...)` decorator ile verilen header değerleri | `ProjectBase.__init__` parametreleri ya da `_defaults` |
| Signature (offset + mask) | Ailede `Signature("alan", ...)` |
| Protokol / interface numarası | `channels.py` içinde kanal; mesaja `_channel` ile |
| Endian seçimi | `settings.py` → `ENDIAN` |

## 4. Testleri uyarlama

### Değişmezler (en önemli kurallar)

1. **Attribute bloğu aynen korunur.** Her testin başındaki blok (decorator, docstring, yorum, sözlük,
   sınıf özniteliği — biçimi ne ise) karakter karakter aynı kalır: aynı alanlar, aynı sıra, aynı metin,
   aynı yer (testin hemen üstü / ilk satırı). İki çıktı dosyasında da aynı.
2. **Test adları, sırası ve sayısı korunur.** Hiçbir test silinmez, birleştirilmez, bölünmez.
3. **Beklenen değerler, toleranslar, süreler, adım sırası değişmez.** Sadece çağrı biçimi değişir.
4. **Yorumlar korunur.** Testin içindeki adım yorumları yerinde kalır.
5. **Dönüştürülemeyen test silinmez:** `@unittest.skip("migration: <neden>")` /
   `@pytest.mark.skip(reason="migration: <neden>")` + `# TODO(migration): ...` + rapora yazılır.
6. **Testte UTS adı geçmez.** Sadece `comm` / mesaj nesneleri / yardımcılar kullanılır.

### Kullanıcının test base'i

- **unittest:** kullanıcının base'i değiştirilmez. `tests/support/<proje>_base.py` içinde ikisini birleştiren
  bir sınıf yazılır:
  ```python
  class ProjectTestCase(UserTestBase, CommTestCase):
      """User's TestBase on top of CommTestCase: opened Comm in self.comm, adapter in self.adapter."""
  ```
  - Kullanıcının `setUp` / `tearDown`'ı `super().setUp()` / `super().tearDown()` çağırmıyorsa sıra elle
    kurulur: önce `CommTestCase.setUp(self)`, sonra kullanıcının `setUp`'ı; `tearDown`'da tersi.
    Comm'un kapanması `addCleanup` ile zaten garanti.
  - Kullanıcı base'inin yardımcı metodları aynen kullanılabilir kalır.
- **pytest:** aynı hazırlık `tests/support/<proje>_fixtures.py` içinde fixture olur:
  ```python
  @pytest.fixture
  def case(comm, adapter):
      """Same preparation as ProjectTestCase.setUp / tearDown, for pytest tests."""
      ctx = UserContext(comm, adapter)        # user's setUp steps
      yield ctx
      ctx.teardown()                          # user's tearDown steps
  ```
  Kullanıcı base'i `unittest.TestCase`'e bağlı yardımcılar (`self.assertX`) içeriyorsa pytest tarafında
  düz `assert` kullanılır; yardımcının davranışı aynı kalmalı.

### Sınıf yapısı

- **unittest dosyası:** referanstaki sınıf ve metod yapısı birebir; taban `ProjectTestCase`
  (donanım gerektiren testler `HardwareTestCase` tabanlı birleşimden).
- **pytest dosyası:** aynı sınıf adları, **düz sınıf** (`class TestX:`, `unittest.TestCase`'ten türemez),
  aynı metod adları; hazırlık fixture'dan gelir:
  ```python
  class TestMotor:
      <ATTRIBUTE BLOCK — referanstan aynen>
      def test_start_request(self, case, comm):
          ...
  ```
  pytest sınıf adlarının `Test` ile başlaması gerekir. Referans sınıf adı `Test` ile başlamıyorsa pytest
  dosyasında `Test<RefAdı>` kullanılır ve raporda belirtilir; metod adları değişmez (`test_` ile başlamıyorsa
  `pytest.ini`'ye `python_functions` eklenir, ad değiştirilmez).
- Attribute bloğu bir decorator ise ve `unittest.TestCase`'e bağımlıysa pytest tarafında çalışıp çalışmadığı
  kontrol edilir; çalışmıyorsa `tests/support/` içine aynı imzalı ince bir uyarlama yazılır, blok metni yine
  değişmez.

### Eski test API'si → yeni API

| İş | unittest (`self` = ProjectTestCase) | pytest |
|---|---|---|
| Mesaj nesnesi | testin ya da `setUp`'ın içinde oluşturulur (modül seviyesinde değil; her test registry'yi temizler) | testin ya da fixture'ın içinde |
| Bir kez gönder | `self.send(msg)` (başarısızsa test düşer) | `assert comm.send(msg)` |
| Periyodik gönder | `self.start(msg)` (test bitince durur) | `comm.start(msg)` + test sonunda `comm.stop(msg)` (ya da fixture) |
| Periyodik durdur | `self.comm.stop(msg)` | `comm.stop(msg)` |
| Yeni paket bekle | `self.expect_new(msg, timeout)` | `assert comm.wait_new(msg, timeout=t) > 0` |
| Gönderimi bekle | `self.expect_sent(msg, timeout)` | `assert comm.wait_sent(msg, timeout=t) > 0` |
| Koşul gerçekleşene kadar bekle | `rec = self.comm.wait_for(msg, lambda m: ..., timeout=t, after=mark)` | aynı, `comm.` ile |
| İstekten önce işaret | `mark = msg.rx_history.mark()` | aynı |
| Bulunan paketin değerleri | `rec.snapshot().alan` | aynı |
| Son değer | `msg.alan` ya da `msg.rx_history.last()` | aynı |
| Birlikte yazılacak alanlar | `with msg.locked_update(): ...` | aynı |
| Olay dinleme | `self.comm.subscribe(EventType, handler)` | `comm.subscribe(...)` |
| Cihazı taklit (sadece simülasyon) | `self.device_sends(msg)` | `adapter.inject(ch, ch.framing.envelope.on_send(msg.pack()))` |
| Donanımda koşan test | `HardwareTestCase` tabanı | `@pytest.mark.hardware` |
| Yön / periyot | `msg(..., direction=Direction.TX, tx=Timing(0.02))`, `rx=Timing(p, tolerance=n)` | aynı |

- `time.sleep` ile "cevap gelmiştir" diye beklemek yerine `expect_new` / `wait_for` kullanılır; ama
  referans testte bilinçli bir bekleme süresi varsa (ör. "5 s boyunca gönderilmemeli") korunur.
- Bir referans çağrının karşılığı yoksa tahmin etme: skip + TODO + rapor.

### Dosya kuralları

- Her dosyanın başında modül docstring'i ve `__author__ = "İsmail Baysal"`.
- Kod içi yorumlar İngilizce, sade (PEP 257). Docstring'ler kısa ve açıklayıcı.
- Import'lar: `asl_testing` (public API), `projects.<proje>...`, `tests.support...`, `tests.settings`.

## 5. Şablonlar

### unittest: `tests/unittest_suite/test_<ad>.py`

```python
"""<Referans dosyanın açıklaması>. Migrated from <referans yolu>."""

__author__ = "İsmail Baysal"

import unittest

from asl_testing import Direction, Timing
from projects.<proje>.messages import motor_cmd, motor_status
from tests.settings import DEST, SRC
from tests.support.<proje>_base import ProjectTestCase


class MotorTests(ProjectTestCase):
    <ATTRIBUTE BLOCK — referanstan aynen>
    def test_start_request(self):
        status = motor_status(DEST, SRC, 0x31, rx=Timing(0.05, tolerance=2))
        cmd = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        mark = status.rx_history.mark()
        with cmd.locked_update():
            cmd.cmd.startReq = 1
        self.start(cmd)
        rec = self.comm.wait_for(status, lambda s: s.running == 1, timeout=1.0, after=mark)
        self.assertIsNotNone(rec, "motor did not start")


if __name__ == "__main__":
    unittest.main()
```

### pytest: `tests/pytest_suite/test_<ad>.py`

```python
"""<Referans dosyanın açıklaması>. Migrated from <referans yolu>."""

__author__ = "İsmail Baysal"

from asl_testing import Direction, Timing
from projects.<proje>.messages import motor_cmd, motor_status
from tests.settings import DEST, SRC


class TestMotorTests:
    <ATTRIBUTE BLOCK — referanstan aynen>
    def test_start_request(self, case, comm):
        status = motor_status(DEST, SRC, 0x31, rx=Timing(0.05, tolerance=2))
        cmd = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        mark = status.rx_history.mark()
        with cmd.locked_update():
            cmd.cmd.startReq = 1
        comm.start(cmd)
        try:
            rec = comm.wait_for(status, lambda s: s.running == 1, timeout=1.0, after=mark)
            assert rec is not None, "motor did not start"
        finally:
            comm.stop(cmd)
```

## 6. Doğrulama (rapordan önce, hepsi yapılır)

1. **Import:** bütün yeni modüller hatasız import edilir.
2. **Bayt düzeni:** her mesaj için eski ve yeni tanımdan aynı değerlerle oluşturulan nesnelerin baytları
   karşılaştırılır (CRC / sayaç / length dahil). Eski kod çalıştırılamıyorsa en az boy (`ctypes.sizeof`) ve
   alan ofsetleri karşılaştırılır.
3. **Koşum:** iki takım da simülasyonda (`FakeUtsAdapter`) koşulur:
   ```
   python -m unittest discover -s tests/unittest_suite -t .
   python -m pytest tests/pytest_suite
   ```
   Simülasyonda cevap veren bir cihaz yoksa RX bekleyen testler zaman aşımına düşer; bu beklenen bir
   durumdur, rapora yazılır. Hata (import, attribute, tip) olmamalı.
4. **Test sayısı:** her referans dosya için referans, unittest ve pytest dosyalarında aynı sayıda ve aynı
   adlarda test var.
5. **Attribute blokları:** her testin bloğu referans, unittest ve pytest dosyalarında birebir aynı.
   Bunu bir script ile kontrol et (`ast` ile her test metodunun decorator listesi ve docstring'i; yorum
   bloğu ise metod tanımından önceki ardışık yorum satırları) ve sonucu rapora yaz.
6. **Mevcut testler:** repodaki `tests/` altındaki altyapı testleri hâlâ geçiyor
   (`python -m unittest discover -s tests -t .` — `unittest_suite` / `pytest_suite` hariç).

## 7. Rapor: `MIGRATION_REPORT.md`

- Uyarlanan proje dosyaları ve eski → yeni eşleme tablosu.
- Her referans dosya: üretilen iki dosya, test sayıları (referans / unittest / pytest), attribute kontrolü sonucu.
- Skip edilen testler ve TODO'lar, nedenleriyle.
- Bayt düzeni karşılaştırma sonucu (mesaj başına).
- Koşum sonuçları (iki takım), beklenen zaman aşımları ayrı.
- Kullanıcıya açık sorular.

## Çalışma biçimi

- Büyük işler için sırayla: önce proje dosyaları (bölüm 3) ve doğrulaması, sonra testler **dosya dosya**.
  Her referans dosyadan sonra o dosyanın iki çıktısını doğrula, sonra sıradakine geç.
- Altyapının kendisini (`asl_testing/`) değiştirme. Gerekli görünen bir değişiklik varsa öneri olarak rapora yaz.
- Kullanıcının referans testlerini ve test base'ini değiştirme; onlar sadece okunur.
