from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def safe_write_csv(df: pd.DataFrame, path, **kwargs) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")

    if tmp.exists():
        try:
            tmp.unlink()
        except (PermissionError, OSError):
            pass

    with open(tmp, "w", encoding="utf-8", newline="") as f:
        df.to_csv(f, **kwargs)
        f.flush()
        try:
            os.fsync(f.fileno())
        except (OSError, AttributeError):
            pass

    with open(tmp, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size > 0:
            f.seek(max(0, size - 1))
            if f.read(1) != b"\n":
                with open(tmp, "ab") as fa:
                    fa.write(b"\n")
                    fa.flush()
                    try:
                        os.fsync(fa.fileno())
                    except (OSError, AttributeError):
                        pass

    tmp.replace(path)
