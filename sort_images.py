"""
Sorts images into category folders with CLIP (runs locally on the GPU, no API).

Pick a folder, it classifies every image, shows how many land in each category and saves preview sheets,
then asks before moving anything. Every move is logged in <DEST>/sort_log.csv (see undo_sort.py).

    sort_images.bat                                  (folder picker)
    python sort_images.py <folder> [--sub] [--dest D] [--dry-run]

Settings, in order of precedence: command-line flag, environment variable, default.
    --dest         SORT_DEST         where category folders are created   (default ~/Pictures/Sorted)
    --start-dir    SORT_START_DIR    folder the picker opens in           (default ~/Pictures)
    --categories   SORT_CATEGORIES   category definitions                 (default categories.json next to this file)
    --model        SORT_MODEL        any Hugging Face CLIP model          (default openai/clip-vit-large-patch14)
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
EXTS = (".png", ".jpg", ".jpeg", ".webp")
BATCH = 64


def parse_args():
    pictures = str(Path.home() / "Pictures")
    ap = argparse.ArgumentParser(description="Sort images into category folders with CLIP.")
    ap.add_argument("folder", nargs="?", help="folder of images to sort (omit to use the folder picker)")
    ap.add_argument("--sub", action="store_true", help="include subfolders")
    ap.add_argument("--dest", default=os.environ.get("SORT_DEST") or str(Path(pictures) / "Sorted"))
    ap.add_argument("--start-dir", default=os.environ.get("SORT_START_DIR") or pictures)
    ap.add_argument("--categories", default=os.environ.get("SORT_CATEGORIES") or str(HERE / "categories.json"))
    ap.add_argument("--model", default=os.environ.get("SORT_MODEL") or "openai/clip-vit-large-patch14")
    ap.add_argument("--dry-run", action="store_true", help="classify and write preview sheets, but never move anything")
    return ap.parse_args()


def load_categories(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["categories"], cfg.get("nsfw_category"), cfg.get("nsfw_min", 0.40), cfg.get("other_below", 0.22)


def pick_folder(start_dir):
    """Folder dialog: PowerShell on Windows (embedded Pythons have no tkinter), tkinter elsewhere."""
    if os.name == "nt":
        ps = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8;"  # so folder names with å, ä, ö come back intact
              "Add-Type -AssemblyName System.Windows.Forms;"
              "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
              "$d.Description = 'Choose a folder of images to sort';"
              "$d.SelectedPath = $env:SORT_PICK_START;"
              "if ($d.ShowDialog((New-Object System.Windows.Forms.Form -Property @{TopMost=$true})) -eq 'OK') { $d.SelectedPath }")
        out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True,
                             encoding="utf-8", env={**os.environ, "SORT_PICK_START": start_dir})
        return out.stdout.strip()
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        return filedialog.askdirectory(initialdir=start_dir, title="Choose a folder of images to sort")
    except Exception:
        return input("Folder of images to sort: ").strip().strip('"')


def open_folder(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
    except Exception:
        pass  # opening the previews is a convenience only


def list_images(folder, sub):
    if sub:
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(folder) for f in fs if f.lower().endswith(EXTS))
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(EXTS))


def features(out):
    """Newer transformers return an output object instead of the embedding tensor."""
    import torch
    return out if torch.is_tensor(out) else out.pooler_output


def classify(paths, categories, nsfw_name, nsfw_min, other_below, model_name, progress=None, cancelled=None):
    """Returns [(path, category, score)]. progress(done, total) and cancelled() are optional hooks for a UI;
    a cancelled run returns None. The heavy imports live here so other code can import this module without torch."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading CLIP on {device} (the first run downloads about 1.7 GB)...")
    model = CLIPModel.from_pretrained(model_name, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device).eval()
    proc = CLIPProcessor.from_pretrained(model_name)
    names = list(categories)
    texts = [t for n in names for t in categories[n]]
    owner = torch.tensor([i for i, n in enumerate(names) for _ in categories[n]], device=device)
    with torch.no_grad():
        t = proc(text=texts, return_tensors="pt", padding=True).to(device)
        tf = features(model.get_text_features(**t))
        tf = tf / tf.norm(dim=-1, keepdim=True)

    results, started = [], time.time()
    for i in range(0, len(paths), BATCH):
        if cancelled and cancelled():
            return None
        chunk, imgs = [], []
        for p in paths[i:i + BATCH]:
            try:
                with Image.open(p) as im:
                    imgs.append(im.convert("RGB"))
                chunk.append(p)
            except Exception as e:
                print(f"  skipped {p}: {e}")
        if not imgs:
            continue
        with torch.no_grad():
            x = proc(images=imgs, return_tensors="pt")["pixel_values"].to(device, model.dtype)
            f = features(model.get_image_features(pixel_values=x))
            f = f / f.norm(dim=-1, keepdim=True)
            sims = (f @ tf.T).float() * 100
            best = torch.full((len(imgs), len(names)), -1e9, device=device)
            best = best.scatter_reduce(1, owner.expand(len(imgs), -1), sims, reduce="amax")
            probs = best.softmax(dim=1)
        for p, pr in zip(chunk, probs.tolist()):
            top = max(range(len(names)), key=lambda k: pr[k])
            cat = names[top]
            if nsfw_name in names and pr[names.index(nsfw_name)] >= nsfw_min:
                cat = nsfw_name  # wins whenever it gets at least this share, even if another category scores higher
            elif pr[top] < other_below:
                cat = "other"
            results.append((p, cat, round(pr[top], 3)))
        done = min(i + BATCH, len(paths))
        print(f"  {done}/{len(paths)}  ({done / max(time.time() - started, 0.01):.0f} images/s)", end="\r")
        if progress:
            progress(done, len(paths))
    print()
    return results


