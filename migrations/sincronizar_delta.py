#!/usr/bin/env python3
"""
sincronizar_delta.py — Trae al destino lo que entró en el origen después
de la copia inicial.

Uso:
    venv\\Scripts\\python migrations\\sincronizar_delta.py ORIGEN_DIRECT DESTINO_DIRECT

Por qué existe: la migración de base se hizo con el sistema en marcha.
Entre la copia y el cambio de DATABASE_URL en Vercel, el gateway siguió
subiendo telemetría y eventos al origen, y como los marca como
sincronizados en su SQLite, no los reenvía. Este script copia ese hueco.

Es idempotente: se apoya en las claves únicas de la ingesta
(uq_telemetria_sensor_trx, uq_evento) y en las primarias de las demás
tablas, con ON CONFLICT DO NOTHING. Se puede correr las veces que haga
falta.
"""
import io
import sys

import psycopg2

TABLAS = ["telemetria_indoor", "node_eventos", "comandos", "auth_codes", "users", "gateways", "edge_nodes"]

# Tablas cuyo `id` es un serial sin significado y que tienen clave natural
# (uq_telemetria_sensor_trx, uq_evento). Se copian SIN el id: las dos
# bases siguieron numerando por separado desde el corte, y una fila
# nueva del origen puede llevar el mismo id que otra distinta del
# destino. Con el id, el ON CONFLICT la descartaba por la primaria y se
# perdía en silencio.
SIN_ID = {"telemetria_indoor", "node_eventos"}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = psycopg2.connect(sys.argv[1]), psycopg2.connect(sys.argv[2])
    cs, cd = src.cursor(), dst.cursor()

    for t in TABLAS:
        cs.execute("""select column_name from information_schema.columns
                      where table_schema='public' and table_name=%s order by ordinal_position""", (t,))
        cols = [r[0] for r in cs.fetchall()]
        if t in SIN_ID:
            cols = [c for c in cols if c != "id"]
        lista = ",".join(f'"{c}"' for c in cols)

        # Se trae la tabla entera y el ON CONFLICT descarta lo ya copiado:
        # son decenas de miles de filas, no millones, y así no depende de
        # ninguna marca de tiempo que el reloj del gateway pueda mover.
        buf = io.StringIO()
        cs.copy_expert(f'copy (select {lista} from public."{t}") to stdout with (format csv)', buf)
        buf.seek(0)

        # Tabla temporal + INSERT ... ON CONFLICT DO NOTHING: es la forma de
        # hacer un COPY idempotente. El PK y las claves únicas deciden.
        # La temporal se crea a partir de una consulta vacía con las
        # columnas elegidas: `LIKE tabla` arrastraría el NOT NULL del id.
        cd.execute(f'create temp table _delta on commit drop as select {lista} from public."{t}" where false')
        cd.copy_expert(f'copy _delta ({lista}) from stdin with (format csv)', buf)
        cd.execute(f'insert into public."{t}" ({lista}) select {lista} from _delta on conflict do nothing')
        nuevas = cd.rowcount
        dst.commit()
        cs.execute(f'select count(*) from public."{t}"'); a = cs.fetchone()[0]
        cd.execute(f'select count(*) from public."{t}"'); b = cd.fetchone()[0]
        print(f"  {t:<20} +{nuevas:<6} origen={a:<7} destino={b:<7} {'OK' if a == b else 'DIFIERE'}")

    # Secuencias al día
    cd.execute("""select table_name, column_name from information_schema.columns
                  where table_schema='public' and (is_identity='YES' or column_default like 'nextval%')""")
    for t, c in cd.fetchall():
        cd.execute("select pg_get_serial_sequence(%s,%s)", (f"public.{t}", c)); seq = cd.fetchone()[0]
        if seq:
            cd.execute(f'select coalesce(max("{c}"),0) from public."{t}"'); m = cd.fetchone()[0]
            cd.execute("select setval(%s,%s)", (seq, max(m, 1)))
    dst.commit()
    print("delta aplicado")


if __name__ == "__main__":
    main()
