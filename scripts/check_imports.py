"""Importe chaque module d'exécution d'ask_my_cv : une dépendance manquante dans l'image échoue ici.

Lancé dans l'image construite (CI) :
`docker run --rm --entrypoint .venv/bin/python <image> scripts/check_imports.py`.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import ask_my_cv


def runtime_modules() -> list[str]:
    return sorted(
        info.name for info in pkgutil.walk_packages(ask_my_cv.__path__, prefix="ask_my_cv.")
    )


def main() -> int:
    failures = []
    for name in runtime_modules():
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"{name} : {type(exc).__name__}: {exc}")
    for failure in failures:
        print(failure, file=sys.stderr)
    print(f"{len(runtime_modules()) - len(failures)} modules importés, {len(failures)} échec(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
