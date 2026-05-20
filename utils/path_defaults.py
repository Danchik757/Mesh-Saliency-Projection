from __future__ import annotations

import os
from pathlib import Path


def resolve_dataset_root(
    cli_value: Path | None,
    *,
    env_var: str,
    dataset_name: str,
    example_path: str | None = None,
) -> Path:
    if cli_value is not None:
        return cli_value.expanduser().resolve()

    env_value = os.environ.get(env_var)
    if env_value:
        return Path(env_value).expanduser().resolve()

    message = (
        f"{dataset_name} dataset root is not set. "
        f"Pass --dataset-root or set the environment variable {env_var}."
    )
    if example_path:
        message += f" Example local path: {example_path}"
    raise SystemExit(message)
