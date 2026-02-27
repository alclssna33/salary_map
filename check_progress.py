import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='medigate', user='postgres', password='postgres')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM recruit_posts WHERE source='medigate'")
total = cur.fetchone()[0]
print(f"총 저장 건수: {total:,}건")

cur.execute("SELECT COUNT(*) FROM recruit_post_specialties")
spec = cur.fetchone()[0]
print(f"전공 태그 수: {spec:,}개")

cur.execute("SELECT region_sido, COUNT(*) FROM recruit_posts WHERE source='medigate' GROUP BY region_sido ORDER BY COUNT(*) DESC LIMIT 10")
print("\n지역별 상위 10:")
for row in cur.fetchall():
    print(f"  {row[0]!r}: {row[1]:,}건")

cur.execute("SELECT LEFT(register_date, 7), COUNT(*) FROM recruit_posts WHERE source='medigate' GROUP BY LEFT(register_date, 7) ORDER BY LEFT(register_date, 7) DESC LIMIT 10")
print("\n등록월별 (최근 10개월):")
for row in cur.fetchall():
    print(f"  {row[0]!r}: {row[1]:,}건")

cur.execute("SELECT specialty, COUNT(*) FROM recruit_post_specialties GROUP BY specialty ORDER BY COUNT(*) DESC LIMIT 10")
print("\n전공별 상위 10:")
for row in cur.fetchall():
    print(f"  {row[0]!r}: {row[1]:,}건")

conn.close()
