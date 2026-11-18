# Oturum logu (`SessionLog`)

`SessionLog`, bir test koşusunu bir **oturum klasörüne** yazan servis. `CommLogger`'ın genişletilmiş hali:
aynı paket satırlarına ek olarak UTS hatalarını, RX olaylarını ve test adımı işaretlerini de yazar; testin
bitip bitmediğini ve mesaj tanımlarının nerede olduğunu `session.json`'da tutar.

Bu klasörü okuyan ayrı bir izleme aracı var (`asl_monitor`, ayrı repo). Bu repo aracı bilmez; aradaki tek sözleşme
bu dokümandaki dosya biçimidir.

## Kullanım

```python
from asl_testing import SessionLog

session = SessionLog(comm, "runs", name="lab1")      # runs/2026-11-19_001500_lab1/
session.mark("adım 2: motor başlat")                 # test adımı işareti
...
comm.close()
session.close()                                      # comm.close()'dan sonra: kuyruktaki olaylar önce yazılır
```

Her test case için ayrı oturum:

```python
def setUp(self):
    super().setUp()                                   # self.comm açılır, cleanup'ta kapanır
    self.session = SessionLog(self.comm, "runs", name=self.id())
    self.addCleanup(self.session.close)               # comm.close'dan sonra çalışır (cleanup ters sırada)
```

| Parametre | Anlamı |
|---|---|
| `comm` | Dinlenecek `Comm` |
| `root` | Oturum klasörlerinin oluşturulacağı klasör (varsayılan `runs`) |
| `name` | Klasör adına ve `session.json`'a eklenen ad (test adı, tezgâh ...) |
| `projects` | Mesaj tanımlarının proje sınıfları; verilmezse `comm.projects` |

Deneme: `python -m examples.session_demo` (`runs/` altına bir oturum yazar).

## Bilgiler nereden geliyor

`SessionLog`, `comm.subscribe(object, ...)` ile EventBus'taki bütün olayları dinler. Yeni veri üretmez:

| Olay | Yayınlayan | Satır |
|---|---|---|
| `MessageReceived`, `InvalidReceived`, `UnknownReceived` | RX thread'i (dispatcher) | `RX`, `RX-INVALID`, `RX-UNKNOWN` |
| `MessageSent` | TX thread'i | `TX` |
| `LinkError` | RX / TX (UTS isteği başarısız) | `ERROR` |
| `RxTimeout`, `RxRestored`, `RxOverflow` | RX thread'i | `EVENT` |
| `Mark` | `session.mark(...)` (bus'a yayınlanır) | `MARK` |

`mark` bus üzerinden yayınlandığı için kendinden önce yayınlanan paketlerin arkasına, doğru sırada yazılır.

## Oturum klasörü

```
runs/2026-11-19_001500_lab1/
    session.json     bu koşunun bilgileri
    records.csv      kayıtlar
```

Aynı saniyede aynı adla ikinci bir oturum açılırsa klasör adına `_2`, `_3` ... eklenir.

### `session.json`

```json
{
  "format": "asl-session",
  "formatVersion": 1,
  "name": "lab1",
  "status": "running",
  "started": "2026-11-19 00:15:00.123456",
  "ended": null,
  "records": "records.csv",
  "catalog": {
    "kind": "asl",
    "root": "C:/work/TestingInfrastructureASL",
    "projects": ["projects.example_project.header:ProjectBase"],
    "modules": ["projects.example_project.header", "projects.example_project.messages"]
  },
  "python": "3.13.1"
}
```

| Alan | Anlamı |
|---|---|
| `format`, `formatVersion` | Biçim adı ve sürümü. Biçim geriye uyumsuz değişirse sürüm artar |
| `status` | `running`; `session.close()` ile `closed`. Okuyan taraf testin bittiğini buradan anlar |
| `started`, `ended` | Yerel saat, mikrosaniye. Oturumlar `started`'a göre sıralanır |
| `records` | Kayıt dosyasının adı |
| `catalog` | Mesaj tanımlarının yeri: import kökü (`root`), proje sınıfları (`modül:Sınıf`), mesaj modülleri |

Dosya her yazımda geçici dosyaya yazılıp yerine konur (`os.replace`); okuyan taraf yarım dosya görmez.

### `records.csv`

`CommLogger` sütunları + sonda `note`:

```
host_time, uts_time, direction, channel, message, signature, length, data, note
```

| `direction` | Anlamı | `data` | `note` |
|---|---|---|---|
| `TX`, `RX` | Gönderilen / alınan geçerli paket | ham baytlar (hex) | |
| `RX-INVALID` | CRC / boy hatalı paket | ham baytlar | |
| `RX-UNKNOWN` | Hiçbir mesaja ait olmayan paket | ham baytlar | |
| `ERROR` | `LinkError` | | `UTS send failed: ConnectionError(...)` |
| `EVENT` | `RxTimeout`, `RxRestored`, `RxOverflow` | | `RxTimeout age=0.152` |
| `MARK` | `session.mark(...)` | | işaret metni |

Kurallar:
- **Her kayıt tek satır.** `note` içindeki satır sonu `\n`, ters bölü `\\` olarak yazılır. Okuyan taraf satır sonu
  gelmemiş satırı henüz yazılıyor sayar ve bir sonraki okumaya bırakır.
- **Her satırdan sonra `flush`.** Test çökse de o ana kadarki kayıtlar dosyadadır; dosya yazılırken okunabilir.
- **Ham bayt saklanır**, çözülmüş değer saklanmaz. Mesaj tanımı değişirse eski log yeniden çözülebilir.
- `host_time`: test bilgisayarının yerel saati, mikrosaniye. `uts_time`: UTS saniyesi (varsa; `ERROR` / `EVENT` /
  `MARK` satırlarında boş).
- Paket satırları `CommLogger` ile aynı biçimde; bu yüzden aynı okuyucu iki dosyayı da açabilir
  (`CommLogger` dosyasında `note` sütunu ve `session.json` yoktur).

## CommLogger ile farkı

| | `CommLogger` | `SessionLog` |
|---|---|---|
| Çıktı | Tek CSV | Klasör: `records.csv` + `session.json` |
| Paket satırları | Var | Aynısı |
| `ERROR`, `EVENT`, `MARK` satırları, `note` sütunu | Yok | Var |
| Zaman | Milisaniye | Mikrosaniye |
| Testin bittiği / mesaj tanımlarının yeri | Yok | `session.json` |

`CommLogger` değişmedi; ikisi yan yana kullanılabilir.
