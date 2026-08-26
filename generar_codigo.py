"""
generar_codigo.py — Emite un OTP de acceso sin pasar por el correo.

    python generar_codigo.py                       # correo por defecto
    python generar_codigo.py otro@correo.com
    python generar_codigo.py otro@correo.com 999888 120

Para qué: el login del dashboard es passwordless por OTP enviado con
SMTP. Durante el desarrollo eso obliga a abrir el buzón en cada sesión,
y si el correo tarda o el proveedor lo marca como spam, el trabajo se
detiene por algo que no es el trabajo.

Esto hace lo mismo que `POST /api/auth/request-code` —crea el usuario si
no existe e inserta el código en `auth_codes`— pero se salta el envío.
El código sigue siendo un OTP normal: expira, se marca como usado al
canjearlo y no salta ninguna validación del servidor.

⚠️ Es una herramienta de desarrollo. No debe existir en el despliegue.
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

CORREO_DEF = "jhonattan.gonzalez.38@gmail.com"
MINUTOS_DEF = 60


def cargar_env() -> None:
    """Lee el .env del proyecto sin depender de python-dotenv."""
    ruta = Path(__file__).parent / ".env"
    if not ruta.exists():
        sys.exit("No encuentro .env junto a este script")
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


def main() -> None:
    cargar_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL no está definida en .env")

    correo = (sys.argv[1] if len(sys.argv) > 1 else CORREO_DEF).lower()
    codigo = sys.argv[2] if len(sys.argv) > 2 else f"{random.randint(100000, 999999)}"
    minutos = int(sys.argv[3]) if len(sys.argv) > 3 else MINUTOS_DEF
    expira = datetime.now(timezone.utc) + timedelta(minutes=minutos)

    con = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = con.cursor()

    cur.execute("SELECT id FROM public.users WHERE email = %s", (correo,))
    fila = cur.fetchone()
    if fila:
        user_id = fila["id"]
        nuevo = False
    else:
        cur.execute(
            "INSERT INTO public.users (email) VALUES (%s) RETURNING id", (correo,)
        )
        user_id = cur.fetchone()["id"]
        nuevo = True

    cur.execute(
        "INSERT INTO public.auth_codes (user_id, otp_code, expires_at) "
        "VALUES (%s, %s, %s)",
        (user_id, codigo, expira),
    )
    con.commit()
    cur.close()
    con.close()

    # ASCII a proposito: la consola de Windows usa cp1252 por defecto y
    # los caracteres de caja hacen reventar el print con UnicodeEncodeError
    # justo despues de haber escrito el codigo en la base.
    print()
    print("  +---------------------------------------------+")
    print(f"  |  correo : {correo:<33} |")
    print(f"  |  codigo : {codigo:<33} |")
    print("  +---------------------------------------------+")
    print(f"     usuario {'creado' if nuevo else 'existente'} · id {user_id}")
    print(f"     valido {minutos} min, hasta las "
          f"{expira.astimezone():%H:%M:%S}")
    print(f"     un solo uso: al canjearlo queda marcado como usado")
    print()


if __name__ == "__main__":
    main()
