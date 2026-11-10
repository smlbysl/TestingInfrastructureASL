# Bilinen sorunlar

Bütün bilinen açıklar tek listede. Her madde: önem, durum, nerede, ne oluyor, önerilen düzeltme.
Ayrıntılı analiz için kaynak belgeler:
- `docs/RX_HISTORY_HANDOFF.md` (B1–B15: thread güvenliği, mesaj geçmişi, TX tutarlılığı)
- `docs/DESIGN.md` → "Açık konular"

Önem: **Kritik** (veri kaybı / thread ölümü / yanlış veri hatta), **Yüksek**, **Orta**, **Düşük**.
Durum: **Açık**, **Karar bekliyor**, **Doğrulandı** (ölçümle ya da testle gösterildi), **Düzeltildi** (dal `v2.1-pdu`).

---

## Özet

| No | Konu | Durum |
|---|---|---|
| K1 | Uzunluk alanı RX thread'ini öldürüyordu | Düzeltildi |
| K2 | Paketin sonundaki fazla byte'lar kabul ediliyor | Karar bekliyor |
| K3 | Özel alan tipleri projenin endian'ını takip etmiyor | Açık |
| K4 | `snapshot()` nesnesinde metadata yok | Dokümante edildi (B15) |
| K5 | Aynı adreste header'lı kanalların header çakışması kontrol edilmiyor | Açık |
| B1–B11, B13 | Thread güvenliği, mesaj geçmişi, TX tutarlılığı | Düzeltildi (B5, B12, B14 hariç) |

---

## RX doğrulama

### K1 — Değişken boyda küçük uzunluk değeri RX thread'ini öldürüyordu
- **Önem:** Kritik — **Durum:** Düzeltildi (`2852a49`)
- **Ne oluyordu:** Uzunluk alanı checksum boyundan küçükse `from_buffer_copy(raw, negatif)` `ValueError` fırlatıyor,
  RxPoller thread'i ölüyordu; sonraki hiçbir paket alınmıyordu.
- **Düzeltme:** `LengthType.on_receive` alt sınırı kontrol ediyor; `validate()` hook istisnasını geçersiz paket sayıyor
  (WARNING); RX döngüsü tek paketteki ya da döngüdeki hatayı loglayıp devam ediyor. Testler: `RxValidationTests`,
  `test_too_small_length_does_not_stop_receiving`.

### K2 — Paketin sonundaki fazla baytlar kabul ediliyor
- **Önem:** Orta — **Durum:** Karar bekliyor
- **Nerede:** `validate()` yalnızca `len(raw) < beklenen` kontrol ediyor.
- **Karar:** Reddedilsin mi? Ethernet'te her paket tek mesaj olduğu için reddetmek mantıklı; akış protokollerinde
  splitter ayırıyor.

### K3 — Özel alan tipleri projenin endian'ını takip etmiyor
- **Önem:** Yüksek (big-endian projede Kritik) — **Durum:** Doğrulandı, açık
- **Ne oluyor:** `FieldType` makinenin yerel sırasıyla (x86: little-endian) tanımlı. Big-endian bir projede bile
  little-endian kalıyor, ctypes hata vermiyor. Uzunluk, sayaç ve CRC hatta ters sırayla gider; bit alanlarının konumu
  değişir. 1553 projesi (`Mil1553Base`) big-endian olduğu için 1553 mesajlarında özel tip kullanılırsa bu sorun görünür.
- **Düzeltme önerisi:** Proje tiplerinde endian açıkça yazılsın (`class CRC16(ChecksumType, BigEndianStructure)`) ve
  kütüphane tanımda her özel alanın bayt sırasını projeninkiyle karşılaştırıp uyuşmazsa `TypeError` versin.

### K5 — Aynı adreste header'lı kanalların header çakışması
- **Önem:** Orta — **Durum:** Açık
- **Ne oluyor:** Aynı adreste iki header'lı kanal varsa denenme sırası tanım sırasıdır (artık `set` değil), ama iki
  header'ın aynı paketi kabul edip etmediği kontrol edilmiyor.

---

## Thread güvenliği ve mesaj geçmişi (ayrıntı: `docs/RX_HISTORY_HANDOFF.md`)

