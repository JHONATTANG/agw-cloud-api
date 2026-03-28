#!/usr/bin/env bash
# ==============================================================
#  test_api.sh — AGW Cloud API — Noxum Soluciones
#  Script de pruebas automatizadas contra todos los endpoints
#
#  Uso:
#    chmod +x test_api.sh
#    ./test_api.sh                          # prueba en localhost
#    BASE_URL="https://tu-app.vercel.app" ./test_api.sh   # producción
#    API_TOKEN="mi-token-real" BASE_URL="..." ./test_api.sh
#
#  Dependencias: curl, jq (opcional pero recomendado)
# ==============================================================

# ── Configuración ──────────────────────────────────────────
BASE_URL="${BASE_URL:-http://localhost:8000}"
API_TOKEN="${API_TOKEN:-dev-token-change-in-production}"
NODE_ID="FOG_RPI_HIERBABUENA_01"

# ── Colores ANSI ───────────────────────────────────────────
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

# ── Contadores ─────────────────────────────────────────────
PASSED=0
FAILED=0

# ── Helpers ────────────────────────────────────────────────
print_header() {
    echo ""
    echo -e "${CYAN}${BOLD}══════════════════════════════════════════════${RESET}"
    echo -e "${CYAN}${BOLD}  $1${RESET}"
    echo -e "${CYAN}${BOLD}══════════════════════════════════════════════${RESET}"
}

print_test() {
    echo -e "\n${BOLD}▶ TEST: $1${RESET}"
}

assert_status() {
    local EXPECTED="$1"
    local ACTUAL="$2"
    local LABEL="$3"

    if [ "$ACTUAL" -eq "$EXPECTED" ]; then
        echo -e "${GREEN}✔  PASS${RESET} — ${LABEL} (HTTP ${ACTUAL})"
        ((PASSED++))
    else
        echo -e "${RED}✘  FAIL${RESET} — ${LABEL} | Esperado: ${EXPECTED} | Obtenido: ${ACTUAL}"
        ((FAILED++))
    fi
}

pretty_json() {
    # Print JSON pretty if jq is available, else raw
    if command -v jq &> /dev/null; then
        echo "$1" | jq .
    else
        echo "$1"
    fi
}

# ── Inicio ─────────────────────────────────────────────────
print_header "AGW Cloud API — Test Suite"
echo -e "  ${BOLD}Base URL :${RESET} ${BASE_URL}"
echo -e "  ${BOLD}Node ID  :${RESET} ${NODE_ID}"
echo -e "  ${BOLD}Token    :${RESET} ${API_TOKEN:0:8}... (truncado)"
echo ""

# ==============================================================
# TEST 1 — GET / (Root Health Check)
# ==============================================================
print_test "GET / — Root health check"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "${BASE_URL}/")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 200 "$HTTP_CODE" "GET /"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 2 — GET /api/health (Detailed Health Check)
# ==============================================================
print_test "GET /api/health — Detailed health check con DB"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "${BASE_URL}/api/health")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 200 "$HTTP_CODE" "GET /api/health"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 3 — POST /api/telemetria (Sin token → debe fallar 401)
# ==============================================================
print_test "POST /api/telemetria — Sin token (debe retornar 401)"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/telemetria" \
    -H "Content-Type: application/json" \
    -d '{
        "node_id": "FOG_RPI_HIERBABUENA_01",
        "sensor_id": "ESP32_ZONA_A",
        "temperatura": 23.5
    }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 401 "$HTTP_CODE" "POST /api/telemetria sin token"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 4 — POST /api/telemetria (Con token — lectura completa)
# ==============================================================
print_test "POST /api/telemetria — Ingestión completa de hierbabuena"
PAYLOAD='{
    "node_id": "FOG_RPI_HIERBABUENA_01",
    "sensor_id": "ESP32_ZONA_A",
    "temperatura": 23.5,
    "humedad_ambiente": 65.2,
    "humedad_suelo": 82.0,
    "ph": 6.1,
    "estado_actuadores": "{\"bomba\": \"ON\", \"lampara\": \"ON\", \"ventilador\": \"OFF\"}"
}'

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/telemetria" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 201 "$HTTP_CODE" "POST /api/telemetria — lectura hierbabuena zona A"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 5 — POST /api/telemetria (Segunda zona — Zona B)
# ==============================================================
print_test "POST /api/telemetria — Segunda lectura (Zona B)"
PAYLOAD='{
    "node_id": "FOG_RPI_HIERBABUENA_01",
    "sensor_id": "ESP32_ZONA_B",
    "temperatura": 22.8,
    "humedad_ambiente": 67.0,
    "humedad_suelo": 84.3,
    "ph": 5.9,
    "estado_actuadores": "{\"bomba\": \"OFF\", \"lampara\": \"ON\", \"ventilador\": \"ON\"}"
}'

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/telemetria" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 201 "$HTTP_CODE" "POST /api/telemetria — lectura hierbabuena zona B"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 6 — POST /api/telemetria (Payload inválido — pH fuera de rango)
# ==============================================================
print_test "POST /api/telemetria — Payload inválido (pH > 14, debe retornar 422)"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/telemetria" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -d '{"node_id": "TEST_NODE", "sensor_id": "ESP32_TEST", "ph": 99.9}')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 422 "$HTTP_CODE" "POST /api/telemetria — pH fuera de rango"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 7 — GET /api/telemetria/{node_id} — Sin token (debe fallar 401)
# ==============================================================
print_test "GET /api/telemetria/${NODE_ID} — Sin token (debe retornar 401)"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "${BASE_URL}/api/telemetria/${NODE_ID}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 401 "$HTTP_CODE" "GET /api/telemetria/${NODE_ID} sin token"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 8 — GET /api/telemetria/{node_id} — Con token (últimos 50)
# ==============================================================
print_test "GET /api/telemetria/${NODE_ID} — Últimos 50 registros"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "${BASE_URL}/api/telemetria/${NODE_ID}" \
    -H "Authorization: Bearer ${API_TOKEN}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 200 "$HTTP_CODE" "GET /api/telemetria/${NODE_ID}"
echo "  Response:"
pretty_json "$BODY"

# ==============================================================
# TEST 9 — GET /api/telemetria/{node_id} — Nodo inexistente (lista vacía 200)
# ==============================================================
print_test "GET /api/telemetria/NODO_INEXISTENTE — Debe retornar 200 con lista vacía"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "${BASE_URL}/api/telemetria/NODO_INEXISTENTE_XYZ" \
    -H "Authorization: Bearer ${API_TOKEN}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

assert_status 200 "$HTTP_CODE" "GET /api/telemetria/NODO_INEXISTENTE_XYZ"
echo "  Response:"
pretty_json "$BODY"

# ── Resumen final ──────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  RESUMEN DE PRUEBAS${RESET}"
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════${RESET}"
TOTAL=$((PASSED + FAILED))
echo -e "  Total   : ${BOLD}${TOTAL}${RESET}"
echo -e "  ${GREEN}Exitosas : ${PASSED}${RESET}"
echo -e "  ${RED}Fallidas : ${FAILED}${RESET}"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✔  Todas las pruebas pasaron. ¡API lista para producción!${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}✘  ${FAILED} prueba(s) fallaron. Revisar los logs arriba.${RESET}"
    exit 1
fi
