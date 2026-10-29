# image-sorter

Sorts a folder of images (png, jpg, webp) into category folders such as portraits, landscapes, anime and horror.
It uses [CLIP](https://huggingface.co/openai/clip-vit-large-patch14) locally on your GPU (or CPU). There are no API calls and nothing leaves your machine.

How it works:

1. You pick a folder.
2. Every image is classified and you see how many land in each category.
3. Preview sheets (up to 48 thumbnails per category) are saved and opened so you can check the result.
4. **Nothing moves until you answer `y`.** Every move is logged in `sort_log.csv` in the destination folder and can be undone.

## Install

You need Python 3.9 or newer.

**Windows**

```bat
setup.bat
```

This creates a local `venv` and installs the requirements. For an NVIDIA GPU, install a CUDA build of torch first. The command is in `setup.bat`, and the selector is at <https://pytorch.org/get-started/locally/>.

**Anywhere else**

```bash
pip install -r requirements.txt
```

The first run downloads the CLIP model (about 1.7 GB).

## Use

Windows: double-click `Sort_images.bat` to get a folder picker, or run it from a terminal with options.
Any OS:

```bash
python sort_images.py                      # folder picker
python sort_images.py /path/to/folder      # skip the picker
python sort_images.py /path/to/folder --sub --dest /path/to/sorted
python sort_images.py /path/to/folder --dry-run
```

| Option | Environment variable | Default |
| --- | --- | --- |
| `--dest` | `SORT_DEST` | `~/Pictures/Sorted` |
| `--start-dir` (where the picker opens) | `SORT_START_DIR` | `~/Pictures` |
| `--categories` | `SORT_CATEGORIES` | `categories.json` next to the script |
| `--model` | `SORT_MODEL` | `openai/clip-vit-large-patch14` |
| `--sub` (include subfolders) | | off |
| `--dry-run` (previews only, never moves) | | off |

Files are moved to `<dest>/<category>/` and renamed `<source folder name>_<file name>`, so images from different folders never clash and you can see where each came from.

### Using ComfyUI's Python (or any other Python)

Point `SORT_PYTHON` at the interpreter before running the `.bat`:

```bat
set SORT_PYTHON=C:\path\to\ComfyUI_windows_portable\python_embeded\python.exe
Sort_images.bat
```

Set it permanently with `setx SORT_PYTHON "..."`. It needs `transformers` installed (`python -m pip install transformers`).

## Undo

```bash
python undo_sort.py <dest>/sort_log.csv --dry-run     # see what would be restored
python undo_sort.py <dest>/sort_log.csv --last-run    # restore only the most recent sort
python undo_sort.py <dest>/sort_log.csv               # restore everything
```

## Customising categories

Edit `categories.json`. Each category has a list of text descriptions, and an image scores as well as its best-matching description. More varied descriptions work better than one long one. Other settings in the same file:

- `other_below`: if the best category scores below this share, the image goes to `other`.
- `nsfw_category` and `nsfw_min`: the category with this name wins whenever it gets at least this share, even if another category scores higher. Set `nsfw_category` to `null` to turn the rule off.

**Note:** the default category list includes an `nsfw` category with explicit descriptions, so explicit images are kept apart from the rest. Delete it from `categories.json` if you don't want it.

## Notes

- Always check the preview sheets first. CLIP is good at this but not perfect.
- The folder picker uses PowerShell on Windows and tkinter elsewhere. If neither works, you are asked to type the path.

## License

MIT
