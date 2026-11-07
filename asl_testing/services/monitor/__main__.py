"""Offline monitor: opens the page without a running test, to import CommLogger CSV files.

    python -m asl_testing.services.monitor projects.example_project.header:ProjectBase projects.example_project.messages

Arguments: module:ProjectClass for each project, and the modules that define the message classes
(a CSV row is decoded with the class of the same name, so that class must be imported).
"""
import argparse
import importlib
import time

from asl_testing.services.monitor.service import MonitorService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("specs", nargs="+", help="module:ProjectClass, or a module with message classes")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()
    projects = []
    for spec in args.specs:
        module, _, name = spec.partition(":")
        imported = importlib.import_module(module)
        if name:
            projects.append(getattr(imported, name))
    monitor = MonitorService(None, projects, port=args.port)
    monitor.start()
    print(f"monitor (offline) on {monitor.url}  - File > Import CSV;  Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()


if __name__ == "__main__":
    main()
