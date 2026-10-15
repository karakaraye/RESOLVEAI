import os
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

host = os.environ.get("DB_HOST", "127.0.0.1")
port = os.environ.get("DB_PORT", "5432")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")
target_db = os.environ.get("DB_NAME", "resolveai")

def ensure_database():
    try:
        conn = psycopg2.connect(dbname="postgres", user=user, password=password, host=host, port=port)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;", (target_db,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(f'CREATE DATABASE "{target_db}";')
            print(f"Created PostgreSQL database '{target_db}' successfully.")
        else:
            print(f"PostgreSQL database '{target_db}' already exists.")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return False

if __name__ == "__main__":
    ensure_database()
