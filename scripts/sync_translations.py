#!/usr/bin/env python3
"""Generate translations/en.json from strings.json.

Home Assistant reads user-facing text from `translations/<lang>.json`, while
hassfest and the frontend's development flow read `strings.json`. For English the
two files have identical contents, so keeping both by hand means keeping two
copies of every sentence in step - which lasted exactly one round of edits before
they drifted.

`strings.json` is the single source. This script copies it, and `--check` makes
CI fail if the copy is stale instead of shipping a half-translated UI.

    python3 scripts/sync_translations.py            # write translations/en.json
    python3 scripts/sync_translations.py --check    # verify, exit 1 if stale

Other languages are hand-written and are not touched; they are only checked for
being valid JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "rover_client"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations"
EN = TRANSLATIONS / "en.json"


def render(strings: dict) -> str:
    """Return the exact text en.json should hold for these strings."""
    return json.dumps(strings, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    """Write or verify translations/en.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if en.json is not what strings.json would produce",
    )
    args = parser.parse_args()

    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    expected = render(strings)

    for path in sorted(TRANSLATIONS.glob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            print(f"{path.name} is not valid JSON: {err}", file=sys.stderr)  # noqa: T201
            return 1

    current = EN.read_text(encoding="utf-8") if EN.exists() else None

    if args.check:
        if current != expected:
            print(  # noqa: T201
                "translations/en.json is out of date with strings.json.\n"
                "Run: python3 scripts/sync_translations.py",
                file=sys.stderr,
            )
            return 1
        print("translations/en.json is in sync with strings.json")  # noqa: T201
        return 0

    if current == expected:
        print("translations/en.json already up to date")  # noqa: T201
        return 0

    TRANSLATIONS.mkdir(exist_ok=True)
    EN.write_text(expected, encoding="utf-8")
    print("Wrote translations/en.json from strings.json")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
