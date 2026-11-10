# Bilinen sorunlar

Bütün bilinen açıklar tek listede. Her madde: önem, durum, nerede, ne oluyor, önerilen düzeltme.
Ayrıntılı analiz için kaynak belgeler:
- `docs/RX_HISTORY_HANDOFF.md` (B1–B15: thread güvenliği, mesaj geçmişi, TX tutarlılığı)
- `docs/DESIGN.md` → "Açık konular" (tasarım gereği esnek bırakılanlar)

Önem: **Kritik** (veri kaybı / thread ölümü / yanlış veri hatta), **Yüksek**, **Orta**, **Düşük**.
Durum: **Açık**, **Karar bekliyor**, **Doğrulandı** (ölçümle ya da testle gösterildi).

---

## Öncelik sırası (önerilen)

1. K1: Uzunluk alanı RX thread'ini öldürüyor
2. B1: `decode` okuyuculara yarım değer gösteriyor
3. K3: Özel alan tipleri projenin endian'ını takip etmiyor
4. B9–B11: `pack()` ile gönderilen baytlar tutarsız olabiliyor
5. B2, B6: Mesaj geçmişi (ring buffer) ve çağırana ait imleç
6. B13: GIL kontrolü

---

## RX doğrulama

### K1 — Değişken boyda küçük uzunluk değeri RX thread'ini öldürüyor
- **Önem:** Kritik — **Durum:** Doğrulandı
- **Nerede:** `ChecksumType.on_receive` (`asl_testing/message/fields.py`), `RxPoller`
- **Ne oluyor:** Uzunluk alanı checksum boyundan küçükse (0 veya 1) `_rx_body` negatif döner,
  `from_buffer_copy(raw, negatif)` `ValueError` fırlatır. İstisna yakalanmadığı için RxPoller thread'i ölür.
  Sonraki hiçbir paket alınmaz, `InvalidReceived` da gelmez.
- **Düzeltme:** (1) `LengthType.on_receive` değişken boyda alt sınırı da kontrol etsin (uzunluk alanının bittiği
  yer + checksum boyu); (2) `validate()` bir hook istisna fırlatırsa paketi geçersiz saysın; (3) RX döngüsü tek
  paketteki hatayı loglayıp devam etsin. Testleri eklenecek.

### K2 — Paketin sonundaki fazla baytlar kabul ediliyor
- **Önem:** Orta — **Durum:** Karar bekliyor
- **Nerede:** `validate()` yalnızca `len(raw) < beklenen` kontrol ediyor.
- **Ne oluyor:** Sabit boylu mesajda paketin sonuna eklenen baytlar, değişken boylu mesajda uzunluk alanından
  uzun paket kabul ediliyor.
- **Karar:** Reddedilsin mi? Ethernet'te her paket tek mesaj olduğu için reddetmek mantıklı; akış protokollerinde
  splitter ayırıyor.

### K3 — Özel alan tipleri projenin endian'ını takip etmiyor
- **Önem:** Yüksek (big-endian projede Kritik) — **Durum:** Doğrulandı
- **Nerede:** `FieldType(Structure)`; proje tipleri `Length16`, `Counter8`, `CRC16`, `CmdByte`
- **Ne oluyor:** `FieldType` makinenin yerel sırasıyla (x86: little-endian) tanımlı. Big-endian bir projenin içinde
  bile little-endian kalıyor, ctypes hata vermiyor. Uzunluk, sayaç ve CRC hatta ters sırayla gider.
  Bit alanlarının konumu da değişir: `a=1` little-endian'da `0x01`, big-endian'da `0x80`.
  TX ve RX kendi aralarında tutarlı olduğu için simülasyonda testler geçer; hata gerçek cihazda görünür.
- **Düzeltme:** Proje tiplerinde endian açıkça yazılsın (`class CRC16(ChecksumType, BigEndianStructure)`) ve
  kütüphane, mesaj sınıfı tanımlanırken her özel alanın bayt sırasını projeninkiyle karşılaştırıp uyuşmazsa
  `TypeError` versin.

### K4 — `snapshot()` / `from_buffer_copy` ile oluşan nesnede metadata yok
- Bkz. B15. `__init__` çalışmadığı için `_channel`, `_rx`, `_tx` yok; `snap.channel` `AttributeError` verir.

---

## Thread güvenliği ve mesaj geçmişi (ayrıntı: `docs/RX_HISTORY_HANDOFF.md`)

| No | Konu | Önem | Durum | Özet |
|---|---|---|---|---|
| B1 | `decode` yarım/sıfır durum gösteriyor | Kritik | Doğrulandı | `memset` + iki `memmove` GIL'i bırakıyor. Bu oturumda ölçüldü: mevcut decode 4.602.009 tutarsız okuma, tek kopyalı yazım 0. Düzeltme: görüntüyü hazırlayıp tek `memoryview` atamasıyla yaz. |
| B2 | Aynı poll'deki paketlerin ara değerleri kayboluyor | Yüksek | Açık | Test yalnızca son paketi görüyor. Düzeltme: mesaj başına history (ring buffer) + `comm.wait_for`. |
| B3 | Gömülü alanlar ve diziler kilit tabanlı korumayı boşa çıkarır | Tasarım | Açık | `msg.cmd` aynı belleği paylaşan alt nesne. B1'in tek kopyalı yazımı ile çözülür; mutex yaklaşımı reddedildi. |
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
