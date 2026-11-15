# Test arayüzü: neye, nasıl erişilir

Yazar: İsmail Baysal

Bu belge arayüzlerin referansı ve açık tasarım soruları. Nasıl kullanılacağı için `docs/USAGE.md`'ye bak.

Bu belge test yazan kişinin kullanabileceği yüzeyi listeler. Her madde için iki şeye bakıldı:
- **Test için anlamlı mı?** Test kodu bunu kullanmalı mı?
- **Tasarım kararı:** Bu parçayı biz bilerek mi ekledik, yoksa ayrıntıdan mı ibaret?

Erişilebilen ama test için tavsiye edilmeyen parçalar "iç" olarak işaretlendi. Bunlara ulaşmak mümkün, ama testlerin bağımlı olmaması gerekir.

---

## 1. Comm (giriş noktası)

Test kodunun başlıca konuştuğu nesne. Tek başına katmanları kurar ve bağlar.

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `Comm(adapter, projects, poll_interval, channels, logger)` | Kurulum | Evet | Evet |
| `open()` / `close()` / `with Comm(...)` | Thread'leri başlatır / durdurur (kanal başına RX thread'i ve denetçi; periyodik mesajı olan kanal başına TX thread'i) | Evet | Evet |
| `send(msg) -> bool` | Tek gönderim, başarısızsa `False` | Evet | Evet |
| `start(msg)` / `stop(msg)` | Periyodik gönderim | Evet | Evet |
| `start_all(channel=None)` / `stop_all(channel=None)` | Kanaldaki (ya da hepsindeki) periyodik TX mesajlarını başlatır / durdurur; listelerini döndürür | Evet | Evet |
| `on_receive(msg, handler)` | Mesaj alındığında handler (kendi thread'inde) | Evet | Evet |
| `wait_new(msg, timeout)` | Yeni geçerli paket gelene kadar bekler | Evet | Evet |
| `wait_for(msg, predicate, timeout, after) -> Record \| None` | Değerleri koşulu sağlayan paket gelene kadar bekler; tek yoklamadaki ara paketlere de bakar | Evet | Evet |
| `wait_sent(msg, timeout)` | Yeni başarılı gönderim olana kadar bekler | Evet | Evet |
| `listen(channel)` | Kayıtlı mesajı olmayan kanalı da yoklar | Evet | Evet |
| `unknown` | Hiçbir mesajla eşleşmeyen çerçevelerin listesi | Evet | Evet |
| `subscribe(event_type, handler, where)` | Herhangi bir olaya abone ol | Evet | Evet |
| `adapter` (`UtsAdapter`) | Adaptör: UTS yapılandırması ve filtreler (`comm.adapter.add_filter(msg)` vb.) | Evet | Evet |
| `bus`, `transport`, `dispatcher`, `rx`, `tx` | Katman nesneleri | Hayır | İç |
| `log` | Logger | Hayır | İç |

## 2. Mesaj nesnesi (`BaseMessageStructure`)

Test, mesajın değerlerini ve durumunu bu nesne üzerinden okur ve yazar.

### Değer ve kimlik
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.<alan>` | Alan değeri (okuma / yazma) | Evet | Evet |
| `msg.channel` | Mesajın kanalı | Evet | Evet |
| `msg.direction` | RX / TX / BOTH | Evet | Evet |
| `msg.signature_id` | İmza değeri | Evet (hata ayıklama) | Evet |
| `bytes(msg)` | Yapının ham belleği | Sınırlı | Evet, ama ara temsil |
| `msg.pack()` | Gönderilecek baytlar (sayaç ve CRC dahil, sayılmaz) | Evet (test verisi üretmek için) | Evet |
| `msg.body_size()` / `msg.wire_size()` | Değişken boy bilgisi | Evet | Evet |
| `msg.validate(raw)` / `msg.decode(raw, ts)` | Ham baytı doğrula / yükle | Hayır (dispatcher kullanır) | İç |

### Alım durumu (RX)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.has_new()` | Yeni geçerli paket sayısı, sayacı sıfırlar | Evet | Evet |
| `msg.peek_new()` | Aynısı, sıfırlamadan | Evet | Evet |
| `msg.rx_history` | Gelen paketler sırayla (son N): `mark()`, `since(mark)`, `last()`, `wait_for(...)`, `dropped`, `capacity` | Evet | Evet |
| `msg.snapshot()` | Canlı nesnenin tek kopyayla alınmış hali; birden fazla alanı aynı paketten okumak için | Evet | Evet |
| `with msg.locked_update(): ...` | Mesajın kilidi: bloktaki yazmalar aynı pakette birlikte gider, istek biti kaybolmaz; süren gönderimi bekler | Evet | Evet |
| `msg.rx_timestamp` | UTS'ten gelen son paketin zamanı | Evet | Evet |
| `msg.rx_host_time` | Bu makinenin saatinde son paket zamanı | Evet | Evet |
| `msg.rx_age` | Son paketten bu yana geçen süre | Evet | Evet |
| `msg.rx_state` | `RxState` (count, errors, timing ...) | Sınırlı | Evet |

### Gönderim durumu (TX)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.has_sent()` | Başarılı gönderim sayısı, sayacı sıfırlar | Evet | Evet |
| `msg.peek_sent()` | Aynısı, sıfırlamadan | Evet | Evet |
| `msg.tx_state` | `TxState` (count, last_time, timing) | Sınırlı | Evet |

### Kancalar (callout)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.on_send(fn)` | Her gönderimde `fn(msg)`, paketlemeden önce | Evet (periyodik değer üretmek için) | Evet |
| `msg.on_receive(fn)` | Her alımda `fn(msg)` | Evet | Evet |

### Sınıf düzeyi (tanım, genelde test yazmaz)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `families()`, `lookup*()`, `clear_registry()` | Registry sorguları | Hayır | İç |
| `initialize()` | Varsayılanlara döndürür | Evet (testler arası sıfırlama) | Evet |
| `_channel`, `_direction`, `_timing`, `_signature` | Sınıf varsayılanları | Tanımda kullanılır | Evet |
| `_rx`, `_tx`, `_registered`, `_trailer_offset()` ... | Özel alanlar | Hayır | İç |

## 3. Alanlar (`FieldType` ve özel tipler)

| Tip | Test için | Tasarım |
|---|---|---|
| Normal ctypes alanı (`c_uint16` vb.) | Değer okuma / yazma | Evet |
| Bit alanları | `msg.cmd.startReq` gibi | Evet |
| `FieldType.val` | Özel tiplerin değeri | Evet |
| `LengthType` | Paketlemede otomatik hesaplanır; test yanlış boy üretmek isterse el ile yazamaz | Evet, ama fault için yetersiz |
| `CounterType` | Gönderimde artar; test değeri set edebilir | Evet |
| `ChecksumType` | Paketlemede hesaplanır | Evet, ama bozuk CRC için fault gerekir |
| `AsciiType` | Metin alanı | Evet |
| `CmdByte` (örnek) | `on_init` + `after_send` ile tek seferlik bit | Evet, tasarım örneği |
| `class X(CounterType, endian=ENDIAN)` / `class P(BaseMessageStructure, endian=ENDIAN)` | Bayt sırası; değer projenin `settings.py`'sinde, varsayılan little; uyuşmazlık `TypeError` | Evet |

Özel tiplerin hook'ları: `on_init`, `on_send` (paketlemede), `on_receive` (doğrulama), `after_send` (başarılı gönderimden sonra).

## 4. Kanal (`Channel`, `ChannelSet`)

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `ch.name`, `ch.interface` | Kimlik | Evet | Evet |
| `ch.protocol` | Kanalın protokol adı (`"ethernet"`, `"rs422"`, `"mil1553"`); tanımı `UtsAdapter`'da | Evet | Evet |
| `ch.key` | Interface: `(protocol, interface)` | Sınırlı | Evet |
| `ch.framing` | Splitter ve envelope | Evet (özel çerçeve için) | Evet |
| `ChannelSet.all()` | Projedeki tüm kanallar | Evet | Evet |
| `ChannelSet` kuralı (`check_channels`) | Bir interface, bir kanal; tanım sırasında kontrol | Evet (hata mesajı) | Evet |
| `EthernetChannel`, `Rs422Channel`, `Mil1553Channel` | Kanal tipleri (protokole göre) | Evet (proje tanımı) | Evet |

### Protokoller

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `UtsAdapter(time_unit)` / `FakeUtsAdapter(time_unit)` | Protokol tanımlarını kurar; `time_unit` UTS birimi başına saniye (varsayılan 1e-6) | Evet (zaman birimi farklıysa) | Evet |
| `adapter.protocols`, `adapter.protocol(channel)` | Protokol adı → tanım; kanalın tanımı | Sınırlı | Evet |
| `UtsAdapter(timeout=...)`, `adapter.timeout_of(protocol)` | İstek bekleme süresi; verilmezse protokolünki (Ethernet / 1553: 2 sn, RS422: 3 sn) | Evet | Evet |
| `post(path, interface, body, timeout)` / `get(path, interface, timeout)` | Gerçek adaptörün yazacağı istekler; UTS cevap gövdesini döndürür, süre içinde cevap yoksa `AdapterError` | Evet (gerçek adaptör) | Evet |
| `UtsAdapter.answer(status, body)` | 200 ise gövde, değilse `statusInfo`'dan `AdapterError` (`status`, `code`) | Evet (gerçek adaptör) | Evet |
| `adapter.send(channel, wire)` / `adapter.receive(channel)` | Tanımla encode + `post` → gönderim zamanı / `get` + decode → `Polled(received, overflow)` (Transport kullanır) | Sınırlı | Evet |
| `EthernetProtocol`, `Rs422Protocol` | Bayt listesi: `{"message": [...]}` | Sınırlı | Evet |
| `protocol.sent_time(answer)` / `items(answer)` / `overflow(answer)` | POST cevabındaki zaman (sn); GET cevabındaki öğeler ve taşma bayrağı | Sınırlı | Evet |
| `Mil1553Protocol` | 16 bitlik değer listesi: `[rt, subnet, word_count, word, ...]`; kelime sırası kanaldan | Sınırlı | Evet |
| `protocol.encode(channel, data)` / `decode(channel, item)` / `simulate(channel, data, ts)` | Bayt ↔ UTS gövdesi / öğesi | Sınırlı (protokol testi) | Evet |
| `Mil1553Channel(1, byte_order="big")` | 16 bitlik kelimelerin bayt sırası; mesaj yapısıyla aynı olmalı | Evet (big-endian projede) | Evet |

## 5. Çerçeveleme (`Framing`, `Splitter`, `Envelope`)

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `Envelope.on_send(data)` | Gönderimde başlık ekler | Evet (yanıt üretirken) | Evet |
| `Envelope.on_receive(wire)` | Kabul ederse mesaj baytlarını, etmezse `None` | Evet (kendi envelope'unu test ederken) | Evet |
| `Envelope.offset` | Başlık boyu (UTS filtresi için) | Evet | Evet |
| `Splitter.split(data)` | UTS'ten gelen veriyi çerçevelere böler | Evet (akış protokolleri için) | Evet |

## 6. Olaylar (`events`)

Test, paket akışını olaylardan izleyebilir.

| Olay | İçerik | Anlamlı mı | Tasarım |
|---|---|---|---|
| `MessageReceived` / `MessageSent` | Mesaj nesnesi, gönderilen/alınan görüntü; `MessageSent.timestamp` UTS'in gönderim zamanı | Evet | Evet |
| `InvalidReceived` | Bozuk paket | Evet | Evet |
| `UnknownReceived` | Eşleşmeyen çerçeve, kanal bilgisiyle | Evet | Evet |
| `WireReceived` / `WireSent` | Tel üzerindeki bayt, UTS zamanı | Evet (framing testi) | Evet |
| `RxTimeout` / `RxRestored` | Periyodik RX kesildi / geri geldi | Evet | Evet |
| `RxOverflow` | UTS alım tamponu taştı (kanal, zaman) | Evet | Evet |
| `LinkError` | UTS hatası (gönderim veya alım) | Evet | Evet |
| `event.snapshot()` | Olayın görüntüsünü kopyalar | Sınırlı | Evet |

Abonelik: `comm.subscribe(Tip, handler, where=msg)`; `where` belirli bir mesajla sınırlar. Abonelik `comm.bus.unsubscribe(sub)` ile biter.

## 7. UTS

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `FakeUtsAdapter.inject(channel, bytes, timestamp=None)` | Simülasyonda RX paketi üretir (kanalın protokol tanımıyla) | Evet (sahte cihaz) | Evet |
| `FakeUtsAdapter.overflow(channel)` | Kanalın bir sonraki GET'i taşma bildirir | Evet (simülasyon) | Evet |
| `FakeUtsAdapter.posted` | Gönderilen istekler: `(path, interface, gövde)`; gövdede `"message"` hattaki baytlar | Evet (simülasyonda kontrol) | Evet |
| `comm.adapter.get_config / set_config` | Hedefin UTS yapılandırması | Evet | Evet |
| `comm.adapter.add_filter(msg)` / `remove_filter(msg)` | Mesajın imzasını filtreye ekler / çıkarır | Evet | Evet |
| `comm.adapter.get_filter / set_filter / clear_filter` | Ham filtre yönetimi | Sınırlı | Evet |
| `AdapterError` | UTS hata tipi | Evet | Evet |
| `read_config` / `write_config` / `read_filter` / `write_filter` | Gerçek adaptörün yazacağı config ve filtre istekleri; yazılmamışsa `NotImplementedError` | Evet (gerçek adaptör) | Evet |
| `Adapter` | Çekirdeğin gördüğü sözleşme (`send`, `receive`); config ve filtre yoksa `AdapterError` | Sınırlı (yeni adaptör yazarken) | Evet |

## 8. Servisler

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `CommLogger(comm, path)` | Paketleri CSV'ye yazar | Evet | Evet |
| `ErrorLog` | Hataları olay olarak toplar | Evet | Evet |
| `MonitorService(comm, projects, port)` | Tarayıcıda canlı / CSV izleme | Evet | Evet |

## 9. Zamanlama ve yön

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `Timing(period, tolerance)` | Periyot ve tolerans | Evet | Evet |
| `Direction.RX / TX / BOTH` | Yön | Evet | Evet |
| `Signature(offset, mask, endian)` | Mesaj imzası | Evet | Evet |

---

## Açık tasarım soruları

- **Fault enjeksiyonu** henüz yok. Önerilen yapı: mesaja bağlı `msg.fault` ve `Fault.corrupt / resize / flip / raw`. Bozuk CRC ve uzunluk için alan değeri set etmek yetmediği için gerekli.
- **`CommLogger` ve `Comm.log`** ayrımı: logger seçimi test tarafına bırakıldı.
- **Frame tipleri:** `RxFrame` iç tip. Testlerin olay (`WireReceived`) üzerinden çalışması önerilir.
- **Üst düzey dışa aktarım:** Çözüldü. Test kodu ve proje tanımları her şeyi `from asl_testing import ...` ile alır (`asl_testing/__init__.py`, `__all__`). Dahili tipler (`RxFrame`, `Transport`, `Dispatcher`, `RxPoller`, `TxScheduler`) dışa açılmadı.

## Mesaj geçmişi (`MessageHistory`, `Record`)

`msg.rx_history` bir `MessageHistory`'dir; her kayıt bir `Record`.

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `history.mark() -> int` | Şu anki konum; sonrası okunur | Evet | Evet |
| `history.since(mark) -> list[Record]` | `mark`'tan sonraki kayıtlar, eskiden yeniye | Evet | Evet |
| `history.last() -> Record \| None` | Son kayıt | Evet | Evet |
| `history.wait_for(predicate, after, timeout)` | `comm.wait_for`'un altındaki çağrı | Sınırlı | Evet |
| `history.dropped` | Taşma yüzünden düşen kayıt sayısı | Evet | Evet |
| `history.capacity`, `len(history)` | Kapasite, mevcut kayıt sayısı | Evet | Evet |
| `history.clear()` | Geçmişi boşaltır | Sınırlı | Evet |
| `record.snapshot()` | O paketin değerleriyle ayrı bir nesne | Evet | Evet |
| `record.seq` | Bütün mesajlar arasında geliş sırası | Evet | Evet |
| `record.timestamp` / `record.host_time` | UTS zamanı / bu makinenin saati | Evet | Evet |
| `record.image`, `record.cls` | Ham bellek, mesaj sınıfı | Sınırlı | Evet |

Ayarlar: sınıfta `_history = 64` (varsayılan), nesnede `history=` parametresi. Nesne yeniden oluşturulunca geçmiş boşalır.
Açık nokta: `seq` UTS'in GET listesinin kronolojik olmasına dayanıyor; gerçek UTS ile doğrulanmalı.
