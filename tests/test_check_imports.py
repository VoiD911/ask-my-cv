import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_imports.py"
spec = importlib.util.spec_from_file_location("check_imports", SCRIPT)
assert spec and spec.loader
check_imports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_imports)


def test_lists_every_runtime_module() -> None:
    modules = check_imports.runtime_modules()
    assert "ask_my_cv.app" in modules
    assert "ask_my_cv.aws.sigv4" in modules
    assert not any(m.startswith("ask_my_cv.tests") for m in modules)


def test_all_runtime_modules_import() -> None:
    assert check_imports.main() == 0
