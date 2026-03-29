import os
import sys
import asyncio
import asyncpg

async def run():
    print("Connecting to Supabase...")
    dsn = "postgresql://postgres.sayqxmtvqaeyxhyptgpw:pg-crops-+4@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
    
    try:
        conn = await asyncpg.connect(dsn)
        print("Connected! Executing SQL migration 013...")
        
        with open('migrations/013_refactor_devices.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
            
        await conn.execute(sql)
        print("✅ Base de datos migrada correctamente (gateways y edge_nodes creados).")
        
        await conn.close()
        print("Proceso completado.")
    except Exception as e:
        print(f"Error en la conexión o migración: {e}")

if __name__ == "__main__":
    asyncio.run(run())