def preview_sheets(results, dest, folder_name):
    """Up to 48 thumbnails per category, to check the sorting before anything moves."""
    out = os.path.join(dest, "_previews", folder_name)
    os.makedirs(out, exist_ok=True)
    for cat in sorted({c for _, c, _ in results}):
        items = [p for p, c, _ in results if c == cat][:48]
        cell, cols = 200, 8
        sheet = Image.new("RGB", (cols * cell, ((len(items) + cols - 1) // cols) * cell), (20, 20, 20))
        for k, p in enumerate(items):
            try:
                with Image.open(p) as im:
                    im.draft("RGB", (cell * 2, cell * 2))
                    im = im.convert("RGB")
                    im.thumbnail((cell, cell))
                    sheet.paste(im, ((k % cols) * cell + (cell - im.width) // 2, (k // cols) * cell + (cell - im.height) // 2))
            except Exception:
                pass
        sheet.save(os.path.join(out, f"{cat}.jpg"), quality=80)
    return out


def unique_path(folder, name):
    path, n = os.path.join(folder, name), 2
    stem, ext = os.path.splitext(name)
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}_{n}{ext}")
        n += 1
    return path


def move_all(results, folder, dest):
    os.makedirs(dest, exist_ok=True)
    log_path = os.path.join(dest, "sort_log.csv")
    new_log = not os.path.exists(log_path)
    tag = os.path.basename(os.path.normpath(folder))
    # Re-sorting a category folder inside dest keeps the names (they already have their source prefix)
    resort = os.path.normcase(os.path.abspath(folder)).startswith(os.path.normcase(os.path.abspath(dest)) + os.sep)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["time", "from", "to", "category", "score"])
        for p, cat, score in results:
            target_dir = os.path.join(dest, cat)
            if os.path.normcase(os.path.dirname(os.path.abspath(p))) == os.path.normcase(os.path.abspath(target_dir)):
                continue  # already in the right folder
            os.makedirs(target_dir, exist_ok=True)
            # The source folder's name goes in front, so files from different folders don't clash
            # and you can still see where an image came from
            name = os.path.basename(p) if resort else f"{tag}_{os.path.basename(p)}"
            target = unique_path(target_dir, name)
            shutil.move(p, target)
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), p, target, cat, score])
    return log_path


def main():
    args = parse_args()
    categories, nsfw_name, nsfw_min, other_below = load_categories(args.categories)
    folder = args.folder or pick_folder(args.start_dir)
    if not folder or not os.path.isdir(folder):
        print("No valid folder chosen.")
        return
    sub = args.sub
    if not args.folder:
        has_sub = any(os.path.isdir(os.path.join(folder, d)) for d in os.listdir(folder))
        if has_sub:
            sub = input("This folder has subfolders. Include them? (y/n): ").strip().lower() == "y"
    paths = list_images(folder, sub)
    print(f"\n{len(paths)} images in {folder}" + (" (with subfolders)" if sub else ""))
    if not paths:
        input("Nothing to sort. Press Enter to close.")
        return

    results = classify(paths, categories, nsfw_name, nsfw_min, other_below, args.model)
    counts = {}
    for _, c, _ in results:
        counts[c] = counts.get(c, 0) + 1
    print("\nWould move:")
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:6}  {c}")
    sheets = preview_sheets(results, args.dest, os.path.basename(os.path.normpath(folder)))
    print(f"\nPreview sheets (up to 48 per category): {sheets}")
    open_folder(sheets)

    if args.dry_run:
        print("Dry run: nothing was moved.")
    elif input(f"\nMove {len(results)} images to {args.dest}? (y/n): ").strip().lower() != "y":
        print("Nothing was moved.")
    else:
        log = move_all(results, folder, args.dest)
        print(f"Done. Every move is listed in {log}")
    input("Press Enter to close.")


if __name__ == "__main__":
    main()
