-- ============================================================
--  007_eventos_reales.sql — La misma frontera, para los eventos
-- ============================================================
--  La 006 separó la telemetría del nodo simulado de la del real, pero
--  los eventos —inicio y fin de cada riego, caídas, reconexiones—
--  siguieron entrando en `node_eventos` sin esa frontera. Se notó en
--  /diario: contaba 110 riegos al día con 288 tramas, porque las
--  tramas venían de la vista y los riegos de la tabla entera. Un nodo
--  que riega 60 veces al día no puede sumar 110 sin que alguien lo
--  note, y aun así tardó semanas.
--
--  Misma regla y misma forma que `telemetria_real`: LEFT JOIN para que
--  un sensor sin alta cuente como real, y una sola definición para que
--  ninguna consulta pueda olvidarse el filtro.

CREATE OR REPLACE VIEW public.eventos_reales AS
    SELECT e.*
    FROM public.node_eventos e
    LEFT JOIN public.edge_nodes n ON n.sensor_id = e.sensor_id
    WHERE COALESCE(n.simulado, false) = false;

COMMENT ON VIEW public.eventos_reales IS
    'node_eventos sin los nodos simulados. Fuente de las metricas del '
    '§9 cuando no se pregunta por un nodo concreto.';
