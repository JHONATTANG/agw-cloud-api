"""
api/_env.py — Carga de variables de entorno desde .env
======================================================
Importar ESTE módulo antes que cualquier otro que lea os.environ.

Por qué existe:
  En un despliegue serverless el proveedor inyecta las variables de
  entorno automáticamente. Corriendo en local (uvicorn) no las inyecta
  nadie, así que sin esto la aplicación revienta con KeyError al
  importar api/security.py.

Comportamiento:
  · Solo define variables que NO estén ya en el entorno. Es decir, el
    entorno real siempre gana sobre el archivo .env. Así el mismo
    código sirve en local y en cualquier plataforma de despliegue.
  · Si no existe .env, no hace nada y no falla.
  · Sin dependencias externas: no requiere python-dotenv.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = _ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Quitar comillas envolventes si las hay
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        # El entorno real tiene prioridad sobre el archivo
        os.environ.setdefault(key, value)


load_env()
