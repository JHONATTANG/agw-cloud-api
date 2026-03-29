# API_SERVICES.md — AGW Cloud API
## Vital Crop · Sistema Hidropónico Indoor de Hierbabuena

> **Versión:** 2.0.0 · **Repositorio:** `agw-cloud-api` · **Despliegue:** Vercel Serverless (Python 3.11)

---

## Arquitectura de Seguridad

Todos los endpoints de datos están protegidos con un **Bearer Token estático** compartido entre el Gateway (Raspberry Pi) y la API Cloud. Este token se configura como variable de entorno en Vercel y en la SD del Raspberry Pi.

```
Authorization: Bearer <API_TOKEN>
```

> [!IMPORTANT]
> El token debe ser un string de al menos 32 bytes aleatorios. Generarlo con:
> `python -c "import secrets; print(secrets.token_urlsafe(32))"`

---

## Configuración Base

| Parámetro | Valor |
|---|---|
| Base URL (local) | `http://localhost:8000` |
| Base URL (producción) | `https://<tu-proyecto>.vercel.app` |
| Content-Type | `application/json` |
| Autenticación | `Bearer Token` (header `Authorization`) |
| Timeout recomendado | 30 segundos |
| Pooler BD | Supabase Transaction Pooler — puerto `6543` |

---

## Endpoints

### 1. `GET /` — Root Health Check

**Propósito:** Punto de entrada raíz. Responde 200 para que Vercel no retorne un 404 en la URL base del proyecto.

**Autenticación:** ❌ No requerida

**Request:**
```http
GET / HTTP/1.1
Host: tu-proyecto.vercel.app
```

**Respuesta exitosa — 200 OK:**
```json
{
  "service": "AGW Cloud API",
  "version": "2.0.0",
  "organization": "Vital Crop",
  "status": "operational",
  "timestamp": "2026-03-28T23:45:00.123456+00:00"
}
```

**Códigos de respuesta:**

| Código | Descripción |
|---|---|
| `200 OK` | Servicio operativo |
| `500` | Error interno del servidor |

---

### 2. `GET /api/health` — Detailed Health Check

**Propósito:** Verifica el estado de la API **y** la conectividad con la base de datos PostgreSQL en Supabase. Esencial para monitoreo y alertas de infraestructura.

**Autenticación:** ❌ No requerida

**Request:**
```http
GET /api/health HTTP/1.1
Host: tu-proyecto.vercel.app
```

