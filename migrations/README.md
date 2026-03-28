# VitalCrop AGW — Supabase Database Migrations

Esquema completo de la base de datos PostgreSQL para el sistema **VitalCrop AGW** en Supabase.

---

## Orden de Ejecución

Ejecutar las migraciones **en orden numérico** en el SQL Editor de Supabase o via `psql`:

| # | Archivo | Descripción |
|---|---------|-------------|
| 1 | `001_create_users.sql` | Tabla `users` + enum `user_role` + trigger `updated_at` |
| 2 | `002_create_devices.sql` | Tabla `iot_devices` + enums `device_type`, `device_status` |
| 3 | `003_create_telemetry.sql` | Tabla particionada `telemetry` (por año) |
| 4 | `004_create_commands.sql` | Tabla `device_commands` + `expire_old_commands()` |
| 5 | `005_create_alerts.sql` | Tabla `alerts` + enums `alert_severity`, `alert_source` |
| 6 | `006_create_indexes.sql` | Todos los índices de rendimiento |
| 7 | `007_create_views.sql` | Vistas `device_last_telemetry`, `telemetry_daily_summary` |
| 8 | `008_create_functions.sql` | Funciones `get_telemetry_bucketed`, `get_device_stats`, `mark_alerts_read` |
| 9 | `009_enable_rls.sql` | Políticas de Row Level Security |
| 10 | `010_seed_data.sql` | Usuario admin + dispositivos de ejemplo |

### Ejecutar con psql

```bash
# Variables de entorno
export SUPABASE_DB_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres"

# Ejecutar todas las migraciones en orden
for i in $(ls migrations/*.sql | sort); do
  echo "⏳ Ejecutando $i ..."
  psql "$SUPABASE_DB_URL" -f "$i"
  echo "✅ $i completado"
done
```

### Ejecutar en Supabase SQL Editor

1. Ir a **Supabase Dashboard → SQL Editor**
2. Pegar y ejecutar cada archivo en orden numérico
3. Verificar que no haya errores antes de continuar con el siguiente

---

## Diagrama ER

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VitalCrop AGW Schema                        │
└─────────────────────────────────────────────────────────────────────┘

  users
  ┌──────────────────────────────────────┐
  │ id (PK, UUID)                        │
  │ email          TEXT UNIQUE           │
  │ password_hash  TEXT                  │
  │ full_name      TEXT                  │
  │ role           user_role             │◄── SUPERROOT|ADMIN|OPERATOR|VIEWER
  │ is_active      BOOLEAN               │
  │ last_login     TIMESTAMPTZ           │
  │ refresh_token_hash TEXT              │
  │ created_at / updated_at              │
  └──────────────────────┬───────────────┘
                         │ 1
                         │
                     ────┼────────────────────────────────────────
                         │ N
  iot_devices            │
  ┌──────────────────────▼───────────────┐
  │ id (PK, UUID)                        │
  │ device_uid     TEXT UNIQUE           │◄── AGW-SOIL-01, AGW-HYDRO-01
  │ device_type    device_type           │◄── SOIL | HYDRO
  │ user_id (FK → users.id)             │
  │ gateway_id     TEXT                  │◄── AGW-EDGE-01
  │ status         device_status         │◄── ONLINE|OFFLINE|MAINTENANCE|ERROR
  │ is_active      BOOLEAN               │
  │ last_seen      TIMESTAMPTZ           │
  │ ip_address     INET                  │
  │ mac_address    MACADDR               │
  │ config         JSONB                 │
  │ created_at / updated_at              │
  └──────┬──────────────┬───────┬────────┘
         │ 1            │ 1     │ 1
         │              │       │
         │ N            │ N     │ N
  ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
  │  telemetry  │ │  device_  │ │   alerts    │
  │  (parti-    │ │  commands │ │             │
  │  cionada)   │ │           │ │             │
  └─────────────┘ └───────────┘ └─────────────┘

  telemetry (PARTITION BY RANGE timestamp)
  ├── telemetry_2024
  ├── telemetry_2025
  ├── telemetry_2026
  └── telemetry_2027
