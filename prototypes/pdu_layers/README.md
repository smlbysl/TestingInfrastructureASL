# PDU katmanları: prototip

Çok protokollü tasarımın PDU yapısıyla (PDU = PCI + SDU) nasıl kurulabileceğini gösteren, `asl_testing`'den bağımsız
küçük bir prototip. Mevcut koda dokunmaz.

```
python -m prototypes.pdu_layers.demo
```

## Katmanlar

```
Mesaj (ctypes)                SDU: payload baytları              message.py
   │
Protocol                      PCI: protokolün kendi alanları      protocols.py, pdu.py
   │  Pdu(pci, sdu, timestamp)
Channel                       protokol + adaptör + registry       channel.py
   │
UTS adaptörü                  Pdu <-> UTS JSON                     adapters.py
   │
UTS                                                               gateway.py (sahte)
```

| Kavram | Ne | Örnek |
|---|---|---|
| SDU | Mesajın baytları | `bytes(bit_report)` |
| PCI | Protokolün eklediği alanlar = mesajın o protokoldeki adresi | `Mil1553Pci(node=5, subnet=3)`, `CanPci(0x123)`, `NoPci()` |
| PDU | PCI + SDU (+ alım zamanı) | `Pdu(pci, sdu, timestamp)` |

## Kurallar

**Mesaj oluşturma:** Protokolün PCI alanları zorunludur. 1553'te `node` ve `subnet` (1–32), CAN'da `can_id`.
Eksik alan `TypeError`, aralık dışı değer `ValueError` verir.

**Kayıt:** Mesajlar kendi kanalına kaydolur. Aynı PCI altında:
- signature'sız bir mesaj varsa başka mesaj kaydolamaz,
- birden fazla mesaj varsa her birinin farklı bir signature'ı olmalıdır,
- aynı mesaj yeniden oluşturulursa eskisinin yerini alır.

**Tanıma:** UTS'den gelen öğe, o adresi paylaşan kanallara sırayla verilir (başlıklı kanallar önce):
1. Adaptör öğeyi PDU'ya çevirir. Kanalın protokolü paketi kendine ait bulmazsa sıradaki kanal denenir.
2. PCI'ın anahtarıyla kanalın registry'sinde adaylar bulunur.
3. Tek aday ve signature'sızsa o mesajdır; değilse signature'ı tutan mesaj.
4. Hiçbiri tutmazsa unknown.

**Hatalar ve sonuçları:**

| Nerede | Ne | Sonuç |
|---|---|---|
| Adaptör | UTS cevabı beklenen formatta değil (1553 word sayısı tutmuyor, bayt 0–255 dışı) | gateway error |
| Protocol | Paket bu kanalın başlığına uymuyor | sıradaki kanal, hiçbiri değilse unknown |
| Registry | PCI ya da signature eşleşmiyor | unknown (kanal bilgisiyle) |
| Mesaj | Boy tutmuyor | invalid |

## Varsayımlar (gerçek UTS ile kontrol edilecek)

- Bayt akışı: `{"message": [b0, b1, ...], "timestamp": t}`
- 1553: `{"message": [node, subnet, word_count, w0, ...], "timestamp": t}`; word'ler MSB önce
- CAN: `{"id": can_id, "message": [...], "timestamp": t}` (tamamen varsayım)
- `timestamp` birimi bilinmiyor; adaptörde `time_unit` ile ayarlanır
- 1553 T/R biti PCI'da yok

## asl_testing'e taşınırken

| Prototip | asl_testing'deki karşılığı |
|---|---|
| `Pdu` | `UtsFrame` ve `RxFrame`'in yerini alır |
| `Protocol` | `ProtocolType` enum'unun yerini alır; `Envelope` byte stream protokolünün başlığı (`Header`) olur |
| `UtsAdapter` | `UtsClient.transfer / fetch` içindeki bayt varsayımını taşır |
| `Channel.registry` | Aile / proje sınıfındaki `Registry` kanala taşınır |
| `Gateway.poll` | `Transport.poll` + `Dispatcher` |
| `Message` | `BaseMessageStructure` aynen kalır; sadece PCI alanlarını protokole verir |

Prototipte olmayanlar: özel alanlar (uzunluk, sayaç, CRC), değişken boy, olaylar, thread'ler, config istekleri,
segmentasyon (TP) katmanı.
