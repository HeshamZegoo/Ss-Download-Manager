# Ss Download Manager

A Windows-first download manager inspired by the supplied IDM-style HTML mockup.

## Current implementation

- Native desktop UI built with PySide6.
- Real HTTP/HTTPS downloads (not simulated progress).
- Pause and resume using HTTP Range when the server supports it.
- Download queue, per-download progress/speed, and persistent download history.
- Choose a destination folder and open completed files.
- Windows executable packaging through GitHub Actions.

## Requirements

- Python 3.11+
- Windows 10/11 (development also works on Linux/macOS)
- See `requirements.txt`

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Build a Windows executable locally

```powershell
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name "Ss Download Manager" --collect-all PySide6 main.py
```

The executable is written to `dist/Ss Download Manager/`.

## GitHub Actions

Push to `main` or run **Build Windows EXE** manually from the Actions tab. The workflow builds a Windows x64 package and uploads it as an artifact. A tagged push (for example `v0.1.0`) also creates a GitHub Release.

## Important limitations

Resume depends on the remote server supporting byte-range requests and keeping the same resource. Some hosts require authentication, cookies, or signed URLs; those must be supplied by the user and may expire. This app does not bypass host, bandwidth, account, or legal restrictions. Multi-connection downloads, browser integration, video extraction, scheduling, and upload management are planned features, not claimed as implemented in this first working foundation.
