import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundled_runtime_hashes_are_expected():
    assert sha256(ROOT / "runtime/zeptun.exe") == (
        "acfe6a06385ca47a9767ef7cd898de60048084f56e954b9f2cf0d9c29f89017e"
    )
    assert sha256(ROOT / "runtime/wintun.dll") == (
        "e5da8447dc2c320edc0fc52fa01885c103de8c118481f683643cacc3220dafce"
    )
