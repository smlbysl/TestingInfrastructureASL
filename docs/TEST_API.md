# Test arayüzü: neye, nasıl erişilir

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
| `Comm(uts, projects, poll_interval, channels, logger, adapters, time_unit)` | Kurulum; `adapters` protokol başına UTS adaptörü, `time_unit` UTS zaman biriminin saniyesi | Evet | Evet |
| `open()` / `close()` / `with Comm(...)` | Thread'leri başlatır / durdurur | Evet | Evet |
| `send(msg) -> bool` | Tek gönderim, başarısızsa `False` | Evet | Evet |
| `start(msg)` / `stop(msg)` | Periyodik gönderim | Evet | Evet |
| `on_receive(msg, handler)` | Mesaj alındığında handler (kendi thread'inde) | Evet | Evet |
| `wait_new(msg, timeout)` | Yeni geçerli paket gelene kadar bekler | Evet | Evet |
| `wait_sent(msg, timeout)` | Yeni başarılı gönderim olana kadar bekler | Evet | Evet |
| `wait_for(msg, predicate, timeout, after)` | Geçmişte predicate'i tutan ilk paketi bekler; `Record` ya da `None` | Evet | Evet |
| `listen(channel)` | Kayıtlı mesajı olmayan kanalı da yoklar | Evet | Evet |
| `unknown` | Hiçbir mesajla eşleşmeyen çerçevelerin listesi | Evet | Evet |
| `subscribe(event_type, handler, where)` | Herhangi bir olaya abone ol | Evet | Evet |
| `control` (`UtsControl`) | UTS yapılandırması ve filtreler | Evet | Evet |
| `bus`, `transport`, `dispatcher`, `rx`, `tx` | Katman nesneleri | Hayır | İç |
| `log` | Logger | Hayır | İç |

## 2. Mesaj nesnesi (`BaseMessageStructure`)

Test, mesajın değerlerini ve durumunu bu nesne üzerinden okur ve yazar.

### Değer ve kimlik
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.<alan>` | Alan değeri (okuma / yazma) | Evet | Evet |
| `msg.channel` | Mesajın kanalı | Evet | Evet |
| `msg.pci` | Protokoldeki adresi (1553 `node`/`subnet`, CAN `can_id`; Ethernet/RS422'de boş) | Evet | Evet |
| `msg.snapshot()` | O anki değerlerin tutarlı kopyası (kayıtsız, nesne bilgisi yok) | Evet | Evet |
| `msg.direction` | RX / TX / BOTH | Evet | Evet |
| `msg.signature_id` | İmza değeri | Evet (hata ayıklama) | Evet |
| `bytes(msg)` | Yapının ham belleği | Sınırlı | Evet, ama ara temsil |
| `msg.pack()` | Gönderilecek baytlar (sayaç ve CRC tek kopyada; gönderim sayılmaz) | Evet (test verisi üretmek için) | Evet |
| `msg.body_size()` / `msg.wire_size()` | Değişken boy bilgisi | Evet | Evet |
| `msg.validate(raw)` / `msg.decode(raw, ts)` | Ham baytı doğrula / yükle | Hayır (dispatcher kullanır) | İç |

### Alım durumu (RX)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.has_new()` | Yeni geçerli paket sayısı, sayacı sıfırlar | Evet | Evet |
| `msg.peek_new()` | Aynısı, sıfırlamadan | Evet | Evet |
| `msg.rx_timestamp` | UTS'ten gelen son paketin zamanı | Evet | Evet |
| `msg.rx_host_time` | Bu makinenin saatinde son paket zamanı | Evet | Evet |
| `msg.rx_age` | Son paketten bu yana geçen süre | Evet | Evet |
| `msg.rx_state` | `RxState` (count, errors, timing ...) | Sınırlı | Evet |
| `msg.rx_history` | `MessageHistory`: her geçerli paket (`mark`, `since`, `last`, `dropped`) | Evet | Evet |

### Gönderim durumu (TX)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.has_sent()` | Başarılı gönderim sayısı, sayacı sıfırlar | Evet | Evet |
| `msg.peek_sent()` | Aynısı, sıfırlamadan | Evet | Evet |
| `msg.tx_state` | `TxState` (count, last_time, timing) | Sınırlı | Evet |
| `msg.tx_history` | Başarıyla gönderilen paketler | Evet | Evet |

### Kancalar (callout)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `msg.on_send(fn)` | Her gönderimde `fn(msg)`, paketlemeden önce | Evet (periyodik değer üretmek için) | Evet |
| `msg.on_receive(fn)` | Her alımda `fn(msg)`, RX thread'inde (olay görüntüsü bundan öncedir) | Evet | Evet |

### Sınıf düzeyi (tanım, genelde test yazmaz)
| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `channels()`, `clear_registry()` | Projenin kullandığı kanallar / kanallardan nesnelerini çıkarır | Sınırlı (testler arası) | Evet |
| `initialize()` | Varsayılanlara döndürür | Evet (testler arası sıfırlama) | Evet |
| `_channel`, `_direction`, `_timing`, `_signature` | Sınıf varsayılanları | Tanımda kullanılır | Evet |
| `_address`, `_history` | Varsayılan PCI (`{"can_id": 0x123}`), geçmiş kapasitesi (64) | Tanımda kullanılır | Evet |
| Oluşturma: `node=`, `subnet=`, `can_id=`, `history=` | PCI alanları (protokol zorunlu tutar), geçmiş kapasitesi | Evet | Evet |
| `_rx`, `_tx`, `_pci`, `_registered`, `_pack()`, `_trailer_offset()` ... | Özel alanlar | Hayır | İç |

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

Özel tiplerin hook'ları: `on_init`, `on_send` (paketlemede), `on_receive` (doğrulama), `after_send` (başarılı gönderimden sonra).

## 4. Kanal (`Channel`, `ChannelSet`)

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `EthernetChannel(i, header=, splitter=)`, `Rs422Channel(...)` | Bayt akışı kanalları | Tanımda | Evet |
| `Mil1553Channel(i, byteorder="big")`, `CanChannel(i, extended=False)` | 1553 ve CAN kanalları | Tanımda | Evet |
| `ch.name`, `ch.interface`, `ch.protocol` | Kimlik; `protocol` bir protokol nesnesi | Evet | Evet |
| `ch.address` | (UTS path, interface), ör. `("1553", 1)` | Evet (adres bazlı kontrol için) | Evet |
| `ch.has_header`, `ch.splitter` | Bayt akışı ayarları | Sınırlı | Evet |
| `ch.registry` | Kanala kaydolan mesajlar (`identify(pdu)`, `slots`) | Sınırlı (hata ayıklama) | İç |
| `ChannelSet.all()` | Projedeki tüm kanallar | Evet | Evet |
| `ChannelSet` kuralları (`check_channels`) | Tanım sırasında doğrulama | Evet (hata mesajı) | Evet |

## 5. Protokol katmanı (`Pci`, `Pdu`, `Protocol`, `Header`, `Splitter`)

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `Pci` alt sınıfları: `NoPci`, `Mil1553Pci(node, subnet)`, `CanPci(can_id)` | Mesajın protokoldeki adresi | Evet | Evet |
| `Pdu(pci, sdu, timestamp)` | PCI + mesaj baytları | Sınırlı | Evet |
| `Protocol.make_pci(**adres)` | PCI üretir; eksik / fazla alan `TypeError`, aralık dışı `ValueError` | Sınırlı | Evet |
| `Protocol.check_sdu(sdu)` | Boy kuralları (CAN ≤ 8 bayt, 1553 1..32 word) | Sınırlı | Evet |
| `Protocol.offset` | Hatta mesajın önündeki bayt sayısı (UTS filtresi için) | Sınırlı | Evet |
| `Header.encode(pci, sdu)` / `Header.decode(data)` | Bayt akışında başlık; `decode` başka kanalın paketinde `None` | Evet (kendi başlığını yazarken) | Evet |
| `Splitter.split(data)` / `reset()` | UTS'ten gelen akışı paketlere böler | Evet (akış protokolleri için) | Evet |
| Yeni protokol | `Pci` + `Protocol` alt sınıfı + `UtsAdapter` (`register_adapter`) | Proje / altyapı | Evet |

## 6. Olaylar (`events`)

Test, paket akışını olaylardan izleyebilir.

| Olay | İçerik | Anlamlı mı | Tasarım |
|---|---|---|---|
| `MessageReceived` / `MessageSent` | Mesaj nesnesi, `raw` (mesaj baytları), `image` (paketin kendisi) | Evet | Evet |
| `InvalidReceived` | Bozuk paket | Evet | Evet |
| `UnknownReceived` | Eşleşmeyen paket; `channel`, `pci` (adresi) | Evet | Evet |
| `WireReceived` / `WireSent` | Hattaki bayt (başlık dahil), `protocol` = UTS path, UTS zamanı | Evet (başlık testi) | Evet |
| `RxTimeout` / `RxRestored` | Periyodik RX kesildi / geri geldi | Evet | Evet |
| `LinkError` | UTS hatası (gönderim, alım, bozuk biçimli UTS öğesi) | Evet | Evet |
| `event.snapshot()` | Olayın görüntüsünü kopyalar | Sınırlı | Evet |

Abonelik: `comm.subscribe(Tip, handler, where=msg)`; `where` belirli bir mesajla sınırlar. Abonelik `comm.bus.unsubscribe(sub)` ile biter (tekrar çağrılabilir).

## 6b. Geçmiş (`MessageHistory`, `Record`)

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `history.mark()` | Okuyanın konumu; sonraki kayıtlar sayılır | Evet | Evet |
| `history.since(mark)` | Konumdan sonraki kayıtlar, eskiden yeniye | Evet | Evet |
| `history.last()`, `len(history)`, `history.capacity` | Son kayıt, kayıt sayısı, kapasite | Evet | Evet |
| `history.dropped` | Kapasite dolduğu için düşen kayıt sayısı | Evet | Evet |
| `history.wait_for(predicate, after, timeout)` | `comm.wait_for`'un kullandığı bekleme | Sınırlı | Evet |
| `Record.seq`, `.timestamp`, `.host_time`, `.image`, `.snapshot()` | Bir paket: sıra, UTS zamanı, host zamanı, görüntü, değerler | Evet | Evet |

## 7. UTS

| Erişim | Ne yapar | Anlamlı mı | Tasarım |
|---|---|---|---|
| `FakeUtsClient.device_sends(msg)` | Cihaz mesajı gönderir (PCI ve başlık protokolden) | Evet (sahte cihaz) | Evet |
| `FakeUtsClient.device_sends_bytes(ch, data, pci=None)` | Cihaz mesaj baytı gönderir (bozuk paketler için) | Evet | Evet |
| `FakeUtsClient.inject(path, interface, item)` | Ham UTS öğesi (JSON) | Evet (biçim hatası testi) | Evet |
| `FakeUtsClient.sent` | Gönderilenler: `(path, interface, gövde)` | Evet | Evet |
| `UtsClient.post / get` | UTS istemci arayüzü (JSON) | Yeni istemci yazarken | Evet |
| `UtsAdapter`, `ByteListAdapter`, `Mil1553Adapter`, `CanAdapter` | PDU <-> UTS JSON | Yeni protokol / biçim | Evet |
| `UtsFormatError` | UTS'ten gelen öğe beklenen biçimde değil | Sınırlı | Evet |
| `comm.control.get_config / set_config` | Hedefin UTS yapılandırması | Evet | Evet |
| `comm.control.add_filter(msg)` / `remove_filter(msg)` | Mesajın imzasını filtreye ekler / çıkarır | Evet | Evet |
| `comm.control.get_filter / set_filter / clear_filter` | Ham filtre yönetimi | Sınırlı | Evet |
| `UtsError` | UTS hata tipi | Evet | Evet |
| `HttpUtsClient` | Gerçek HTTP istemcisi (henüz taslak) | Hayır (şu an) | Taslak |

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
| `Signature(*alan_adları)` | Mesaj imzası (SDU içindeki alanlar; offset, mask ve endian otomatik) | Evet | Evet |

---

## Açık tasarım soruları

- **Fault enjeksiyonu** henüz yok. Önerilen yapı: mesaja bağlı `msg.fault` ve `Fault.corrupt / resize / flip / raw`. Bozuk CRC ve uzunluk için alan değeri set etmek yetmediği için gerekli.
- **`CommLogger` ve `Comm.log`** ayrımı: logger seçimi test tarafına bırakıldı.
- **Frame tipleri:** `RxFrame` iç tip. Testlerin olay (`WireReceived`) üzerinden çalışması önerilir.
- **Çok protokol:** gerçek UTS biçimleri (CAN gövdesi, zaman birimi), 1553 T/R biti, kanal config'inin `comm.open()` sırasında gönderilmesi açık. Ayrıntı: `docs/KNOWN_ISSUES.md`.
- **Üst düzey dışa aktarım:** Çözüldü. Test kodu ve proje tanımları her şeyi `from asl_testing import ...` ile alır (`asl_testing/__init__.py`, `__all__`). Dahili tipler (`RxFrame`, `Transport`, `Dispatcher`, `RxPoller`, `TxScheduler`) dışa açılmadı.
