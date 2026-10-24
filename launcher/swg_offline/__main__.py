"""Entry point: `python -m swg_offline` opens the launcher; `--cli` runs one session in the console."""

import argparse
import sys

from . import presets
from .session import Session, Stage
from .settings import Settings


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="swg_offline", description=__doc__)
    parser.add_argument("--cli", action="store_true", help="no window; print progress to the console")
    parser.add_argument("--swg-dir", help="your SWGEmu client folder")
    parser.add_argument("--preset", choices=sorted(presets.PRESETS))
    parser.add_argument("--account", help="account name to log in with")
    parser.add_argument("--zones", help="comma-separated ground zones, e.g. tutorial,tatooine,naboo")
    return parser.parse_args(argv)


def run_cli(settings: Settings) -> int:
    def status(stage: Stage, text: str) -> None:
        print(f"[{stage.name}] {text}" if text else f"[{stage.name}]", flush=True)
        result[0] = stage

    result = [None]
    session = Session(settings, status)
    try:
        session.run()
    except KeyboardInterrupt:
        session.cancel()
    return 0 if result[0] == Stage.DONE else 1


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = Settings.load()
    if args.swg_dir:
        settings.swg_dir = args.swg_dir
    if args.preset:
        settings.preset = args.preset
    if args.account:
        settings.account = args.account
    if args.zones:
        settings.zones = [z.strip() for z in args.zones.split(",") if z.strip()]

    if args.cli:
        settings.save()
        return run_cli(settings)

    from . import gui  # tkinter is only needed for the window
    gui.main(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