**Respuesta exitosa — 200 OK (base de datos conectada):**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "database": {
    "status": "connected",
    "latency_ms": 42.17,
    "pooler": "supabase-transaction-pooler"
  },
  "timestamp": "2026-03-28T23:45:00.123456+00:00"
}
```

**Respuesta degradada — 200 OK (base de datos no disponible):**
```json
{
  "status": "degraded",
  "version": "2.0.0",
  "database": {
    "status": "unreachable",
    "latency_ms": null,
    "pooler": "supabase-transaction-pooler"
  },
  "timestamp": "2026-03-28T23:45:00.123456+00:00"
}
```

> [!NOTE]
> El endpoint retorna **200** incluso si la BD falla (no 503), para evitar reintentos agresivos del health checker de Vercel. El campo `status` diferencia "ok" de "degraded".

**Códigos de respuesta:**

| Código | Descripción |
|---|---|
| `200 OK` | API respondiendo (revisar `status` interno) |

---

### 3. `POST /api/telemetria` — Ingerir Telemetría

**Propósito:** Recibe y persiste una lectura de sensores enviada por el Gateway Fog (Raspberry Pi). Inserta un registro en la tabla `telemetria_indoor` de Supabase.

**Autenticación:** ✅ **Requerida** — `Bearer Token`

**Request Headers:**
```http
POST /api/telemetria HTTP/1.1
Host: tu-proyecto.vercel.app
Content-Type: application/json
Authorization: Bearer <API_TOKEN>
```

**Request Body — Schema:**

| Campo | Tipo | Requerido | Descripción | Restricciones |
|---|---|---|---|---|
| `node_id` | `string` | ✅ | ID del Fog Gateway (Raspberry Pi) | 3–64 chars |
| `sensor_id` | `string` | ✅ | ID del nodo ESP32 origen | 3–64 chars |
| `temperatura` | `float` | ❌ | Temperatura ambiente en °C | -40 a 100 |
| `humedad_ambiente` | `float` | ❌ | Humedad relativa del aire (%) | 0 a 100 |
| `humedad_suelo` | `float` | ❌ | Humedad del sustrato/solución (%) | 0 a 100 |
| `ph` | `float` | ❌ | pH de la solución nutritiva | 0 a 14 |
| `estado_actuadores` | `string` | ❌ | Estado de actuadores (JSON como texto) | máx 255 chars |

**Request Body — Ejemplo real (cultivo hierbabuena, Zona A, ciclo diurno):**
```json
{
  "node_id": "FOG_RPI_HIERBABUENA_01",
  "sensor_id": "ESP32_ZONA_A",
  "temperatura": 23.5,
  "humedad_ambiente": 65.2,
  "humedad_suelo": 82.0,
  "ph": 6.1,
  "estado_actuadores": "{\"bomba\": \"ON\", \"lampara\": \"ON\", \"ventilador\": \"OFF\"}"
}
```

**Request Body — Ejemplo real (cultivo hierbabuena, Zona B, ciclo nocturno):**
```json
{
  "node_id": "FOG_RPI_HIERBABUENA_01",
  "sensor_id": "ESP32_ZONA_B",
  "temperatura": 19.8,
  "humedad_ambiente": 68.0,
  "humedad_suelo": 79.5,
  "ph": 5.9,
  "estado_actuadores": "{\"bomba\": \"OFF\", \"lampara\": \"OFF\", \"ventilador\": \"ON\"}"
}
```

**Respuesta exitosa — 201 Created:**
```json
{
  "status": "created",
  "id": 1042,
  "created_at": "2026-03-28T23:45:00.123456+00:00",
  "node_id": "FOG_RPI_HIERBABUENA_01",
  "sensor_id": "ESP32_ZONA_A"
}
```

**Códigos de respuesta:**

| Código | Descripción |
|---|---|
| `201 Created` | Registro insertado exitosamente |
| `401 Unauthorized` | Token ausente o inválido |
| `422 Unprocessable Entity` | Validación fallida (ej. pH > 14) |
| `500 Internal Server Error` | Error de conexión a BD |

**Ejemplo de error 422 (pH fuera de rango):**
```json
{
  "detail": [
    {
      "loc": ["body", "ph"],
      "msg": "Input should be less than or equal to 14",
      "type": "less_than_equal",
      "ctx": {"le": 14}
    }
  ]
}
```

---

### 4. `GET /api/telemetria/{node_id}` — Obtener Telemetría de un Nodo

**Propósito:** Retorna los **últimos 50 registros** de telemetría para un `node_id` específico, ordenados del más reciente al más antiguo.

**Autenticación:** ✅ **Requerida** — `Bearer Token`

**Parámetro de ruta:**

| Parámetro | Tipo | Descripción | Ejemplo |
|---|---|---|---|
| `node_id` | `string` | ID del Fog Gateway | `FOG_RPI_HIERBABUENA_01` |

**Request:**
```http
GET /api/telemetria/FOG_RPI_HIERBABUENA_01 HTTP/1.1
Host: tu-proyecto.vercel.app
Authorization: Bearer <API_TOKEN>
```

**Respuesta exitosa — 200 OK:**
```json
{
  "node_id": "FOG_RPI_HIERBABUENA_01",
  "count": 3,
  "records": [
    {
      "id": 1044,
      "created_at": "2026-03-28T23:50:00.000000+00:00",
      "node_id": "FOG_RPI_HIERBABUENA_01",
      "sensor_id": "ESP32_ZONA_A",
      "temperatura": 23.8,
      "humedad_ambiente": 64.9,
      "humedad_suelo": 81.5,
      "ph": 6.0,
      "estado_actuadores": "{\"bomba\": \"ON\", \"lampara\": \"ON\", \"ventilador\": \"OFF\"}"
    },
    {
      "id": 1043,
      "created_at": "2026-03-28T23:45:00.000000+00:00",
      "node_id": "FOG_RPI_HIERBABUENA_01",
      "sensor_id": "ESP32_ZONA_A",
      "temperatura": 23.5,
      "humedad_ambiente": 65.2,
      "humedad_suelo": 82.0,
      "ph": 6.1,
      "estado_actuadores": "{\"bomba\": \"ON\", \"lampara\": \"ON\", \"ventilador\": \"OFF\"}"
    },
    {
      "id": 1042,
      "created_at": "2026-03-28T23:40:00.000000+00:00",
      "node_id": "FOG_RPI_HIERBABUENA_01",
      "sensor_id": "ESP32_ZONA_B",
      "temperatura": 22.9,
      "humedad_ambiente": 66.1,
      "humedad_suelo": 83.2,
      "ph": 5.8,
      "estado_actuadores": "{\"bomba\": \"OFF\", \"lampara\": \"ON\", \"ventilador\": \"ON\"}"
    }
  ]
}
```

**Respuesta cuando el nodo no tiene registros — 200 OK:**
```json
{
  "node_id": "NODO_INEXISTENTE",
  "count": 0,
  "records": []
}
```

**Códigos de respuesta:**

| Código | Descripción |
|---|---|
| `200 OK` | Consulta exitosa (puede retornar lista vacía) |
| `401 Unauthorized` | Token ausente o inválido |
| `500 Internal Server Error` | Error de conexión a BD |

---

### 5. `POST /api/auth/request-code` — Solicitar Código Passwordless

**Propósito:** Inicia el flujo Passwordless. Recibe un email de un operador o agrónomo, genera un OTP y lo envía vía correo electrónico. Si el usuario no existe, lo aprovisiona automáticamente.

**Autenticación:** ❌ No requerida

**Request Body — Schema:**
```json
{
  "email": "jhonattan.gonzalez.38@gmail.com"
}
```

**Respuesta exitosa — 200 OK:**
```json
{
  "status": "ok",
  "message": "Código enviado a jhonattan.gonzalez.38@gmail.com"
}
```

---

### 6. `POST /api/auth/verify-code` — Validar Código y Obtener JWT

**Propósito:** Finaliza el flujo Passwordless validando el OTP. Retorna el Token JWT necesario para operar el Dashboard y gestionar dispositivos.

**Autenticación:** ❌ No requerida

**Request Body — Schema:**
```json
{
  "email": "jhonattan.gonzalez.38@gmail.com",
  "code": "481516"
}
```

**Respuesta exitosa — 200 OK:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
  "token_type": "bearer",
  "user_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "email": "jhonattan.gonzalez.38@gmail.com"
}
```

