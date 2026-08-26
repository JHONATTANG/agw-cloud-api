"""
Métricas de telecomunicaciones — MCD §9.

Este router es el que sostiene el eje evaluativo del proyecto. Todo lo
demás del backend sirve datos agronómicos; esto sirve el desempeño de
la cadena de comunicación, que es lo que el trabajo de grado mide.

DECISIÓN DE DISEÑO: las agregaciones viven en SQL, no en el frontend.
La definición de "pérdida de mensajes" es una sola y está aquí. Si
viviera en TypeScript, el día que cambie habría dos definiciones
distintas en el sistema y ninguna sería la buena.

CÓMO SE DERIVAN LAS MÉTRICAS SIN INSTRUMENTACIÓN EXTRA

El nodo no sella sus tramas con la hora de publicación —eso exigiría
reflashear— pero cada trama trae `uptime_ms` y `periodo_ms`, y la Pi
estampa `t_rx` al recibirla. Con esos tres campos salen tres de las
métricas del §9:

  · Pérdida:   entre dos tramas consecutivas, el salto de uptime
               dividido por el periodo vigente dice cuántas DEBIÓ
               emitir el nodo. Lo que falte, se perdió.
  · Jitter:    desviación del intervalo real de llegada frente al
               periodo programado.
  · Reinicios: un uptime que retrocede es un arranque nuevo. De ahí
               salen disponibilidad y MTTR del nodo.

Lo que NO se puede derivar así queda declarado como tal en /resumen,
en vez de devolver un cero que parezca una medición.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.security import get_current_user, get_db_connection

logger = logging.getLogger("agw-cloud-api.metricas")

metricas_router = APIRouter(prefix="/api/metricas", tags=["Telecomunicaciones"])

# Frontera entre la trama que sube en caliente y la que se recupera del
# buffer tras un corte. Ver la nota en `resumen()`.
_UMBRAL_EN_VIVO_MS = 60_000

# Ventana por defecto de casi todas las consultas. 7 días entra holgado
# en memoria del navegador y cubre el ciclo semanal del cultivo.
DIAS_DEF = 7


def _filas(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("Fallo la consulta de métricas: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error consultando métricas",
        )
    finally:
        cur.close()
        conn.close()


def _una(sql: str, params: tuple = ()) -> dict:
    f = _filas(sql, params)
    return f[0] if f else {}


# ═══════════════════════════════════════════════════════════════
#  Resumen — las tarjetas de cabecera del panel
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/resumen",
    summary="KPIs de la cadena de telecomunicaciones (MCD §9)",
)
async def resumen(
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    sensor_id: Optional[str] = None,
    _user: dict = Depends(get_current_user),
):
    filtro = "AND sensor_id = %s" if sensor_id else ""
    p = (dias, sensor_id) if sensor_id else (dias,)

    cobertura = _una(f"""
        SELECT COUNT(*)                              AS tramas,
               MIN(t_rx)                             AS desde,
               MAX(t_rx)                             AS hasta,
               COUNT(DISTINCT sensor_id)             AS nodos,
               COUNT(DISTINCT fw)                    AS versiones_fw
        FROM telemetria_indoor
        WHERE t_rx > now() - (%s || ' days')::interval {filtro}
    """, p)

    rssi = _una(f"""
        SELECT ROUND(AVG(rssi)::numeric, 1)          AS media,
               MIN(rssi)                             AS minimo,
               MAX(rssi)                             AS maximo,
               ROUND(STDDEV(rssi)::numeric, 1)       AS sigma,
               PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY rssi) AS p05,
               PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY rssi) AS p50,
               PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY rssi) AS p95,
               ROUND(100.0 * SUM(CASE WHEN rssi < -70 THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 1)       AS pct_bajo_umbral
        FROM telemetria_indoor
        WHERE rssi IS NOT NULL
          AND t_rx > now() - (%s || ' days')::interval {filtro}
    """, p)

    # Pérdida: el salto de uptime frente al periodo vigente. Se descartan
    # los saltos negativos, que son reinicios y no huecos.
    perdida = _una(f"""
        WITH s AS (
            SELECT sensor_id, t_rx, uptime_ms, periodo_ms,
                   uptime_ms - LAG(uptime_ms) OVER w AS d_up
            FROM telemetria_indoor
            WHERE uptime_ms IS NOT NULL AND periodo_ms > 0
              AND t_rx > now() - (%s || ' days')::interval {filtro}
            WINDOW w AS (PARTITION BY sensor_id ORDER BY t_rx)
        ), e AS (
            SELECT GREATEST(ROUND(d_up::numeric / periodo_ms), 1) AS esperadas
            FROM s WHERE d_up > 0
        )
        SELECT COALESCE(SUM(esperadas), 0)                       AS esperadas,
               COUNT(*)                                          AS recibidas,
               COALESCE(SUM(esperadas), 0) - COUNT(*)            AS perdidas,
               ROUND(100.0 * (COALESCE(SUM(esperadas), 0) - COUNT(*))
                     / NULLIF(SUM(esperadas), 0), 3)             AS pct
        FROM e
    """, p)

    jitter = _filas(f"""
        SELECT periodo_ms / 1000                     AS cadencia_s,
               COUNT(*)                              AS n,
               ROUND(AVG(intervalo_s)::numeric, 2)   AS media_s,
               ROUND(STDDEV(intervalo_s)::numeric, 3) AS sigma_s,
               ROUND(MIN(intervalo_s)::numeric, 2)   AS min_s,
               ROUND(MAX(intervalo_s)::numeric, 2)   AS max_s
        FROM v_intervalos
        WHERE intervalo_s IS NOT NULL AND periodo_ms > 0
          AND intervalo_s < periodo_ms / 1000.0 * 1.5
          AND t_rx > now() - (%s || ' days')::interval {filtro}
        GROUP BY 1 ORDER BY 1
    """, p)

    # Un uptime que retrocede = el nodo arrancó de nuevo.
    reinicios = _una(f"""
        WITH s AS (
            SELECT t_rx, uptime_ms,
                   LAG(uptime_ms) OVER (PARTITION BY sensor_id ORDER BY t_rx) AS prev
            FROM telemetria_indoor
            WHERE uptime_ms IS NOT NULL
              AND t_rx > now() - (%s || ' days')::interval {filtro}
        )
        SELECT COUNT(*) AS n, MAX(t_rx) AS ultimo
        FROM s WHERE prev IS NOT NULL AND uptime_ms < prev
    """, p)

    # La vista mezcla dos poblaciones que no se pueden promediar juntas:
    # la trama que sube en caliente y la que estuvo días en el buffer
    # SQLite esperando que volviera la red. Promediarlas daba una
    # "latencia de subida" de 4,5 horas, que no describe nada: ni el
    # camino en vivo, que tarda 200 ms, ni la recuperación, que tarda lo
    # que durase el corte.
    #
    # No hay una columna que las distinga, pero el umbral las separa sin
    # ambigüedad: el remitente en vivo publica en cuanto recibe del
    # broker, así que nada del camino caliente puede tardar un minuto.
    subida = _una(f"""
        SELECT COUNT(*)                            AS n,
               ROUND(AVG(latencia_ms)::numeric, 1) AS media_ms,
               ROUND(MIN(latencia_ms)::numeric, 1) AS minimo_ms,
               PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latencia_ms) AS p50_ms,
               PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latencia_ms) AS p95_ms
        FROM v_latencia_subida WHERE latencia_ms < {_UMBRAL_EN_VIVO_MS}
    """)

    recuperadas = _una(f"""
        SELECT COUNT(*)                                  AS n,
               ROUND(MAX(latencia_ms)::numeric / 3600000, 1) AS peor_horas
        FROM v_latencia_subida WHERE latencia_ms >= {_UMBRAL_EN_VIVO_MS}
    """)

    return {
        "ventana_dias": dias,
        "cobertura": cobertura,
        "rssi": {**rssi, "objetivo_dbm": -70},
        "perdida": {**perdida, "objetivo_pct": 1.0},
        "jitter_por_cadencia": jitter,
        "reinicios_nodo": reinicios,
        "latencia_subida": {
            **subida,
            "objetivo_ms": 1500,
            "umbral_en_vivo_ms": _UMBRAL_EN_VIVO_MS,
            # Sin ingesta en vivo no hay ningún registro 'directo', y la
            # vista devuelve vacío. Decirlo es más útil que un cero.
            "estado": "medible" if (subida.get("n") or 0) > 0
                      else "sin ingesta en vivo todavia",
        },
        # No es ruido que haya que esconder: es la prueba de que el buffer
        # del borde cumplió su trabajo y de cuánto llegó a acumular.
        "recuperacion_de_buffer": recuperadas,
        "no_instrumentado": {
            "latencia_extremo_a_extremo":
                "requiere que el ESP32 selle t_pub en cada trama",
            "rtt_icmp_mqtt_http":
                "sondas activas del gateway, aun no persistidas en net_muestras",
            "impacto_qos":
                "PubSubClient solo publica QoS 0 (deuda 7.22)",
        },
    }


# ═══════════════════════════════════════════════════════════════
#  Mapa de calor
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/heatmap",
    summary="Matriz hora x dia de una metrica, para mapa de calor",
)
async def heatmap(
    metrica: str = Query("rssi", pattern="^(rssi|temperatura|humedad_ambiente|ec|tramas)$"),
    dias: int = Query(14, ge=1, le=90),
    sensor_id: Optional[str] = None,
    _user: dict = Depends(get_current_user),
):
    """
    Una fila por celda (día, hora). El frontend solo pinta.

    Se agrega aquí y no en el navegador porque son 31.000 filas: mandar
    la serie cruda para que el cliente la agrupe es tirar ancho de banda
    y batería del que mira.
    """
    agregado = "COUNT(*)" if metrica == "tramas" else f"ROUND(AVG({metrica})::numeric, 2)"
    cond = "" if metrica == "tramas" else f"AND {metrica} IS NOT NULL"
    filtro = "AND sensor_id = %s" if sensor_id else ""
    p = (dias, sensor_id) if sensor_id else (dias,)

    filas = _filas(f"""
        SELECT date_trunc('day', t_rx)::date  AS dia,
               EXTRACT(hour FROM t_rx)::int   AS hora,
               {agregado}                     AS valor,
               COUNT(*)                       AS muestras
        FROM telemetria_indoor
        WHERE t_rx > now() - (%s || ' days')::interval {cond} {filtro}
        GROUP BY 1, 2 ORDER BY 1, 2
    """, p)

    valores = [f["valor"] for f in filas if f["valor"] is not None]
    return {
        "metrica": metrica,
        "celdas": filas,
        "min": min(valores) if valores else None,
        "max": max(valores) if valores else None,
    }


# ═══════════════════════════════════════════════════════════════
#  Series y distribuciones
# ═══════════════════════════════════════════════════════════════

@metricas_router.get("/series", summary="Serie temporal agregada por bucket")
async def series(
    metrica: str = Query("rssi", pattern="^(rssi|temperatura|humedad_ambiente|humedad_suelo|ec|tds)$"),
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    bucket_min: int = Query(30, ge=1, le=1440),
    sensor_id: Optional[str] = None,
    _user: dict = Depends(get_current_user),
):
    filtro = "AND sensor_id = %s" if sensor_id else ""
    p = (bucket_min, dias, sensor_id) if sensor_id else (bucket_min, dias)

    return {
        "metrica": metrica,
        "bucket_min": bucket_min,
        "puntos": _filas(f"""
            SELECT to_timestamp(FLOOR(EXTRACT(epoch FROM t_rx) / (%s * 60)) * (%s * 60)) AS t,
                   ROUND(AVG({metrica})::numeric, 2)  AS media,
                   MIN({metrica})                     AS minimo,
                   MAX({metrica})                     AS maximo,
                   COUNT(*)                           AS n
            FROM telemetria_indoor
            WHERE {metrica} IS NOT NULL
              AND t_rx > now() - (%s || ' days')::interval {filtro}
            GROUP BY 1 ORDER BY 1
        """, (bucket_min, bucket_min) + p[1:]),
    }


@metricas_router.get("/distribucion", summary="Histograma y CDF de una metrica")
async def distribucion(
    metrica: str = Query("rssi", pattern="^(rssi|temperatura|humedad_ambiente|ec)$"),
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    bins: int = Query(24, ge=4, le=80),
    _user: dict = Depends(get_current_user),
):
    """
    Histograma con anchura de bin calculada sobre el rango real, más la
    acumulada. La CDF es lo que responde "¿qué porcentaje del tiempo
    estuve por debajo del umbral?", que es la pregunta del §9.
    """
    rango = _una(f"""
        SELECT MIN({metrica}) AS lo, MAX({metrica}) AS hi, COUNT(*) AS n
        FROM telemetria_indoor
        WHERE {metrica} IS NOT NULL AND t_rx > now() - (%s || ' days')::interval
    """, (dias,))

    if not rango.get("n"):
        return {"metrica": metrica, "bins": [], "n": 0}

    lo, hi = float(rango["lo"]), float(rango["hi"])
    if hi == lo:
        hi = lo + 1
    ancho = (hi - lo) / bins

    filas = _filas(f"""
        WITH d AS (
            SELECT LEAST(FLOOR(({metrica} - %s) / %s), %s - 1) AS bin
            FROM telemetria_indoor
            WHERE {metrica} IS NOT NULL AND t_rx > now() - (%s || ' days')::interval
        )
        SELECT bin::int AS bin, COUNT(*) AS n
        FROM d GROUP BY 1 ORDER BY 1
    """, (lo, ancho, bins, dias))

    total = sum(f["n"] for f in filas)
    acum = 0
    salida = []
    for f in filas:
        acum += f["n"]
        salida.append({
            "desde": round(lo + f["bin"] * ancho, 2),
            "hasta": round(lo + (f["bin"] + 1) * ancho, 2),
            "n": f["n"],
            "pct": round(100.0 * f["n"] / total, 2),
            "cdf": round(100.0 * acum / total, 2),
        })

    return {"metrica": metrica, "n": total, "min": lo, "max": hi, "bins": salida}


# ═══════════════════════════════════════════════════════════════
#  Eventos y disponibilidad
# ═══════════════════════════════════════════════════════════════

@metricas_router.get("/eventos", summary="Eventos del nodo registrados por el gateway")
async def eventos(
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    tipo: Optional[str] = None,
    limite: int = Query(200, ge=1, le=2000),
    _user: dict = Depends(get_current_user),
):
    filtro = "AND evento = %s" if tipo else ""
    p = (dias, tipo, limite) if tipo else (dias, limite)

    return {
        "resumen": _filas("""
            SELECT evento, COUNT(*) AS n, MAX(ts) AS ultimo
            FROM node_eventos
            WHERE ts > now() - (%s || ' days')::interval
            GROUP BY 1 ORDER BY n DESC
        """, (dias,)),
        "eventos": _filas(f"""
            SELECT ts, sensor_id, evento, detalle
            FROM node_eventos
            WHERE ts > now() - (%s || ' days')::interval {filtro}
            ORDER BY ts DESC LIMIT %s
        """, p),
    }


@metricas_router.get("/riego", summary="Ciclos de riego contados, no estimados")
async def riego(
    dias: int = Query(14, ge=1, le=90),
    _user: dict = Depends(get_current_user),
):
    """
    Del evento de fin, que trae la duración real medida por el nodo.
    No se puede sacar del muestreo de telemetría: un ciclo de 3 minutos
    cabe entre dos tramas de 5 y desaparecería del recuento.
    """
    return {
        "por_dia": _filas("""
            SELECT ts::date                                     AS dia,
                   COUNT(*)                                     AS ciclos,
                   ROUND(SUM((detalle->>'segundos')::numeric) / 60.0, 1) AS min_bomba,
                   MIN((detalle->>'segundos')::int)             AS s_min,
                   MAX((detalle->>'segundos')::int)             AS s_max
            FROM node_eventos
            WHERE evento = 'riego_hidroponia_fin'
              AND ts > now() - (%s || ' days')::interval
              AND detalle ? 'segundos'
            GROUP BY 1 ORDER BY 1
        """, (dias,)),
    }


@metricas_router.get("/gateway", summary="Estado del gateway visto desde la nube")
async def gateway(
    _user: dict = Depends(get_current_user),
):
    """
    La nube no puede preguntarle a la Raspberry: está detrás de NAT y no
    expone nada hacia fuera. Lo que sí puede es inferir su salud del
    flujo de datos que produce — que es, de hecho, la única señal que un
    operador remoto tendría.
    """
    ultimo = _una("""
        SELECT MAX(t_rx) AS ultima_trama,
               EXTRACT(EPOCH FROM (now() - MAX(t_rx))) AS hace_s
        FROM telemetria_indoor
    """)

    hace = ultimo.get("hace_s") or 0
    return {
        "ultima_trama": ultimo.get("ultima_trama"),
        "silencio_s": round(hace),
        # El umbral no es arbitrario: con la cadencia actual de 300 s,
        # tres periodos sin noticias ya no es jitter, es un problema.
        "estado": "en linea" if hace < 900 else "sin noticias",
        "ingesta_en_vivo": _una("""
            SELECT COUNT(*) AS n FROM telemetria_indoor WHERE origen = 'directo'
        """).get("n", 0),
        "por_origen": _filas("""
            SELECT origen, COUNT(*) AS n, MIN(t_rx) AS desde, MAX(t_rx) AS hasta
            FROM telemetria_indoor GROUP BY 1
        """),
        "eventos_recientes": _filas("""
            SELECT ts, evento, sensor_id FROM node_eventos
            ORDER BY ts DESC LIMIT 10
        """),
    }


# ═══════════════════════════════════════════════════════════════
#  Fog computing — la autonomía, medida
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/fog",
    summary="Evidencia de que el borde decide sin la nube",
)
async def fog(
    dias: int = Query(30, ge=1, le=365),
    _user: dict = Depends(get_current_user),
):
    """
    La resiliencia de borde es el aporte que el proyecto declara como
    innovación, y hasta ahora se sostenía con un diagrama. Esto la
    sostiene con cuentas.

    El argumento tiene una forma concreta y verificable: durante toda la
    ventana de datos la nube estuvo apagada, y aun así el cultivo se
    regó, se iluminó y se corrigió solo. Cada una de esas decisiones
    dejó un evento, y aquí se cuentan.
    """
    # Cuánto tiempo lleva el sistema produciendo datos sin nube. Todo el
    # historico es 'backfill', o sea: nada de esto se subio en su
    # momento, y el cultivo funciono igual.
    ventana = _una("""
        SELECT MIN(t_rx) AS desde, MAX(t_rx) AS hasta,
               EXTRACT(EPOCH FROM (MAX(t_rx) - MIN(t_rx))) / 86400.0 AS dias,
               COUNT(*) FILTER (WHERE origen = 'backfill') AS sin_nube,
               COUNT(*) FILTER (WHERE origen = 'directo')  AS con_nube
        FROM telemetria_indoor
    """)

    # Decisiones que tomó el borde por su cuenta, por tipo.
    decisiones = _filas("""
        SELECT evento,
               COUNT(*) AS n,
               MIN(ts)  AS primero,
               MAX(ts)  AS ultimo
        FROM node_eventos
        WHERE ts > now() - (%s || ' days')::interval
        GROUP BY 1 ORDER BY n DESC
    """, (dias,))

    # Riego ejecutado sin que la nube supiera nada. Es el argumento
    # central: el cultivo no dependio de la conectividad.
    riego = _una("""
        SELECT COUNT(*) AS ciclos,
               ROUND(SUM((detalle->>'segundos')::numeric) / 60.0, 1) AS minutos_bomba,
               COUNT(DISTINCT ts::date) AS dias_con_riego
        FROM node_eventos
        WHERE evento = 'riego_hidroponia_fin'
          AND ts > now() - (%s || ' days')::interval
          AND detalle ? 'segundos'
    """, (dias,))

    # Caídas del nodo y cuánto tardó el gateway en recuperarlo. Es el
    # MTTR real: de 'desconectado' al siguiente 'conectado'.
    recuperacion = _filas("""
        WITH e AS (
            SELECT ts, evento,
                   LEAD(ts)     OVER (ORDER BY ts) AS ts_sig,
                   LEAD(evento) OVER (ORDER BY ts) AS ev_sig
            FROM node_eventos
            WHERE evento IN ('desconectado', 'conectado')
              AND ts > now() - (%s || ' days')::interval
        )
        SELECT ts AS caida, ts_sig AS vuelta,
               ROUND(EXTRACT(EPOCH FROM (ts_sig - ts))) AS segundos
        FROM e
        WHERE evento = 'desconectado' AND ev_sig = 'conectado'
        ORDER BY ts DESC
    """, (dias,))

    tiempos = [r["segundos"] for r in recuperacion if r.get("segundos") is not None]

    # Huecos en la serie: periodos sin una sola trama. Un hueco largo
    # con riego ocurriendo dentro demuestra que el nodo no necesitaba
    # al gateway para seguir.
    huecos = _filas("""
        WITH s AS (
            SELECT t_rx,
                   LAG(t_rx) OVER (ORDER BY t_rx) AS prev,
                   periodo_ms
            FROM telemetria_indoor
            WHERE t_rx > now() - (%s || ' days')::interval
        )
        SELECT prev AS desde, t_rx AS hasta,
               ROUND(EXTRACT(EPOCH FROM (t_rx - prev))) AS segundos
        FROM s
        WHERE prev IS NOT NULL
          AND EXTRACT(EPOCH FROM (t_rx - prev)) > GREATEST(periodo_ms / 1000.0 * 3, 300)
        ORDER BY segundos DESC LIMIT 10
    """, (dias,))

    return {
        "ventana": ventana,
        "autonomia": {
            "dias_sin_nube": round(float(ventana.get("dias") or 0), 1),
            "tramas_generadas_sin_nube": ventana.get("sin_nube", 0),
            "pct_del_historico_sin_nube": (
                round(100.0 * (ventana.get("sin_nube") or 0)
                      / max((ventana.get("sin_nube") or 0) + (ventana.get("con_nube") or 0), 1), 1)
            ),
        },
        "decisiones_del_borde": decisiones,
        "riego_autonomo": riego,
        "recuperaciones": {
            "n": len(tiempos),
            "mttr_s": round(sum(tiempos) / len(tiempos)) if tiempos else None,
            "peor_s": max(tiempos) if tiempos else None,
            "mejor_s": min(tiempos) if tiempos else None,
            "objetivo_s": 90,
            "detalle": recuperacion[:10],
        },
        "huecos_de_datos": huecos,
    }


# ═══════════════════════════════════════════════════════════════
#  Series cruzadas
# ═══════════════════════════════════════════════════════════════
#
#  Los endpoints de arriba sirven una métrica cada uno. Para comparar
#  varias hay que pedirlas por separado y alinearlas en el navegador, y
#  eso sale mal: cada consulta agrupa por su cuenta y basta que a una
#  métrica le falte un bucket para que las series queden desplazadas
#  entre sí y el gráfico mienta.
#
#  Aquí se agrupan todas contra la MISMA rejilla de tiempo, generada con
#  generate_series, así que los huecos son huecos de verdad —null— y no
#  un corrimiento silencioso.

_METRICAS_SERIE = {
    "temperatura":      "temperatura",
    "humedad_ambiente": "humedad_ambiente",
    "humedad_suelo":    "humedad_suelo",
    "ec":               "ec",
    "tds":              "tds",
    "rssi":             "rssi",
    "nivel_raw":        "nivel_raw",
}


@metricas_router.get(
    "/multiserie",
    summary="Varias metricas sobre la misma rejilla temporal",
)
async def multiserie(
    metricas: str = Query("temperatura,humedad_ambiente,ec,rssi"),
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    bucket_min: int = Query(30, ge=1, le=1440),
    _user: dict = Depends(get_current_user),
):
    pedidas = [m.strip() for m in metricas.split(",") if m.strip()]
    malas = [m for m in pedidas if m not in _METRICAS_SERIE]
    if malas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metricas no reconocidas: {', '.join(malas)}",
        )
    if not pedidas:
        raise HTTPException(status_code=400, detail="Sin metricas que servir")

    # Los nombres salen del diccionario blanco de arriba, nunca del
    # parámetro: interpolar directo lo que llega por query sería una
    # inyección de SQL de manual.
    cols = ",\n               ".join(
        f"ROUND(AVG(t.{_METRICAS_SERIE[m]})::numeric, 2) AS {m}" for m in pedidas
    )

    puntos = _filas(f"""
        WITH rejilla AS (
            SELECT generate_series(
                date_trunc('hour', now() - (%s || ' days')::interval),
                date_trunc('hour', now()),
                (%s || ' minutes')::interval
            ) AS t0
        )
        SELECT r.t0 AS t,
               COUNT(t.id) AS n,
               {cols}
        FROM rejilla r
        LEFT JOIN telemetria_indoor t
               ON t.t_rx >= r.t0
              AND t.t_rx <  r.t0 + (%s || ' minutes')::interval
        GROUP BY r.t0 ORDER BY r.t0
    """, (dias, bucket_min, bucket_min))

    return {"metricas": pedidas, "bucket_min": bucket_min, "puntos": puntos}


# ═══════════════════════════════════════════════════════════════
#  Balance diario
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/diario",
    summary="Un dia por fila: cobertura, perdida, disponibilidad y riego",
)
async def diario(
    dias: int = Query(21, ge=1, le=90),
    _user: dict = Depends(get_current_user),
):
    """
    La fila que hace falta para las barras compuestas: cuántas tramas se
    esperaban, cuántas llegaron y qué se hizo ese día.

    "Esperadas" no es una constante: la cadencia cambió de 10 s a 60 s y
    luego a 300 s durante la vida del cultivo. Se calcula por día con el
    `periodo_ms` que el propio nodo reportó, que es el único que sabe a
    qué ritmo estaba publicando en ese momento.
    """
    return {
        "dias": _filas("""
            WITH t AS (
                SELECT date_trunc('day', t_rx) AS dia,
                       COUNT(*)                AS tramas,
                       ROUND(AVG(rssi)::numeric, 1)             AS rssi_medio,
                       MIN(rssi)                                AS rssi_min,
                       ROUND(AVG(temperatura)::numeric, 2)      AS temp_media,
                       ROUND(AVG(humedad_ambiente)::numeric, 2) AS hum_media,
                       ROUND(AVG(ec)::numeric, 1)               AS ec_media,
                       ROUND(AVG(periodo_ms)::numeric, 0)       AS periodo_ms,
                       COUNT(*) FILTER (WHERE rssi < -70)       AS tramas_rssi_bajo
                FROM telemetria_indoor
                WHERE t_rx > now() - (%s || ' days')::interval
                GROUP BY 1
            ),
            reinicios AS (
                SELECT date_trunc('day', t_rx) AS dia, COUNT(*) AS n
                FROM (
                    SELECT t_rx, uptime_ms,
                           LAG(uptime_ms) OVER (ORDER BY t_rx) AS prev
                    FROM telemetria_indoor
                    WHERE t_rx > now() - (%s || ' days')::interval
                      AND uptime_ms IS NOT NULL
                ) s
                WHERE prev IS NOT NULL AND uptime_ms < prev
                GROUP BY 1
            ),
            riego AS (
                SELECT date_trunc('day', ts) AS dia,
                       COUNT(*) AS ciclos,
                       ROUND(SUM((detalle->>'segundos')::numeric) / 60, 1) AS min_bomba
                FROM node_eventos
                WHERE evento LIKE 'riego_%%_fin'
                  AND ts > now() - (%s || ' days')::interval
                GROUP BY 1
            )
            SELECT t.dia,
                   t.tramas, t.rssi_medio, t.rssi_min, t.temp_media,
                   t.hum_media, t.ec_media, t.periodo_ms, t.tramas_rssi_bajo,
                   COALESCE(r.n, 0)          AS reinicios,
                   COALESCE(g.ciclos, 0)     AS ciclos_riego,
                   COALESCE(g.min_bomba, 0)  AS min_bomba,
                   -- Tramas que cabían en el día al ritmo que el nodo dijo
                   -- estar publicando. Se recorta al instante actual para
                   -- no pintar el día en curso como una caída enorme.
                   GREATEST(ROUND(
                       LEAST(86400, EXTRACT(EPOCH FROM (
                           LEAST(now(), t.dia + interval '1 day') - t.dia)))
                       / NULLIF(t.periodo_ms, 0) * 1000
                   ), 1) AS esperadas
            FROM t
            LEFT JOIN reinicios r ON r.dia = t.dia
            LEFT JOIN riego g     ON g.dia = t.dia
            ORDER BY t.dia
        """, (dias, dias, dias)),
    }


# ═══════════════════════════════════════════════════════════════
#  Correlación
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/correlacion",
    summary="Nube de puntos entre dos metricas, con su coeficiente",
)
async def correlacion(
    x: str = Query("temperatura"),
    y: str = Query("ec"),
    dias: int = Query(DIAS_DEF, ge=1, le=90),
    muestras: int = Query(1200, ge=50, le=5000),
    _user: dict = Depends(get_current_user),
):
    """
    Responde lo que una serie temporal esconde: si la EC sube porque sube
    la temperatura —la conductividad de una solución depende de ella— o
    por su cuenta.

    Se submuestrea en el servidor: 30.000 puntos en una nube no se leen
    mejor que 1.200, y sí bloquean el navegador.
    """
    for nombre in (x, y):
        if nombre not in _METRICAS_SERIE:
            raise HTTPException(status_code=400,
                                detail=f"Metrica no reconocida: {nombre}")
    cx, cy = _METRICAS_SERIE[x], _METRICAS_SERIE[y]

    puntos = _filas(f"""
        SELECT ROUND({cx}::numeric, 2) AS x,
               ROUND({cy}::numeric, 2) AS y,
               EXTRACT(HOUR FROM t_rx)::int AS hora
        FROM telemetria_indoor
        WHERE {cx} IS NOT NULL AND {cy} IS NOT NULL
          AND t_rx > now() - (%s || ' days')::interval
        ORDER BY random() LIMIT %s
    """, (dias, muestras))

    coef = _una(f"""
        SELECT ROUND(CORR({cx}, {cy})::numeric, 3) AS r, COUNT(*) AS n
        FROM telemetria_indoor
        WHERE {cx} IS NOT NULL AND {cy} IS NOT NULL
          AND t_rx > now() - (%s || ' days')::interval
    """, (dias,))

    return {"x": x, "y": y, "puntos": puntos, **coef}


# ═══════════════════════════════════════════════════════════════
#  Perfil horario
# ═══════════════════════════════════════════════════════════════

@metricas_router.get(
    "/perfil-horario",
    summary="Las 24 horas del dia promediadas sobre toda la ventana",
)
async def perfil_horario(
    dias: int = Query(14, ge=1, le=90),
    _user: dict = Depends(get_current_user),
):
    """
    Colapsa la ventana en un día tipo. Es lo que deja ver el efecto del
    fotoperiodo —la luz enciende a las 6 y apaga a las 18— sobre la
    temperatura y sobre el enlace: el balastro y el ventilador son ruido
    electromagnético, y eso se paga en el RSSI.
    """
    return {
        "horas": _filas("""
            SELECT EXTRACT(HOUR FROM t_rx)::int          AS hora,
                   COUNT(*)                              AS n,
                   ROUND(AVG(temperatura)::numeric, 2)   AS temperatura,
                   ROUND(AVG(humedad_ambiente)::numeric, 2) AS humedad,
                   ROUND(AVG(ec)::numeric, 1)            AS ec,
                   ROUND(AVG(rssi)::numeric, 1)          AS rssi,
                   ROUND(STDDEV_SAMP(rssi)::numeric, 2)  AS rssi_sigma,
                   COUNT(*) FILTER (WHERE rssi < -70)    AS rssi_bajo
            FROM telemetria_indoor
            WHERE t_rx > now() - (%s || ' days')::interval
            GROUP BY 1 ORDER BY 1
        """, (dias,)),
        "riego_por_hora": _filas("""
            SELECT EXTRACT(HOUR FROM ts)::int AS hora, COUNT(*) AS ciclos
            FROM node_eventos
            WHERE evento LIKE 'riego_%%_fin'
              AND ts > now() - (%s || ' days')::interval
            GROUP BY 1 ORDER BY 1
        """, (dias,)),
    }
