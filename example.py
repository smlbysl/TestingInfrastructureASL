"""Uçtan uca örnek: mesaj nesneleri + Transport + Dispatcher + Scheduler + Monitor.

Çalıştırma (proje kökünden):  python example.py
"""
import time

from comm import Dispatcher, LoopbackTransport, Monitor, Scheduler
from generic.channel import Channel
from generic.enumerations import Direction, ProtocolType
from generic.timing import Timing
from project.messages import bambaşka, comut, request
from project.project import Family1, ProjectBase

RS422_0 = Channel(ProtocolType.RS422, 0)
ETH_1 = Channel(ProtocolType.ETHERNET, 1)

SRC, DEST = 0x0001, 0x0002


def show_registries() -> None:
    for reg in ProjectBase.families():
        fields = "+".join(reg.signature.fields) if reg.signature else "-"
        print(f"  [{fields}]")
        print("    all        :", [type(m).__name__ for m in reg.all])
        print("    dispatch   :", {f"{ch}/0x{sid:X}": type(m).__name__ for (ch, sid), m in reg.dispatch.items()})
        print("    periodic_tx:", [type(m).__name__ for m in reg.periodic_tx])
        print("    periodic_rx:", [type(m).__name__ for m in reg.periodic_rx])


def main() -> None:
    # --- Mesaj nesneleri (ICD'den) -------------------------------------------
    # Aile 1: TX, 20 ms periyotlu -> Scheduler gönderir
    sw_version_req = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.02))
    # Aile 1: RX, 50 ms'de bir gelmesi beklenen -> Monitor izler, Dispatcher yazar
    status = comut(DEST, SRC, 0x20, direction=Direction.RX, rx=Timing(0.05, tolerance=1.5))
    # Aynı mesaj tanımı, farklı channel'dan gelen ikinci nesne (event)
    status_eth = comut(DEST, SRC, 0x20, channel=ETH_1, direction=Direction.RX)
    # Aile 1: çift yönlü, varsayılan channel (RS422:0)
    heartbeat = Family1(SRC, DEST, 0x30, direction=Direction.BOTH, rx=Timing(0.1), tx=Timing(0.1))
    # Aile 2: farklı signature (destinationId + sourceId), Ethernet'ten gelir
    diag = bambaşka(0x07, SRC, 0x40, channel=ETH_1, direction=Direction.RX)

    # --- Kullanıcı callout'ları ---------------------------------------------------
    @status.on_receive
    def print_status(msg):
        print(f"  [on_receive] {type(msg).__name__}.comut[0] = 0x{msg.comut[0]:X}")

    # Gönderimden önce payload'ı değiştirir; checksum bu değişikliği kapsar
    sw_version_req.on_send(lambda msg: msg.request.__setitem__(0, msg.tx_state.count))

    # --- Katmanlar --------------------------------------------------------------
    transport = LoopbackTransport()
    dispatcher = Dispatcher(ProjectBase,
                            on_unknown=lambda ch, raw: print(f"  [unknown] {ch} {raw.hex()}"),
                            on_invalid=lambda m, raw: print(f"  [invalid] {type(m).__name__}"))
    transport.set_receiver(dispatcher.on_raw)
    scheduler = Scheduler(transport, ProjectBase)
    monitor = Monitor(ProjectBase)

    print("Registry (aile başına)")
    show_registries()
    print("  RS422:0 aileleri:", [reg.signature.fields for reg in ProjectBase.families(RS422_0)])
    print("  ETH:1   aileleri:", [reg.signature.fields for reg in ProjectBase.families(ETH_1)])

    # --- TX: Scheduler ----------------------------------------------------------
    print("\nTX")
    scheduler.start()
    time.sleep(0.1)
    scheduler.stop()
    print(f"  gönderilen paket: {len(transport.sent)}, "
          f"sw_version_req sayaç: {sw_version_req.messageCounter.val}, "
          f"request[0] (on_send): {sw_version_req.request[0]}, "
          f"heartbeat sayaç: {heartbeat.messageCounter.val}")
    print(f"  son paket geçerli mi (checksum on_send değişikliğini kapsıyor): "
          f"{sw_version_req.validate(bytes(sw_version_req))}")

    # --- Varsayılan değerler ------------------------------------------------------
    print("\nVarsayılanlar")
    print(f"  şu an     : {[hex(v) for v in sw_version_req.request]}")
    sw_version_req.initialize()
    print(f"  initialize: {[hex(v) for v in sw_version_req.request]}  "
          f"(geçerli mi: {sw_version_req.validate(bytes(sw_version_req))})")

    # --- RX: karşı tarafı taklit et --------------------------------------------
    print("\nRX")
    print("  monitor (başta):", [str(r) for r in monitor.check()])

    remote = comut(DEST, SRC, 0x20, channel=RS422_0, direction=Direction.TX)   # karşı tarafın mesajı
    remote.comut[0] = 0xCAFE
    transport.inject(RS422_0, remote.pack())
    print(f"  status.comut[0] = 0x{status.comut[0]:X}  (eth nesnesi: 0x{status_eth.comut[0]:X})")

    remote_diag = bambaşka(0x07, SRC, 0x40, channel=ETH_1, direction=Direction.TX)
    remote_diag.request[0] = 0xBEEF
    transport.inject(ETH_1, remote_diag.pack())
    print(f"  diag.request[0] = 0x{diag.request[0]:X}  (aile 2, ETH:1)")

    bad = bytearray(remote.pack())
    bad[comut.checksum.offset] ^= 0xFF                                     # bozuk CRC
    transport.inject(RS422_0, bytes(bad))
    transport.inject(RS422_0, bytes(16))                                   # tanınmayan paket

    print("  monitor (sonra):", [str(r) for r in monitor.check()])
    print(f"  status: geçerli={status.rx_state.count} hatalı={status.rx_state.errors} "
          f"taze={status.rx_state.is_fresh()}")


if __name__ == "__main__":
    main()
