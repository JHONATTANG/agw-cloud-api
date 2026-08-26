#!/usr/bin/env python3
"""
migrate.py — Runner de migraciones para Neon PostgreSQL
=======================================================
Ejecuta en orden los archivos .sql de migrations/neon/ y lleva registro
en la tabla `schema_migrations` para no reaplicar lo ya aplicado.

Uso:
    python migrate.py            # aplica las migraciones pendientes
    python migrate.py --status   # solo muestra el estado, no escribe nada
    python migrate.py --dry-run  # muestra qué se aplicaría

Notas de diseño:
  · Usa psycopg2 (síncrono), no asyncpg. asyncpg emplea prepared
    statements, incompatibles con PgBouncer en modo transacción.
  · Prefiere DATABASE_URL_DIRECT (endpoint sin "-pooler") porque el DDL
    y los bloques DO $$ conviene ejecutarlos fuera del pooler.
  · Cada migración corre en su propia transacción: si falla, revierte
    entera y no se marca como aplicada.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "neon"


def load_env() -> None:
    """Carga .env sin depender de python-dotenv."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_dsn() -> str:
    dsn = os.getenv("DATABASE_URL_DIRECT") or os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("ERROR: define DATABASE_URL_DIRECT (o DATABASE_URL) en .env")
    if "-pooler" in dsn:
        print("AVISO: usando el endpoint pooled. Para DDL se recomienda "
              "DATABASE_URL_DIRECT (host sin '-pooler').")
    return dsn


def ensure_tracking_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                filename    TEXT PRIMARY KEY,
                checksum    TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
    conn.commit()


def applied_migrations(conn) -> dict[str, str]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT filename, checksum FROM public.schema_migrations")
        return {r["filename"]: r["checksum"] for r in cur.fetchall()}


def main() -> None:
    load_env()
    status_only = "--status" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not MIGRATIONS_DIR.exists():
        sys.exit(f"ERROR: no existe {MIGRATIONS_DIR}")

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        sys.exit(f"ERROR: no hay archivos .sql en {MIGRATIONS_DIR}")

    conn = psycopg2.connect(get_dsn(), connect_timeout=20)
    conn.autocommit = False
    print(f"Conectado a Neon.\n")

    ensure_tracking_table(conn)
    done = applied_migrations(conn)

    pending = []
    for f in files:
        sql = f.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]
        if f.name in done:
            mark = "OK " if done[f.name] == checksum else "MOD"
            print(f"  [{mark}] {f.name}")
            if mark == "MOD":
                print(f"        ADVERTENCIA: el archivo cambió desde que se "
                      f"aplicó. Crea una migración nueva en vez de editarlo.")
        else:
            print(f"  [   ] {f.name}  <- pendiente")
            pending.append((f, sql, checksum))

    if status_only:
        conn.close()
        return

    if not pending:
        print("\nNada que aplicar. La base está al día.")
        conn.close()
        return

    if dry_run:
        print(f"\n[dry-run] Se aplicarían {len(pending)} migración(es).")
        conn.close()
        return

    print(f"\nAplicando {len(pending)} migración(es)...\n")
    for f, sql, checksum in pending:
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO public.schema_migrations (filename, checksum) "
                    "VALUES (%s, %s)",
                    (f.name, checksum),
                )
            conn.commit()
            print(f"  OK  {f.name}")
        except Exception as exc:
            conn.rollback()
            conn.close()
            sys.exit(f"  FALLO en {f.name}: {exc}\n\nSe revirtió. Nada más se aplicó.")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            ORDER BY 1
        """)
        tables = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"\nListo. Tablas en public: {', '.join(tables)}")


if __name__ == "__main__":
    main()
