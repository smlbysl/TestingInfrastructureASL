# Bilinen sorunlar

Bütün bilinen açıklar tek listede. Her madde: önem, durum, nerede, ne oluyor, önerilen düzeltme.
Ayrıntılı analiz için kaynak belgeler:
- `docs/RX_HISTORY_HANDOFF.md` (B1–B15: thread güvenliği, mesaj geçmişi, TX tutarlılığı)
- `docs/DESIGN.md` → "Açık konular" (tasarım gereği esnek bırakılanlar)

Önem: **Kritik** (veri kaybı / thread ölümü / yanlış veri hatta), **Yüksek**, **Orta**, **Düşük**.
Durum: **Açık**, **Karar bekliyor**, **Doğrulandı** (ölçümle ya da testle gösterildi), **Çözüldü**.

---

## Öncelik sırası (önerilen)

1. ~~K1: Uzunluk alanı RX thread'ini öldürüyor~~ (çözüldü)
2. ~~B1: `decode` okuyuculara yarım değer gösteriyor~~ (çözüldü)
3. K3: Özel alan tipleri projenin endian'ını takip etmiyor (çözüm tasarlandı, karar bekliyor)
4. B9–B11: `pack()` ile gönderilen baytlar tutarsız olabiliyor
5. B2, B6: Mesaj geçmişi (ring buffer) ve çağırana ait imleç
6. B13: GIL kontrolü

---

## RX doğrulama

### K1 — Değişken boyda küçük uzunluk değeri RX thread'ini öldürüyordu
- **Önem:** Kritik — **Durum:** Çözüldü
- **Nerede:** `LengthType.on_receive` (`asl_testing/message/fields.py`), `validate()` (`message/base.py`),
  `RxPoller.poll_once()` (`runtime/rx.py`)
- **Ne oluyordu:** Uzunluk alanı checksum boyundan küçükse (0 veya 1) `_rx_body` negatif dönüyordu,
  `from_buffer_copy(raw, negatif)` `ValueError` fırlatıyordu. İstisna yakalanmadığı için RxPoller thread'i ölüyordu.
- **Düzeltme:**
  1. `LengthType.on_receive` değişken boyda alt sınırı da kontrol ediyor: `min_length(msg)` = uzunluk alanının
     bittiği yer + checksum boyu.
  2. `validate()` bir hook istisna fırlatırsa (ör. paket uzunluk alanını okuyacak kadar uzun değil) hatayı
     loglayıp `False` döner; paket `InvalidReceived` olarak raporlanır.
  3. `RxPoller.poll_once()` tek paketin dispatch hatasını loglayıp sonraki paketle devam eder.
- **Testler:** `tests/test_messages.py` (küçük uzunluk, kısa paket, geçerli değişken boy) ve
  `tests/test_comm.py::test_too_small_length_does_not_stop_the_receiver` (bozuk paketten sonra gelen geçerli paket
  hâlâ alınıyor). Düzeltme geri çekildiğinde bu testler kırılıyor.

### K2 — Paketin sonundaki fazla baytlar kabul ediliyor
- **Önem:** Orta — **Durum:** Karar bekliyor
- **Nerede:** `validate()` yalnızca `len(raw) < beklenen` kontrol ediyor.
- **Ne oluyor:** Sabit boylu mesajda paketin sonuna eklenen baytlar, değişken boylu mesajda uzunluk alanından
  uzun paket kabul ediliyor.
- **Karar:** Reddedilsin mi? Ethernet'te her paket tek mesaj olduğu için reddetmek mantıklı; akış protokollerinde
  splitter ayırıyor.

### K3 — Özel alan tipleri projenin endian'ını takip etmiyor
- **Önem:** Yüksek (big-endian projede Kritik) — **Durum:** Açık (çözüm tasarlandı, uygulanmadı)
- **Nerede:** `FieldType(Structure)`; proje tipleri `Length16`, `Counter8`, `CRC16`, `CmdByte`
- **Ne oluyor:** `BigEndianStructure` alanları `ctypes._endian._other_endian` ile çevirir: temel tipler
  (`c_uint16` …) `__ctype_be__` karşılığına, diziler eleman tipine göre çevrilir; iç içe `Structure` ise **olduğu gibi
  bırakılır**. `FieldType` bir `Structure` olduğu için özel alanlar big-endian mesajda makinenin sırasında
  (x86: little-endian) kalır. Bit alanlarının konumu da değişmez: `a=1` big-endian'da `0x80` olmalıyken `0x01` gider.
  TX ve RX kendi aralarında tutarlı olduğu için simülasyonda testler geçer; hata gerçek cihazda görünür.
  Örnek proje little-endian olduğu için şu an etkilenmiyor.
- **Tasarlanan çözüm (prototiple doğrulandı, Python 3.13):**
  1. `FieldType.__init_subclass__` her özel tip için ters endian'lı bir ikiz üretir ve `__ctype_be__`
     (big-endian makinede `__ctype_le__`) olarak bağlar. ctypes big-endian mesajda bu ikizi kendisi seçer;
     proje tiplerinde hiçbir şey yazmak gerekmez. İkiz aynı metotları taşır, `val` / hook'lar aynı çalışır.
  2. İkiz `Length16`'dan türeyemez (ctypes'ta `_fields_` olan sınıftan türeyen sınıf alanları sona ekler),
     üst sınıftan (`LengthType`) türer. Bu yüzden `isinstance(alan, Length16)` big-endian mesajda `False` döner.
     - **Yol A (önerilen):** Sadece `FieldType` için ctypes'ın metaclass'ından türeyen küçük bir `_FieldMeta`;
       `__instancecheck__` / `__subclasscheck__` ikizin `_origin` bilgisine de bakar. Prototipte `isinstance`
       iki endian'da da doğru. Mesaj sınıflarına dokunmaz.
     - **Yol B:** Metaclass yok; `alan.kind is Length16` ile sorulur, `isinstance(alan, Length16)` kullanılmaması
       dokümante edilir. Risk: unutulursa yine sessiz hata.
  3. Güvenlik kontrolü: mesaj tanımlanırken ikizi olmayan ve endian'ı uyuşmayan bir özel alan `TypeError` verir
     (bayt sırası önemsiz alanlar, ör. tek bayt / `c_char` dizisi, hariç).
