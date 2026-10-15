# iPod Manager

A simple, friendly Windows app to manage music on a **classic iPod** — no iTunes required. Edit tags, create playlists, download music from YouTube Music and sync it straight to your device.

Tested on an **iPod Nano 1st gen (2 GB)** — should work with other classic iPods supported by [pygpod](https://pypi.org/project/pygpod/).

[![☕ Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-rpf16rj-orange)](https://www.buymeacoffee.com/rpf16rj)

---

## Download

Grab the latest **`iPodManager.exe`** from [Releases](../../releases) — it's a single-file standalone executable, no Python or install needed. Just plug in your iPod and run it.

## Features

### iPod management
- **Auto-detection** — finds connected iPods (drives containing `iPod_Control`) on startup or via *Detect iPod* (`F5`)
- **Device info** — model, capacity, free space, track and playlist counts in the toolbar
- **Add music** — via the *Add files* button or by **drag & drop** of files or whole folders (recursive scan) onto the window
- **Automatic conversion** — FLAC, OGG, Opus, WMA, APE, WebM and other unsupported formats are converted to MP3 with the bundled ffmpeg
- **Remove tracks** — deletes from the database *and* frees the disk space (with per-item progress)
- **Export tracks** — copy music from the iPod back to a PC folder (`Artist - Title.ext`)
- **Safe writes** — changes are only committed on *Save to iPod* (`Ctrl+S`), which backs up the iTunesDB first and rolls back on failure
- **Orphan cleanup** — detects files copied to the iPod but never saved to the database and offers to remove them
- **Protected exit** — the app won't close with unsaved changes (save or cancel)
- **Eject** — saves and prepares the device for safe removal

### Library & metadata
- **Inline editing** — double-click a cell to edit title, artist, album, genre, year, track number and star rating
- **Bulk edit** — apply artist/album/genre/year/rating to all selected tracks at once (checkbox per field)
- **Resizable & hideable columns** — drag the header separators; right-click the header to show/hide columns; the layout persists between sessions
- **Rich columns** — including file **Size**, **Added** date and the **Playlists** each track belongs to
- **Sorting & filtering** — click any column header to sort; live filter box
- **Visual feedback** — per-item progress ("Adding 7/25 — name.mp3"), green flash on newly added rows, smooth animated progress bar, wait cursor during operations

### Playlists
- **Create / rename / delete** playlists on the iPod
- **Smart delete** — when deleting a playlist, optionally also delete its tracks (only those not in other playlists)
- **Drop-aware** — dropping files while a playlist is open adds them to *that* playlist; drop files or table tracks directly onto a playlist name
- **Reorder/add/remove** tracks inside playlists

### YouTube Music
- **Search** songs and check individual results for download
- **Load public playlists** by URL or ID
- **Download** selected tracks, all results, or a whole playlist — as **MP3 192 kbps** with ID3v2.3 tags and embedded artwork
- **Per-track queue** — live progress per item, visible failure reasons, **retry failed** and **cancel** buttons
- **Direct to iPod** — optionally send downloads straight to the device; downloaded playlists automatically create a same-named playlist on the iPod (reused on retries)
- **Save prompt** — after copying to the iPod, offers to save immediately so tracks don't become orphans
- Downloads land in a **`downloads\`** folder next to the executable

### Interface
- **Dark modern theme** with green/cyan accents, styled tables, lists, menus and scrollbars
- **Animations** — window fade-in, animated progress, row flash
- **Log dock** — live application log with verbose (DEBUG) toggle; also written to `%APPDATA%\iPodManager\ipodmanager.log`
- **Keyboard shortcuts** — `Ctrl+S` save, `F5` detect, `Del` remove selected
- **Bilingual** — Português (BR) and English, selectable in *Options → Language*

## Usage

1. Plug in the iPod (classic models — Nano, Video, etc.)
2. Open `iPodManager.exe` — it auto-detects the device
3. Manage music in the central table; playlists on the left; YouTube Music downloads on the right
4. Click **Save to iPod** (`Ctrl+S`) to commit changes — always with an automatic iTunesDB backup

## Build from source

```bat
git clone https://github.com/rpf16rj/ipod-manager.git
cd ipod-manager
pip install -r requirements.txt
python main.py
```

Build the executable:

```bat
pip install pyinstaller
python -m PyInstaller iPodManager.spec --noconfirm
```

Output: `dist\iPodManager.exe` (one-file, ~104 MB — includes Python, PySide6, yt-dlp, pygpod, mutagen and ffmpeg).

### Tests

```bat
pytest
```

Tests that require a real device are skipped automatically when no iPod is connected.

## Tech stack

| Component | Role |
|---|---|
| Python 3.14 + PySide6 | UI (QThreads keep it responsive) |
| pygpod | iTunesDB read/write, HASH58 signing, playlist ops |
| ytmusicapi | YouTube Music search & public playlists |
| yt-dlp | Downloads |
| imageio-ffmpeg | Bundled ffmpeg (conversion to MP3) |
| mutagen | ID3v2.3 tags + embedded artwork |
| PyInstaller | One-file Windows executable |

## Architecture

```
main.py                     entry point
ipod_manager/
  ipod_service.py           iPod backend (pygpod facade, backups, orphans)
  downloader.py             YT Music client + yt-dlp + ffmpeg + tagging
  i18n.py                   pt/en string table (tr())
  gui/
    app.py                  MainWindow, panels, dialogs, drag & drop
    workers.py              QObject workers on QThreads (signals)
    theme.py                dark QSS theme + animation helpers
    bulk_edit.py            bulk metadata edit dialog
specs/                      requirements / design / tasks (spec-driven)
tests/                      pytest suite + manual integration scripts
.github/workflows/          release pipeline (builds exe on tags)
```

## Disclaimer

Downloading content from YouTube is intended for **personal use** — respect the copyright of the artists and the YouTube Music terms of service.

## Support

This app is free and made with care. If it helped you, consider [buying me a coffee](https://www.buymeacoffee.com/rpf16rj) ☕ — it keeps the project alive!
