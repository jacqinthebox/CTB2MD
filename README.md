# CTB2MD - CherryTree to Obsidian Converter

Convert CherryTree notes to Obsidian-compatible Markdown files with hierarchical folder structure.

## Features

- Supports all CherryTree formats: `.ctb`, `.ctz`, `.ctd`, `.ctx`
- Password-protected files supported
- Preserves folder hierarchy (nodes with children become folders)
- Skips empty nodes (no empty .md files created)
- Remembers last used input/output folders
- Native macOS app available

## Installation

### Option 1: Use the compiled app

Copy `CTB2MD.app` from `dist/` to your Applications folder:

```bash
cp -r dist/CTB2MD.app /Applications/
```

### Option 2: Run from source

#### Prerequisites

**Python with tkinter support is required.**

If you use pyenv, you need to rebuild Python with tkinter:

```bash
# Install tcl-tk
brew install tcl-tk

# Uninstall current Python version
pyenv uninstall 3.13.3  # or your version

# Reinstall with tkinter support
export LDFLAGS="-L/opt/homebrew/opt/tcl-tk/lib"
export CPPFLAGS="-I/opt/homebrew/opt/tcl-tk/include"
export PKG_CONFIG_PATH="/opt/homebrew/opt/tcl-tk/lib/pkgconfig"
export PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I/opt/homebrew/opt/tcl-tk/include' --with-tcltk-libs='-L/opt/homebrew/opt/tcl-tk/lib -ltcl9.0 -ltk9.0'"

pyenv install 3.13.3

# Verify tkinter works
python -c "import tkinter; print('tkinter OK')"
```

#### Setup

```bash
cd CTB2MD
python -m venv venv
source venv/bin/activate
pip install py7zr
```

#### Run

```bash
source venv/bin/activate
python ctb2md_hierarchical.py
```

Or add an alias to `~/.zshrc`:

```bash
alias ctb2md="cd ~/path/to/CTB2MD && source venv/bin/activate && python ctb2md_hierarchical.py"
```

## Usage

1. Launch the app (or run the script)
2. Select your CherryTree file (`.ctb`, `.ctz`, `.ctd`, or `.ctx`)
3. Choose the output folder (e.g., your Obsidian vault)
4. If the file is password-protected, enter the password
5. Markdown files are created preserving your note hierarchy

## Output Structure

```
Output folder/
├── Category 1/
│   ├── Topic A/
│   │   ├── Note 1.md
│   │   └── Note 2.md
│   └── Topic B/
│       └── Note 3.md
└── Category 2/
    └── Topic C.md
```

- Nodes with children become folders
- Nodes with content become `.md` files
- Empty nodes are skipped

## Settings

Settings are saved automatically:

| Mode | Location |
|------|----------|
| Script | `./settings.json` |
| Compiled app | `~/Library/Application Support/CTB2MD/settings.json` |

To reset settings, delete the `settings.json` file.

## Building the App

```bash
source venv/bin/activate
pip install pyinstaller
pyinstaller -y --onedir --windowed --name "CTB2MD" ctb2md_hierarchical.py
```

The app will be created in `dist/CTB2MD.app`.

## File Format Support

| Extension | Format | Support |
|-----------|--------|---------|
| `.ctb` | SQLite database | Yes |
| `.ctz` | SQLite + password | Yes |
| `.ctd` | XML | Yes |
| `.ctx` | XML + password | Yes |

## System Requirements

- macOS 10.15 (Catalina) or later
- Apple Silicon (M1/M2/M3/M4) or Intel processor

## License

MIT
