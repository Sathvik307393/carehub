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
        db_url = os.environ.get("DATABASE_URL")
        try:
            if db_url:
                self.pool = ThreadedConnectionPool(1, 20, dsn=db_url)
            else:
                self.pool = ThreadedConnectionPool(
                    1, 20,
                    host="127.0.0.1",
                    port=5432,
                    user="postgres",
                    password="SecurePass123!@",
                    database="autohub"
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
