import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="medigate", user="postgres", password="postgres"
)
cur = conn.cursor()

# 1) 테이블 목록
cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
print("=== 테이블 목록 ===")
tables = [r[0] for r in cur.fetchall()]
for t in tables:
    print(" -", t)

# 2) 각 테이블 컬럼 & 샘플
for t in tables:
    cur.execute(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='{t}'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f"\n=== {t}  ({cnt}건) ===")
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    if cnt > 0:
        cur.execute(f"SELECT * FROM {t} LIMIT 3")
        rows = cur.fetchall()
        print("  --- 샘플 ---")
        for r in rows:
            print(" ", r)

conn.close()
