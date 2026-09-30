"""Package the public Git file set without local inputs or runtime caches."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / (ROOT.name + ".zip")
MANIFEST = ROOT / "output" / "bundle_manifest.json"
EXCLUDED_DIRS = {".git", ".venv", "tmp", "__pycache__", ".ipynb_checkpoints",
                 "sources", "passport-pages"}
EXCLUDED_NAMES = {".DS_Store", "group_passport.txt", ".env"}


def include(path):
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS or part.startswith('.venv') for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path == MANIFEST:
        return False
    if path.name.startswith('.env.') and path.name != '.env.example':
        return False
    return path.is_file() and not path.is_symlink()


def main():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    paths = sorted({ROOT / name for name in names if name and include(ROOT / name)})
    records = [{"path": str(path.relative_to(ROOT)),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in paths]
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Hashes cover shipped files except this manifest itself.",
                "files": records}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    temp_path = DEST.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths + [MANIFEST]:
            archive.write(path, ROOT.name + "/" + str(path.relative_to(ROOT)))
    temp_path.replace(DEST)
    with zipfile.ZipFile(DEST) as archive:
        assert archive.testzip() is None
        for record in records:
            content = archive.read(ROOT.name + "/" + record["path"])
            assert hashlib.sha256(content).hexdigest() == record["sha256"]
    print(f"Verified {len(records)} file hashes; archive: {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
