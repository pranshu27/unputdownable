import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
c = psycopg.connect(os.getenv("POSTGRES_URL"), autocommit=True)
print("user:", c.execute("select current_user").fetchone())
print("db:", c.execute("select current_database()").fetchone())
print("search_path:", c.execute("show search_path").fetchone())
print("schemas:", c.execute("select schema_name from information_schema.schemata").fetchall())
for test in ("CREATE SCHEMA IF NOT EXISTS rag",):
    try:
        c.execute(test)
        print("OK:", test)
    except Exception as e:
        print("FAIL:", test, "->", str(e).splitlines()[0])
try:
    c.execute("CREATE TABLE IF NOT EXISTS rag._probe (id int)")
    c.execute("DROP TABLE rag._probe")
    print("OK: create/drop table in rag schema")
except Exception as e:
    print("FAIL: rag table ->", str(e).splitlines()[0])
