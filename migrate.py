import os
import sys
import asyncio
import asyncpg

async def run():
    print("Connecting to Supabase (Port 5432 - Direct IP/Pooler for Migrations)...")
    dsn = "postgresql://postgres.sayqxmtvqaeyxhyptgpw:pg-crops-+4@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
    
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected! Executing SQL migration 011...")
        
        with open('migrations/011_create_telemetria_indoor.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
            
        await conn.execute(sql)
        print("✅ Base de datos migrada correctamente: tabla telemetria_indoor y sus indices creados.")
        
        seed_sql = """
            INSERT INTO telemetria_indoor (node_id, sensor_id, temperatura, humedad_ambiente, humedad_suelo, ph, estado_actuadores)
            VALUES 
                ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_A', 23.5, 65.2, 82.0, 6.1, '{"bomba": "ON", "lampara": "ON"}'),
                ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_B', 22.9, 66.1, 83.2, 5.9, '{"bomba": "OFF", "lampara": "ON"}');
        """
        
        try:
            await conn.execute(seed_sql)
            print("✅ Datos de prueba insertados (Seed Data).")
        except asyncpg.exceptions.UniqueViolationError:
            print("Datos de prueba ya existían o hubo un conflicto.")
        except Exception as e:
            print(f"Nota en seed data: {e}")
            
        await conn.close()
        print("Proceso completado.")
    except Exception as e:
        print(f"Error en la conexión a la bd: {e}")

if __name__ == "__main__":
    asyncio.run(run())
