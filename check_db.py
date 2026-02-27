import psycopg2

try:
    conn = psycopg2.connect(host='localhost', port=5432, dbname='medigate', user='postgres', password='postgres')
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = cur.fetchall()
    print('=== 테이블 목록 ===')
    print(tables)
    for t in tables:
        cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{t[0]}' ORDER BY ordinal_position")
        cols = cur.fetchall()
        print(f'\n--- {t[0]} ---')
        for c in cols:
            print(f'  {c[0]}: {c[1]}')
    conn.close()
except Exception as e:
    print('Error:', e)
