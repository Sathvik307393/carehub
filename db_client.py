import os
import json
import uuid
import psycopg2
from psycopg2.extras import Json
from psycopg2.pool import ThreadedConnectionPool

class PostgresCollection:
    def __init__(self, table_name, db_pool):
        self.table_name = table_name
        self.db_pool = db_pool
        # Create table with JSONB column if not exists
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"CREATE TABLE IF NOT EXISTS {self.table_name} (_id VARCHAR PRIMARY KEY, data JSONB)")
                conn.commit()
        finally:
            self.db_pool.put_conn(conn)

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = str(uuid.uuid4())
        if "id" not in document:
            document["id"] = document["_id"]
        
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {self.table_name} (_id, data) VALUES (%s, %s) ON CONFLICT (_id) DO UPDATE SET data = EXCLUDED.data",
                    (document["_id"], Json(document))
                )
                conn.commit()
        finally:
            self.db_pool.put_conn(conn)
        return document

    def find(self, filter_dict=None):
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                if not filter_dict:
                    cur.execute(f"SELECT data FROM {self.table_name}")
                else:
                    if "_id" in filter_dict and len(filter_dict) == 1:
                        cur.execute(f"SELECT data FROM {self.table_name} WHERE _id = %s", (filter_dict["_id"],))
                    else:
                        cur.execute(f"SELECT data FROM {self.table_name} WHERE data @> %s", (Json(filter_dict),))
                rows = cur.fetchall()
                return [row[0] for row in rows]
        finally:
            self.db_pool.put_conn(conn)

    def find_one(self, filter_dict):
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                if "_id" in filter_dict and len(filter_dict) == 1:
                    cur.execute(f"SELECT data FROM {self.table_name} WHERE _id = %s LIMIT 1", (filter_dict["_id"],))
                else:
                    cur.execute(f"SELECT data FROM {self.table_name} WHERE data @> %s LIMIT 1", (Json(filter_dict),))
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self.db_pool.put_conn(conn)

    def update_one(self, filter_dict, update_dict):
        doc = self.find_one(filter_dict)
        if not doc:
            return False
        
        set_data = update_dict.get("$set", update_dict)
        for k, v in set_data.items():
            doc[k] = v
            
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {self.table_name} SET data = %s WHERE _id = %s",
                    (Json(doc), doc["_id"])
                )
                conn.commit()
                return True
        finally:
            self.db_pool.put_conn(conn)

    def delete_one(self, filter_dict):
        doc = self.find_one(filter_dict)
        if not doc:
            return False
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {self.table_name} WHERE _id = %s", (doc["_id"],))
                conn.commit()
                return True
        finally:
            self.db_pool.put_conn(conn)

    def count_documents(self, filter_dict=None):
        conn = self.db_pool.get_conn()
        try:
            with conn.cursor() as cur:
                if not filter_dict:
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                else:
                    if "_id" in filter_dict and len(filter_dict) == 1:
                        cur.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE _id = %s", (filter_dict["_id"],))
                    else:
                        cur.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE data @> %s", (Json(filter_dict),))
                return cur.fetchone()[0]
        finally:
            self.db_pool.put_conn(conn)


class DBPool:
    def __init__(self):
        # Print diagnostic keys to help troubleshoot Azure DB variable names
        db_keys = [k for k in os.environ.keys() if any(x in k.upper() for x in ["CONN", "DB", "POSTGRES", "SQL", "URL"])]
        print(f"[DBPool] Diagnostic - Available DB-related keys: {db_keys}")

        # 1. Search for DATABASE_URL or AZURE_POSTGRESQL_CONNECTION_STRING
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("AZURE_POSTGRESQL_CONNECTION_STRING")
        
        # 2. Check if Azure Connection Strings tab injected it (prefixed with POSTGRESQLCONNSTR_)
        if not db_url:
            for key, val in os.environ.items():
                if key.startswith("POSTGRESQLCONNSTR_"):
                    db_url = val
                    print(f"Found Azure connection string: {key}")
                    break

        try:
            if db_url:
                self.pool = ThreadedConnectionPool(1, 20, dsn=db_url)
            else:
                # Check if running on Azure App Service
                is_azure = "WEBSITE_INSTANCE_ID" in os.environ or "WEBSITE_SITE_NAME" in os.environ
                if is_azure:
                    print("="*80)
                    print("[DBPool] WARNING: Running on Azure App Service but no PostgreSQL environment variables")
                    print("  (DATABASE_URL or AZURE_POSTGRESQL_CONNECTION_STRING) were found!")
                    print("  Defaulting to localhost (127.0.0.1), which will fail because PostgreSQL is not running locally.")
                    print("  Please configure your database connection string in the Azure Web App Application Settings.")
                    print("="*80)

                # 3. Fallback to individual Azure/Docker settings or local defaults
                host = os.environ.get("AZURE_POSTGRESQL_HOST") or os.environ.get("DB_HOST", "127.0.0.1")
                port = int(os.environ.get("AZURE_POSTGRESQL_PORT") or os.environ.get("DB_PORT", 5432))
                user = os.environ.get("AZURE_POSTGRESQL_USER") or os.environ.get("DB_USER", "postgres")
                password = os.environ.get("AZURE_POSTGRESQL_PASSWORD") or os.environ.get("DB_PASSWORD", "SecurePass123!@")
                database = os.environ.get("AZURE_POSTGRESQL_DB") or os.environ.get("AZURE_POSTGRESQL_DATABASE") or os.environ.get("DB_NAME", "autohub")
                
                self.pool = ThreadedConnectionPool(
                    1, 20,
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database
                )
            print("PostgreSQL connection pool initialized.")
        except Exception as e:
            print(f"Error initializing PostgreSQL pool: {e}")
            raise e

    def get_conn(self):
        return self.pool.getconn()

    def put_conn(self, conn):
        self.pool.putconn(conn)

db_client = DBPool()

def get_db_collection(name):
    return PostgresCollection(name, db_client)
