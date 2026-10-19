#!/usr/bin/env python3
"""Package the Mac installer and application without environments or credentials."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent


def main():
    output = ROOT / "dist/InstantVideoDownloader-macos.zip"
    output.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in ("README.md", "requirements.txt", "package.json", "package-lock.json", "AGENTS.md", ".gitignore")]
    files += [f for f in (ROOT / "scripts").iterdir() if f.suffix == ".py"]
    files += [f for f in (ROOT / "tests").iterdir() if f.suffix in (".py", ".mjs")]
    files += [f for f in (ROOT / "extension").iterdir() if f.is_file()]
    files += [f for f in (ROOT / "companion").iterdir() if f.suffix == ".py"]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, Path("InstantVideoDownloader") / file.relative_to(ROOT))
    print(output)


if __name__ == "__main__":
    main()
