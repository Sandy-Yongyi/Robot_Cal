"""Prepare the capture-only SDK from the Full_Featured_Edition source checkout."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("lidar", "dataprocess", "formats", "pointcloud")


def sync(upstream):
    package = ROOT / "acquisition_sdk"
    sources = upstream / "acquisition_sdk" / "_internal"
    groups = [sorted((sources / component).rglob("*.py")) for component in COMPONENTS]
    if not all(groups):
        raise FileNotFoundError(f"Upstream SDK sources missing under {sources}")
    files = {path.relative_to(sources).as_posix(): path for group in groups for path in group}
    files["compat/FrameFifoConfig.py"] = upstream / "model/utils/FrameFifoConfig.py"
    upstream_hashes = {}
    for name, path in files.items():
        raw = path.read_bytes()
        upstream_hashes[name] = hashlib.sha256(raw).hexdigest()
        source = raw.decode("utf-8-sig").replace("\r\n", "\n")
        source = source.replace("from model.utils.FrameFifoConfig import", "from acquisition_sdk._internal.compat.FrameFifoConfig import")
        if path.name == "__init__.py" and source.strip():
            raise ValueError(f"SDK internal initializer must be empty: {path}")
        destination = package / "_internal" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    for directory in ("_internal", "_internal/compat"):
        (package / directory / "__init__.py").touch()
    manifest = package / "upstream.json"
    manifest.write_text(json.dumps(upstream_hashes, indent=2, sort_keys=True), encoding="utf-8")
    # Refuse unexpected implementations so stale files cannot enter the build.
    from_files = {"_internal/" + name for name in files}
    actual = {p.relative_to(package).as_posix() for p in (package / "_internal").rglob("*.py")
              if p.name != "__init__.py"}
    if actual != {name for name in from_files if not name.endswith("/__init__.py")}:
        raise ValueError("Unexpected files in generated SDK source directory")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Path to Full_Featured_Edition")
    print(sync(parser.parse_args().upstream.resolve()))