---

### 7. Endpoints Protegidos por JWT (`/api/users` & `/api/devices`)

Estos endpoints son utilizados por Web/App Dashboards y **requieren** el token JWT emitido por `/api/auth/verify-code` en lugar del Static Token IoT.

**Autenticación:** ✅ **Requerida** — `Bearer Token` (JWT)

#### `GET /api/users/me` — Perfil de Operador
Retorna la información del agricultor/operador autenticado.
```json
{
  "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "email": "jhonattan.gonzalez.38@gmail.com",
  "full_name": "Jhonattan Gonzalez",
  "created_at": "2026-03-28T20:00:00+00:00"
}
```

#### `GET /api/devices` — Listar Dispositivos Asignados
Retorna los nodos (Gateway o ESP32) asociados al operador.
```json
[
  {
    "id": 1,
    "user_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "node_id": "FOG_RPI_VITALCROP_01",
    "alias": "Gateway IoT Principal",
    "assigned_at": "2026-03-28T20:00:00+00:00"
  },
  {
    "id": 2,
    "user_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "node_id": "ESP32_SOIL_NODE_A",
    "alias": "Nodo de Suelo (Tierra)",
    "assigned_at": "2026-03-28T20:05:00+00:00"
  }
]
```

#### Otros Endpoints CRUD:
- `PUT /api/users/me`: Actualiza `full_name`. Payload: `{"full_name": "Nuevo Nombre"}`
- `POST /api/devices/assign`: Asocia nodo. Payload: `{"node_id": "ESP32_...", "alias": "Nombre"}`
- `PUT /api/devices/{id}`: Cambia alias. Payload: `{"alias": "Nuevo Alias"}`
- `DELETE /api/devices/{id}`: Remueve asignación.

