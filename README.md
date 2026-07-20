# Duplicate Image Scanner

A Streamlit web application that uses **Perceptual Hashing** to detect duplicate and similar images in your file system.

## Features

- 🖼️ Scans folders recursively for images
- 🔍 Uses perceptual hashing to identify visually similar images (not just identical files)
- 📊 Displays results with image previews
- 🧭 Single-group navigation and multi-group per page view
- 🗑️ Delete, "Delete and continue", and "Keep this, delete others" bulk actions
- ✅ Confirmation prompts for destructive actions
- 🗂️ Trash & Undo buffer (moves deleted files to a trash folder and supports restore)
- ♻️ Optional system Trash/Recycle Bin integration via send2trash
- ⏲️ Auto-purge trashed items older than configurable days (default: 30 days)
- 🚦 Progress tracking and responsive UI powered by Streamlit

## Supported Formats

- JPG / JPEG
- PNG
- WebP
- BMP
- GIF (preview support)

## Requirements

- Python 3.7+
- streamlit
- Pillow
- ImageHash
- send2trash (optional — required only to enable sending deletes to the OS Trash/Recycle Bin)

The project ships a requirements.txt with the core dependencies. Install optional send2trash if you want system Trash support:

```bash
pip install send2trash
```

## Installation

1. Clone this repository:

```bash
git clone https://github.com/WanderingFrogg/duplicate-image-scanner.git
cd duplicate-image-scanner
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (cmd.exe)
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
# Optional: enable system Trash integration
pip install send2trash
```

## Usage

Run the application:

```bash
streamlit run dupscan.py
```

Workflow:

1. Choose or paste a folder path to scan.
2. Start a scan — the app will compute perceptual hashes and find duplicate groups.
3. Use the UI to inspect groups (single-group navigation or multiple groups per page).
4. Delete copies (they will be moved to a local trash folder or system Trash if enabled).
5. Use the Trash & Undo panel to preview trashed images, restore selected items, or permanently delete them.

## Undo & Persistence

- Deleted files are moved to a local trash folder at `<scanned-folder>/.duplicate_trash/` (or `~/.duplicate_trash/` if no scanned folder is stored) unless system Trash is enabled.
- An `undo.json` index is stored alongside the trash contents so the app remembers trashed items across restarts. If you restart the app, the Trash & Undo panel will show previous deletions.
- Files in system Trash (when send2trash is used) are recorded in the undo index but cannot be restored by the app due to OS limitations.

## Cross-platform notes

- macOS: Uses an AppleScript folder picker for Browse; send2trash sends to the macOS Trash when installed.
- Windows: Uses tkinter filedialog for Browse; send2trash sends to the Recycle Bin when installed.
- Linux: Uses tkinter filedialog for Browse (install `python3-tk` on some distributions). send2trash support depends on the desktop environment.

All file operations use Python standard libraries (shutil, os) and are compatible across platforms; edge cases such as file locks or permission errors are reported in the UI.

## Security & Safety

- Deletions are not permanent until you choose to permanently empty the app's trash or use "Empty Trash (permanent)". The default behavior is to move files to a recoverable location.
- The Undo index is best-effort persisted to disk. If `undo.json` is deleted externally, the app will recreate it as needed.

## License

MIT

## Contributing

Contributions are welcome! Feel free to submit issues and pull requests.
