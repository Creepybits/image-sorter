"""
Moves images back to where they came from, using the sort_log.csv that sort_images.py writes.

    python undo_sort.py <dest>/sort_log.csv [--last-run] [--dry-run]

Without --last-run every logged move is undone; with it only the most recent run
(the rows whose timestamps are within a minute of the final row).
"""
import argparse
import csv
import os
import shutil
from datetime import datetime


def main():
    ap = argparse.ArgumentParser(description="Undo moves recorded in sort_log.csv.")
    ap.add_argument("log")
    ap.add_argument("--last-run", action="store_true", help="only undo the most recent sort")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.log, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.last_run and rows:
        fmt = "%Y-%m-%d %H:%M:%S"
        end = datetime.strptime(rows[-1]["time"], fmt)
        rows = [r for r in rows if (end - datetime.strptime(r["time"], fmt)).total_seconds() < 60]

    restored = 0
    for r in reversed(rows):
        src, dst = r["to"], r["from"]
        if not os.path.exists(src):
            print(f"missing, skipped: {src}")
            continue
        if os.path.exists(dst):
            print(f"original location is occupied, skipped: {dst}")
            continue
        print(f"{src} -> {dst}")
        if not args.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        restored += 1
    print(f"\n{restored} images {'would be ' if args.dry_run else ''}restored.")


if __name__ == "__main__":
    main()