```

---

## Configuración de RLS

El sistema usa **Row Level Security** de Supabase para aislamiento multi-tenant:

### Claves de API

| Clave | Scope | Uso |
|-------|-------|-----|
| `anon` | RLS activo | Usuarios no autenticados (sin acceso a datos) |
| `authenticated` | RLS activo (con `auth.uid()`) | Usuarios finales del dashboard |
| `service_role` | **Bypasses RLS** | Edge Gateway / Cloud API (inserción de telemetría) |

### Resumen de Políticas

| Tabla | Política | Regla |
|-------|----------|-------|
| `users` | `users_self_read` | Cada usuario ve solo su perfil; ADMIN/SUPERROOT ven todos |
| `users` | `users_admin_insert` | Solo ADMIN/SUPERROOT pueden crear usuarios |
| `iot_devices` | `devices_owner_access` | Solo dispositivos del `user_id` actual |
| `telemetry` | `telemetry_device_owner` | SELECT filtrado por dispositivos del usuario |
| `telemetry` | `telemetry_insert_service` | INSERT permitido (controlado por service_role en la API) |
| `device_commands` | `commands_owner_access` | Solo comandos de sus dispositivos |
| `device_commands` | `commands_create_authorized` | Solo OPERATOR/ADMIN/SUPERROOT pueden crear comandos |
| `alerts` | `alerts_user_access` | Cada usuario ve solo sus alertas |

### Verificar RLS activo

```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('users','iot_devices','telemetry','device_commands','alerts');
```

---

## Estrategia de Particionado

La tabla `telemetry` usa **PARTITION BY RANGE(timestamp)** con particiones anuales.

### Por qué particionado anual

- Con 1 lectura cada 30s por dispositivo → **~1M registros/dispositivo/año**
- Las queries del dashboard siempre filtran por `timestamp` reciente → acceden a 1 partición
- Las particiones antiguas pueden archivarse o eliminarse sin afectar el sistema

### Añadir partición para un nuevo año

```sql
-- Ejecutar antes del inicio del año nuevo
CREATE TABLE telemetry_2028 PARTITION OF telemetry
    FOR VALUES FROM ('2028-01-01 00:00:00+00') TO ('2029-01-01 00:00:00+00');
```

### Eliminar datos antiguos (archivado)

```sql
-- Opción 1: Drop completo (datos perdidos)
DROP TABLE telemetry_2024;

-- Opción 2: Detach + backup externo
ALTER TABLE telemetry DETACH PARTITION telemetry_2024;
-- Luego hacer dump y restaurar en cold storage
```

---

## Configuración de pg_cron

Para expirar comandos PENDING automáticamente, configurar `pg_cron` en Supabase:

### Habilitar pg_cron (una sola vez)

```sql
-- En Supabase, pg_cron ya está disponible — solo habilitar la extensión
CREATE EXTENSION IF NOT EXISTS pg_cron;
```

### Crear el job de expiración

```sql
-- Ejecutar expire_old_commands cada minuto
SELECT cron.schedule(
    'expire-pending-commands',      -- Nombre del job
    '* * * * *',                    -- Cron expression: cada minuto
    'SELECT expire_old_commands();'
);

-- Verificar que el job fue creado
SELECT * FROM cron.job WHERE jobname = 'expire-pending-commands';
```

### Jobs recomendados

```sql
-- Limpiar alertas INFO de más de 90 días
SELECT cron.schedule(
    'cleanup-old-info-alerts',
    '0 2 * * *',   -- 02:00 UTC diariamente
    $$DELETE FROM alerts WHERE severity = 'INFO' AND created_at < NOW() - INTERVAL '90 days'$$
);

-- Actualizar last_seen de dispositivos ONLINE → OFFLINE si no hay telemetría en 5 min
SELECT cron.schedule(
    'detect-offline-devices',
    '*/5 * * * *',   -- Cada 5 minutos
    $$
    UPDATE iot_devices
    SET status = 'OFFLINE'
    WHERE status = 'ONLINE'
      AND (last_seen IS NULL OR last_seen < NOW() - INTERVAL '5 minutes');
    $$
);
```

---

## Variables de Entorno para la Cloud API

```env
SUPABASE_URL=https://[PROJECT_REF].supabase.co
SUPABASE_ANON_KEY=eyJ...           # Para auth de usuarios
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # Para inserción de telemetría (Edge Gateway)
```

---

## Credenciales por Defecto (Seed)

> ⚠️ **Cambiar en producción inmediatamente después del primer login**

| Campo | Valor |
|-------|-------|
| Email | `admin@vitalcrop.io` |
| Password | `VitalCrop2024!` |
| Role | `SUPERROOT` |
