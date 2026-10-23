#!/usr/bin/env python3
"""Package the Windows and Mac installers without environments or credentials."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent


def main():
    output_dir = ROOT / "dist"
    output_dir.mkdir(exist_ok=True)
    files = [ROOT / name for name in ("README.md", "WINDOWS.md", "Install-Windows.bat", "requirements.txt", "package.json", "package-lock.json", "AGENTS.md", ".gitignore", ".gitattributes")]
    files += [f for f in (ROOT / "scripts").iterdir() if f.suffix in (".py", ".mjs")]
    files += [f for f in (ROOT / "tests").iterdir() if f.suffix in (".py", ".mjs")]
    files += [f for f in (ROOT / "extension").iterdir() if f.is_file()]
    files += [f for f in (ROOT / "companion").iterdir() if f.suffix in (".py", ".bat")]
    for platform in ("windows", "macos"):
        output = output_dir / f"InstantVideoDownloader-{platform}.zip"
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            for file in sorted(files):
                name = (Path("InstantVideoDownloader") / file.relative_to(ROOT)).as_posix()
                if file.suffix == ".bat":
                    archive.writestr(name, file.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
                else:
                    archive.write(file, name)
        print(output)


if __name__ == "__main__":
    main()
