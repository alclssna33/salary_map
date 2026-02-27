import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='medigate', user='postgres', password='postgres')
cur = conn.cursor()

# 총 건수
cur.execute('SELECT COUNT(*) FROM recruit_posts')
total = cur.fetchone()[0]
print(f'총 데이터 수: {total:,}건')

# 등록일 범위
cur.execute("SELECT MIN(register_date), MAX(register_date) FROM recruit_posts WHERE register_date IS NOT NULL AND register_date != ''")
mn, mx = cur.fetchone()
print(f'등록일 범위: {mn} ~ {mx}')

# 월별
cur.execute("""
SELECT SUBSTRING(register_date, 1, 7) as ym, COUNT(*) as cnt
FROM recruit_posts
WHERE register_date IS NOT NULL AND register_date != ''
GROUP BY ym ORDER BY ym
""")
monthly = cur.fetchall()
print()
print('[월별 데이터 수]')
for m, c in monthly:
    print(f'  {m}: {c:,}건')

# 시도별
cur.execute('SELECT region_sido, COUNT(*) FROM recruit_posts GROUP BY region_sido ORDER BY COUNT(*) DESC LIMIT 20')
regions = cur.fetchall()
print()
print('[시도별 데이터 수]')
for r, c in regions:
    print(f'  {r}: {c:,}건')

# 과별 (specialties 테이블)
cur.execute('SELECT specialty, COUNT(*) FROM recruit_post_specialties GROUP BY specialty ORDER BY COUNT(*) DESC LIMIT 20')
specs = cur.fetchall()
print()
print('[과별 데이터 수 TOP20]')
for s, c in specs:
    print(f'  {s}: {c:,}건')

conn.close()
