import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import store  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    store.init_store(tmp_path)
    return tmp_path