| No | Konu | Durum | Not |
|---|---|---|---|
| B1 | `decode` yarım/sıfır durum gösteriyordu | Düzeltildi | Tek `memoryview` kopyası. Ölçüm: eski 4.602.009 tutarsız okuma, yeni 0. Test: `OneCopyDecodeTests`. |
| B2 | Aynı poll'deki paketlerin ara değerleri kayboluyordu | Düzeltildi | `rx_history` + `comm.wait_for`. Test: `test_wait_for_finds_a_value_in_the_middle_of_a_batch`. |
| B3 | Gömülü alanlar ve diziler kilit tabanlı korumayı boşa çıkarır | Düzeltildi | B1 ile; kilit yok. |
| B4 | Canlı nesneden çok alanlı okuma tutarsız | Düzeltildi | `msg.snapshot()`; kural dokümanda. |
| B5 | `RxState` güncellemesi veriyle atomik değil | Dokümante edildi | Değer + zaman için history kaydı. |
| B6 | `has_new()` paylaşılan tek imleç | Düzeltildi | `mark()` / `since()` / `wait_for(after=)`; `has_new` ve `peek_new` kaldı. |
| B7 | Batch içindeki paketler aynı zaman damgasını taşıyor | Düzeltildi | Global monoton `seq`. UTS listesinin kronolojik olduğu doğrulanmalı. |
| B8 | `msg.on_receive` callout'u canlı nesneyi değiştirebilir | Karar verildi | Olay ve history paketin kendisini (callout öncesi) taşır. Callout kaldı. |
| B9 | `pack()`: yeni değer + eski CRC gidebiliyordu | Düzeltildi | Hesaplar tek kopyada. Test eski pack ile başarısız, yenisiyle geçiyor. |
| B10 | Değişken boyda `count` / uzunluk / CRC / gövde tutarsızlığı | Düzeltildi | B9 ile. |
| B11 | `MessageSent.image` ile `raw` farklı olabiliyordu | Düzeltildi | İkisi aynı kopyadan. |
| B12 | Periyodik gönderimde `after_send` yarışı | Açık | B9 düzeltmesi bunu çözmez. |
| B13 | Koruma GIL'e bağlı | Düzeltildi | GIL'siz Python'da import hata veriyor. |
| B14 | İki yönlü mesajda RX, TX için yazılan değerlerin üzerine yazar | Karar bekliyor | Seçenekler: RX'i history'den okumak / ayrı nesne / dokümante etmek. |
| B15 | `snapshot()` nesnesinde metadata yok | Dokümante edildi | Zaman ve kanal kayıttan okunur. |

---

## Çok protokol (dal `v2.1-pdu`)

| Konu | Önem | Durum | Not |
|---|---|---|---|
| UTS biçimleri doğrulanmadı | Yüksek | Açık | Byte stream `{"message": [...]}`; 1553 `[node, subnet, wc, words]`; CAN tamamen varsayım; timestamp birimi bilinmiyor (`time_unit`). |
| 1553 T/R biti ve mode code'lar PCI'da değil | Orta | Açık | UTS'nin rolü (BC / RT / monitor) ve RX'in istekle gelip gelmediği netleşmeli. |
| Kanal config'i (RS422 / Camera Link, CANopen) | Orta | Açık | `comm.open()` sırasında protokol config'lerini UTS'ye gönderecek yapı yok. |
| CANopen (SDO, NMT, heartbeat) | Özellik | Açık | CAN üzerinde servis olarak; parçalı aktarım için TP katmanı. |
| Signature'sız mesaj artık slotunda tek başına | Davranış değişikliği | Bilerek | v2.1-base'de sabit boylu mesajlarla tek bir değişken boylu mesaj aynı kanalı paylaşabiliyordu. |

---

## Diğer açıklar

| Konu | Önem | Durum | Not |
|---|---|---|---|
| `HttpUtsClient` taslak | Yüksek | Açık | Master'da referans HTTP katmanı var (`comm/uts/http.py`, `api.py`). |
| Hata enjeksiyonu yok | Özellik | Tasarlandı | `msg.fault` + `Fault.corrupt / resize / flip / raw`; gönderim sırası `_pack()` → fault → adaptör → UTS. |
| `comm.unsubscribe` kısayolu yok | Düşük | Açık | `comm.bus.unsubscribe(sub)` (artık tekrar çağrılabilir). |
| Monitor kayıtları bellekte sınırsız | Orta | Açık | Uzun koşularda üst sınır gerekir. |
| Monitor zaman ekseni host saati | Düşük | Açık | UTS zamanı değil. |
| Pure-Python CRC yavaş | Düşük | Açık | 46 bayt ~33 µs; `binascii.crc_hqx` ~0,18 µs. |
| `tests/conftest.py` pytest ile koşulmadı | Düşük | Açık | Ortamda pytest kurulamıyor. |
