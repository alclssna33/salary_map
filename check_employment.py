import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="medigate", user="postgres", password="postgres"
)
cur = conn.cursor()

cur.execute("""
    SELECT employment_type, COUNT(*) AS cnt
    FROM recruit_posts
    GROUP BY employment_type
    ORDER BY cnt DESC
""")
rows = cur.fetchall()
conn.close()

with open("employment_types.txt", "w", encoding="utf-8") as f:
    f.write("=== employment_type 값 분포 ===\n")
    for r in rows:
        f.write(f"  {str(r[0]):20s}  {r[1]}건\n")

print("저장 완료: employment_types.txt")
