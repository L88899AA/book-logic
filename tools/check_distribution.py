"""Check built archives without extracting their contents."""
import argparse
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def check(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            members = [(n, archive.read(n)) for n in archive.namelist() if not n.endswith("/")]
    else:
        with tarfile.open(path) as archive:
            members = [(m.name.split("/", 1)[-1], archive.extractfile(m).read()) for m in archive.getmembers() if m.isfile()]
    for name, content in members:
        parts = PurePosixPath(name).parts
        assert not name.startswith("/") and ".." not in parts, name
        checked_parts = parts[2:] if path.suffix == ".whl" and parts[0].endswith(".data") and parts[1] == "data" else parts
        assert not any(p in {"data", "reports", ".venv", "__pycache__", "local-library", "demo-library", "workspace", "archive", ".cache"} for p in checked_parts), name
        assert not name.endswith((".sqlite", ".db", ".pdf", ".safetensors", ".pyc", ".npy")), name
        assert PurePosixPath(name).name not in {"config.json", "booklogic.py", "queries.json", "evaluation_queries.json"}, name
        assert b"/Users/" not in content and b"z-library.sk" not in content, name
        if path.suffix == ".whl":
            assert parts[0] == "book_logic" or parts[0].endswith((".dist-info", ".data")), name
        else:
            assert parts[0] in {"src", "skills"} or name in {"README.md", "DIRECTORY.md", "LICENSE", "THIRD_PARTY.md", "pyproject.toml", "processing-policy.json", "MANIFEST.in", "PKG-INFO", "setup.cfg"}, name
    assert any(n.endswith("SKILL.md") for n, _ in members), "Missing Skill"
    assert any(n.endswith("schemas/submission.json") for n, _ in members), "Missing schema"
    assert any(n.endswith("processing-policy.json") for n, _ in members), "Missing processing policy"
    assert any(n.endswith("references/quality.md") for n, _ in members), "Missing quality protocol"
    print(f"PASS {path.name}: {len(members)} public files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    archives = sorted(args.directory.glob("*.whl")) + sorted(args.directory.glob("*.tar.gz"))
    assert archives, "No distribution archives found"
    for path in archives:
        check(path)
