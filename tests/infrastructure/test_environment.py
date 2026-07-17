from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil

from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions
from jatibarang_ccus.surrogate.config import REPO_ROOT


def test_real_infrastructure_dependencies_and_terrain_are_available() -> None:
    for module in ["CoolProp", "pyomo", "networkx", "rasterio", "shapely", "pyproj", "pydantic"]:
        assert importlib.util.find_spec(module) is not None, module
    assert shutil.which("cbc") is not None

    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    raster = REPO_ROOT / assumptions["routing"]["terrain_raster_path"]
    digest = hashlib.sha256()
    with raster.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest().upper() == assumptions["routing"]["terrain_sha256"]
