"""
cargar_historico.py — Sube a Neon el histórico que la Raspberry
acumuló mientras la nube estuvo apagada.

    python cargar_historico.py /tmp/buffer_pi.db
    python cargar_historico.py /tmp/buffer_pi.db --dry-run

Por qué existe: `cloud.enabled` llevaba desde el 8 de agosto en false,
así que 31.776 tramas y sus eventos se quedaron en el SQLite del
gateway. Reenviarlas una a una por `POST /api/telemetria` serían 31.776
peticiones HTTP contra un pooler serverless; esto las inserta por lotes
en una sola conexión.

Lo cargado se marca con `origen='backfill'`: el dato es válido, pero su
`created_at` es el de hoy y no sirve para medir latencia de subida.

Es idempotente por (sensor_id, t_rx): re-ejecutarlo no duplica.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

LOTE = 1000


def cargar_env() -> None:
    ruta = Path(__file__).parent / ".env"
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def ts(epoch) -> datetime | None:
    """Epoch de la Pi -> datetime con zona. La Pi sella en UTC real."""
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


# Rangos del esquema (chk_* en 001_init.sql). Una lectura fuera de
# rango no es un dato: es el sensor diciendo que fallo. El HDC1080
# devuelve 125 C cuando no puede leer, y ese valor llego a la Pi como
# si fuera temperatura. Se guarda NULL y se cuenta aparte, porque el
# numero de lecturas invalidas es en si mismo una metrica de calidad.
RANGOS = {
    "temp":   (-40.0, 100.0),
    "hum":    (0.0, 100.0),
    "hsuelo": (0.0, 100.0),
    "ph":     (0.0, 14.0),
}

descartadas: dict[str, int] = {}


def valido(campo: str, v):
    if v is None:
        return None
    lo, hi = RANGOS[campo]
    try:
        f = float(v)
    except (TypeError, ValueError):
        descartadas[campo] = descartadas.get(campo, 0) + 1
        return None
    if lo <= f <= hi:
        return f
    descartadas[campo] = descartadas.get(campo, 0) + 1
    return None


def leer_telemetria(sq: sqlite3.Connection) -> list[tuple]:
    filas = []
    for r in sq.execute("SELECT payload, created_at FROM telemetry_buffer"):
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue
        if p.get("kind") != "telemetria":
            continue

        s = p.get("sensores") or {}
        t_rx = ts(p.get("t_rx") or r["created_at"])
        if not t_rx:
            continue

        filas.append((
            t_rx,                                  # created_at = cuando se midio
            p.get("gateway_id") or "FOG_RPI_HIERBABUENA_01",   # node_id  = gateway
            p.get("node_id") or "IoT-node-26.001",             # sensor_id = ESP32
            valido("temp", s.get("temp")), valido("hum", s.get("hum")),
            valido("hsuelo", s.get("hsuelo")), valido("ph", s.get("ph")),
            None,                                  # estado_actuadores
            p.get("rssi"), s.get("ec"), s.get("tds"),
            None,                                  # nivel_raw: no va en telemetria
            s.get("agua"),
            p.get("fw"), p.get("uptime_ms"), p.get("periodo_ms"),
            t_rx,                                  # t_rx
            "backfill",
        ))
    return filas


def leer_eventos(sq: sqlite3.Connection) -> list[tuple]:
    try:
        cur = sq.execute(
            "SELECT node_id, evento, detalle, created_at FROM node_events")
    except sqlite3.OperationalError:
        return []                                  # gateway sin la tabla aun

    filas = []
    for r in cur:
        t = ts(r["created_at"])
        if not t:
            continue
        try:
            det = json.loads(r["detalle"] or "{}")
        except Exception:
            det = {"crudo": r["detalle"]}
        filas.append((
            t, "FOG_RPI_HIERBABUENA_01", r["node_id"], r["evento"],
            json.dumps(det),
        ))
    return filas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite", help="copia del buffer.db de la Raspberry")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cargar_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL no definida")

    sq = sqlite3.connect(args.sqlite)
    sq.row_factory = sqlite3.Row

    tele = leer_telemetria(sq)
    even = leer_eventos(sq)
    sq.close()

    print(f"  telemetria a cargar : {len(tele)}")
    if descartadas:
        print("  lecturas fuera de rango, guardadas como NULL:")
        for campo, n in sorted(descartadas.items()):
            lo, hi = RANGOS[campo]
            print(f"      {campo:8s} {n:5d}  (rango valido {lo} a {hi})")
    print(f"  eventos a cargar    : {len(even)}")
    if tele:
        print(f"  ventana             : {min(t[0] for t in tele):%Y-%m-%d %H:%M}"
              f"  ->  {max(t[0] for t in tele):%Y-%m-%d %H:%M}")
    if args.dry_run:
        print("\n  (dry-run: no se escribio nada)")
        return

    con = psycopg2.connect(url)
    cur = con.cursor()

    # Indice unico para que el ON CONFLICT tenga a que agarrarse. Se crea
    # aqui y no en la migracion porque solo el backfill lo necesita: en
    # ingesta normal dos tramas del mismo instante no ocurren.
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_telemetria_sensor_trx
        ON public.telemetria_indoor (sensor_id, t_rx)
        WHERE t_rx IS NOT NULL
    """)
    con.commit()

    print("\n  insertando telemetria...")
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO public.telemetria_indoor
            (created_at, node_id, sensor_id, temperatura, humedad_ambiente,
             humedad_suelo, ph, estado_actuadores, rssi, ec, tds, nivel_raw,
             agua, fw, uptime_ms, periodo_ms, t_rx, origen)
        VALUES %s
        ON CONFLICT (sensor_id, t_rx) WHERE t_rx IS NOT NULL DO NOTHING
        """,
        tele, page_size=LOTE,
    )
    insertadas = cur.rowcount
    con.commit()

    if even:
        print("  insertando eventos...")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO public.node_eventos
                (ts, gateway_id, sensor_id, evento, detalle)
            VALUES %s
            ON CONFLICT (sensor_id, ts, evento) DO NOTHING
            """,
            even, page_size=LOTE,
        )
        con.commit()

    cur.execute("SELECT COUNT(*) FROM public.telemetria_indoor")
    total_t = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM public.node_eventos")
    total_e = cur.fetchone()[0]
    cur.close()
    con.close()

    print(f"\n  insertadas ahora    : {insertadas}")
    print(f"  total en Neon       : {total_t} telemetria, {total_e} eventos")


if __name__ == "__main__":
    main()
