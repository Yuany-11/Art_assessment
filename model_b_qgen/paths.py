"""项目根定位，兼容仓库布局与交付包布局。

- 仓库布局：`<根>/model_b_qgen` + `<根>/data`
- 交付包布局：`<根>/repo/model_b_qgen` + `<根>/data`
- 本地开发：`<项目>/repo/model_b_qgen` + `<项目>/data`
"""
from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    here = Path(__file__).resolve()
    for root in (here.parents[1], here.parents[2]):
        if (root / "data" / "09_qgen").is_dir():
            return root
    return here.parents[2]


PROJECT_ROOT = project_root()