- **Karar bekliyor:** Yol A mı Yol B mi; konu şimdilik açık bırakıldı.

### K4 — `snapshot()` / `from_buffer_copy` ile oluşan nesnede metadata yok
- Bkz. B15. `__init__` çalışmadığı için `_channel`, `_rx`, `_tx` yok; `snap.channel` `AttributeError` verir.

---

## Thread güvenliği ve mesaj geçmişi (ayrıntı: `docs/RX_HISTORY_HANDOFF.md`)

| No | Konu | Önem | Durum | Özet |
|---|---|---|---|---|
| B1 | `decode` yarım/sıfır durum gösteriyordu | Kritik | Çözüldü | `memset` + iki `memmove` GIL'i bırakıyordu. Artık yeni görüntü ayrı bir `bytearray`'de hazırlanıp tek `memoryview` atamasıyla yazılıyor. Test: `tests/test_threading.py` (eski kodda 0,3 sn'de binlerce bozuk okuma, yenisinde 0). |
| B2 | Aynı poll'deki paketlerin ara değerleri kayboluyor | Yüksek | Açık | Test yalnızca son paketi görüyor. Düzeltme: mesaj başına history (ring buffer) + `comm.wait_for`. |
| B3 | Gömülü alanlar ve diziler kilit tabanlı korumayı boşa çıkarır | Tasarım | Çözüldü (B1 ile) | `msg.cmd` aynı belleği paylaşan alt nesne. B1'in tek kopyalı yazımı ile çözüldü; tek alan okuması tutarlı; mutex yaklaşımı reddedildi. |
| B4 | Canlı nesneden çok alanlı okuma tutarsız | Tasarım | Açık | `s = msg.snapshot()` ile oku; dokümana kural olarak yazılmalı. |
| B5 | `RxState` güncellemesi veriyle atomik değil | Düşük | Açık | Değer + zaman birlikte gerekiyorsa history kaydı kullanılmalı. |
| B6 | `has_new()` paylaşılan tek imleç | Orta | Kısmen | `peek_new` / `peek_sent` eklendi. Asıl çözüm: çağırana ait `mark` / `since`. |
| B7 | Batch içindeki paketler aynı zaman damgasını taşıyor | Orta | Açık | Global, monoton `seq` eklenmeli. UTS listesinin kronolojik olduğu doğrulanmalı. |
| B8 | `msg.on_receive` callout'u canlı nesneyi değiştirebilir | Düşük | Karar bekliyor | Event ve history decode'un hazırladığı görüntüyü taşısın. |
| B9 | `pack()`: yeni değer + eski CRC gidebiliyor | Yüksek | Açık | Test thread'i checksum hesabı ile `bytes(self)` arasında yazarsa. Düzeltme: hesaplar tek kopya üzerinde. |
| B10 | Değişken boyda `count` / uzunluk / CRC / gövde tutarsızlığı | Yüksek | Açık | B9'un özel hali; aynı düzeltme. |
| B11 | `MessageSent.image` ile `raw` farklı olabilir | Düşük | Açık | `pack` ikisini aynı kopyadan versin. |
| B12 | Periyodik gönderimde `after_send` yarışı | Orta | Açık | `DESIGN.md`'de kayıtlı; B9 düzeltmesi bunu çözmez. |
| B13 | Koruma GIL'e bağlı | Sınırlama | Açık | Free-threaded Python'da import sırasında hata verilsin. |
| B14 | İki yönlü mesajda RX, TX için yazılan değerlerin üzerine yazar | Tasarım | Karar bekliyor | Seçenekler: RX'i history'den okumak / ayrı nesne / dokümante etmek. |
| B15 | `snapshot()` nesnesinde metadata yok | Düşük | Açık | Zaman ve kanal kayıttan okunmalı. |

---

## Diğer açıklar

| Konu | Önem | Durum | Not |
|---|---|---|---|
| `HttpUtsClient` taslak | Yüksek | Açık | Gerçek UTS ile çalışılamıyor. Çok protokollü tasarımla birlikte ele alınacak. |
| Hata enjeksiyonu yok | Özellik | Tasarlandı | `msg.fault` + `Fault.corrupt / resize / flip / raw`; gönderim sırası `pack()` → fault → envelope → UTS. |
| `comm.unsubscribe` kısayolu yok | Düşük | Açık | Şimdilik `comm.bus.unsubscribe(sub)`. |
| Monitor kayıtları bellekte sınırsız | Orta | Açık | Uzun koşularda üst sınır gerekir. |
| Monitor zaman ekseni host saati | Düşük | Açık | UTS zamanı değil. |
| Aynı adreste birden fazla envelope'lu kanalın sırası | Orta | Açık | `RxPoller.channels()` bir `set`; envelope'lu kanalların denenme sırası garanti değil ve header çakışması kontrol edilmiyor. |
| Pure-Python CRC yavaş | Düşük | Açık | 46 bayt ~33 µs; `binascii.crc_hqx` ~0,18 µs. |
| `tests/conftest.py` pytest ile koşulmadı | Düşük | Açık | Ortamda pytest kurulamıyor; ilk pytest koşusunda doğrulanmalı. |
