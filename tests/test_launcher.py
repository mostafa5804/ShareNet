import importlib.util
from pathlib import Path


def test_launcher_can_import_src_package_without_pythonpath():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("sharenet_launcher_test", root / "launcher.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.main)
