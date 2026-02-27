import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='medigate', user='postgres', password='postgres')
cur = conn.cursor()

cur.execute("""
    SELECT rp.id, rp.hospital_name, rp.region, rp.register_date
    FROM recruit_posts rp
    WHERE rp.hospital_name LIKE '%모두탑365%'
    ORDER BY rp.register_date DESC
""")
posts = cur.fetchall()
print(f'총 {len(posts)}건')
for pid, name, region, reg_date in posts:
    cur.execute('SELECT specialty FROM recruit_post_specialties WHERE post_id=%s', (pid,))
    specs = [r[0] for r in cur.fetchall()]
    print(f'{reg_date} | {name} | {region} | {specs}')

conn.close()