---

## Referencia de Valores Óptimos — Hierbabuena (`Mentha spicata`)

| Parámetro | Rango Óptimo | Valor Crítico Bajo | Valor Crítico Alto |
|---|---|---|---|
| `temperatura` | 18 – 25 °C | < 10 °C | > 30 °C |
| `humedad_ambiente` | 50 – 70 % | < 35 % | > 85 % |
| `humedad_suelo` | 70 – 90 % | < 50 % | > 95 % |
| `ph` | **5.5 – 6.5** | < 5.0 | > 7.0 |

---

## Variables de Entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `DATABASE_URL` | ✅ | Connection string del Supabase Transaction Pooler (puerto 6543) |
| `API_TOKEN` | ✅ | Bearer token estático compartido con el Fog Node |

---

## Instrucciones de Despliegue CI/CD

### Paso 1 — Configurar Git y push al repositorio

```bash
# Navegar al directorio del proyecto
cd agw-cloud-api

# (Solo primera vez) Inicializar repositorio Git
git init
git branch -M main

# (Solo primera vez) Conectar repositorio remoto
git remote add origin https://github.com/JHONATTANG/agw-cloud-api.git

# Añadir todos los archivos nuevos/modificados al stage
git add api/index.py
git add vercel.json
git add requirements.txt
git add .env.example
git add migrations/011_create_telemetria_indoor.sql
git add test_api.sh
git add API_SERVICES.md

# Verificar el estado antes de hacer commit
git status

# Commit con mensaje descriptivo
git commit -m "feat(vercel): add serverless telemetria_indoor endpoints + migration + test suite

- api/index.py: Vercel ASGI entry point con Bearer Token auth + psycopg2
- vercel.json: Routing config para Python 3.11 serverless function  
- migrations/011: CREATE TABLE telemetria_indoor con indexes y constraints
- test_api.sh: 9 pruebas automatizadas con colores y validación HTTP
- API_SERVICES.md: Documentación exhaustiva de endpoints REST
- .env.example: Variables requeridas para Vercel + Docker"

# Push al repositorio remoto
git push -u origin main
```

### Paso 2 — Configurar Variables de Entorno en Vercel

```bash
# Instalar Vercel CLI si no lo tienes
npm install -g vercel

# Login
vercel login

# Establecer variables de entorno en producción
vercel env add DATABASE_URL production
# → Pegar: postgresql://postgres.sayqxmtvqaeyxhyptgpw:...@pooler.supabase.com:6543/postgres

vercel env add API_TOKEN production
# → Pegar: tu-token-de-32-bytes-generado

# Desplegar
vercel --prod
```

### Paso 3 — Aplicar migración en Supabase

```sql
-- Ejecutar en: Supabase Dashboard → SQL Editor → New Query
-- Archivo: migrations/011_create_telemetria_indoor.sql
```

### Paso 4 — Verificar el despliegue

```bash
# Reemplazar con tu URL de Vercel
export BASE_URL="https://agw-cloud-api.vercel.app"
export API_TOKEN="tu-token-real"

# Ejecutar suite de pruebas
chmod +x test_api.sh
./test_api.sh
```

---

## Flujo de Datos IoT

```
ESP32 Zona A ──┐
ESP32 Zona B ──┤──► Raspberry Pi (Fog Gateway) ──► POST /api/telemetria ──► Supabase
ESP32 Zona N ──┘         (agw-edge-raspberry)            (agw-cloud-api)    (telemetria_indoor)
                                                                │
                                                                ▼
                                                   Next.js Dashboard
                                              GET /api/telemetria/{node_id}
```
