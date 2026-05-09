from __future__ import annotations

"""
logger.py

Összegyűjti a projekt összes .py fájljának tartalmát,
és egyetlen text fájlba menti debug / audit célra.

Használat:
    python logger.py

Alapértelmezett output:
    python_code_dump.txt
"""

from pathlib import Path
from datetime import datetime


# Melyik mappát vizsgálja
ROOT_DIR = Path(__file__).parent

# Output fájl
OUTPUT_FILE = ROOT_DIR / "python_code_dump.txt"

# Kihagyott mappák
EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
}


def should_skip(path: Path) -> bool:
    """Megnézi, hogy a fájlt/mappát ki kell-e hagyni."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def collect_python_files(root: Path) -> list[Path]:
    """Összegyűjti az összes .py fájlt."""
    py_files: list[Path] = []

    for file in root.rglob("*.py"):
        if should_skip(file):
            continue

        py_files.append(file)

    return sorted(py_files)


def write_dump(py_files: list[Path], output_file: Path) -> None:
    """Kiírja az összes Python fájl tartalmát egy text fájlba."""

    with output_file.open("w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("PYTHON SOURCE DUMP\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")

        for py_file in py_files:
            relative_path = py_file.relative_to(ROOT_DIR)

            f.write("#" * 80 + "\n")
            f.write(f"FILE: {relative_path}\n")
            f.write("#" * 80 + "\n\n")

            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = py_file.read_text(encoding="latin-1")

            f.write(content)
            f.write("\n\n")

    print(f"\nOK - {len(py_files)} Python fájl exportálva ide:")
    print(output_file)


def main() -> None:
    py_files = collect_python_files(ROOT_DIR)

    if not py_files:
        print("Nem található Python fájl.")
        return

    print(f"Talált Python fájlok: {len(py_files)}")

    write_dump(py_files, OUTPUT_FILE)


if __name__ == "__main__":
    main()
