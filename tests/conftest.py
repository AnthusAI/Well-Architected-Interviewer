import importlib.util
from pathlib import Path

import pytest


def load_wai():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills/well-architected-interviewer/scripts/wai.py"
    spec = importlib.util.spec_from_file_location("wai", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def wai():
    return load_wai()


@pytest.fixture()
def ctx(tmp_path):
    return {"tmp_path": tmp_path}
