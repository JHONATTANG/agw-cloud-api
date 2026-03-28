-- ============================================================
-- MIGRATION 001: users
-- Usuarios del sistema (SUPERROOT, ADMIN, OPERATOR, VIEWER)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE user_role AS ENUM ('SUPERROOT', 'ADMIN', 'OPERATOR', 'VIEWER');

CREATE TABLE users (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT        UNIQUE NOT NULL
                            CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    password_hash       TEXT        NOT NULL,
    full_name           TEXT,
    role                user_role   NOT NULL DEFAULT 'OPERATOR',
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login          TIMESTAMPTZ,
    refresh_token_hash  TEXT,           -- Hash del último refresh token activo
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------
-- Función genérica para mantener updated_at al día
-- (reutilizada por todas las tablas siguientes)
-- -------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- -------------------------------------------------------
-- Comentarios
-- -------------------------------------------------------
COMMENT ON TABLE  users                     IS 'Usuarios del sistema VitalCrop AGW';
COMMENT ON COLUMN users.role                IS 'SUPERROOT: acceso total | ADMIN: gestión | OPERATOR: control | VIEWER: solo lectura';
COMMENT ON COLUMN users.refresh_token_hash  IS 'Bcrypt hash del último refresh token emitido; invalida sesiones anteriores al rotar';
