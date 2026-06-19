# Custom fonts

Drop a sci-fi font file (`.ttf` or `.otf`) in this folder and it will be loaded
automatically at startup and used as the app's UI font (it takes priority over
the built-in fallback stack in `ui/theme.py`).

Good free options (SIL Open Font License):
- **Orbitron** — https://fonts.google.com/specimen/Orbitron
- **Rajdhani** — https://fonts.google.com/specimen/Rajdhani

Example: download `Orbitron-Regular.ttf` and place it here as
`assets/fonts/Orbitron-Regular.ttf`.

If no font is present here, the app falls back to Bahnschrift (Windows 11),
then Consolas, then Segoe UI.
