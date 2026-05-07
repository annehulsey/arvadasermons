from pathlib import Path
import json

from .paths import SERMONS_PATH
from .libsyn_scrape import build_backfill


def save_fresh_jsonl(data, path: Path):
    with open(path, "w") as f:
        for row in data:
            f.write(json.dumps(row) + "\n")

    print(f"Rebuilt file with {len(data)} episodes")


def main():
    # --- SAFETY: only do this in backfill mode ---
    if SERMONS_PATH.exists():
        SERMONS_PATH.unlink()  # delete file

    data = build_backfill()

    save_fresh_jsonl(data, SERMONS_PATH)


if __name__ == "__main__":
    main()