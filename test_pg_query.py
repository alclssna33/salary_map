import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="medigate", user="postgres", password="postgres"
)
df = pd.read_sql("""
    SELECT
        rp.region_sido            AS region,
        rps.specialty             AS specialty,
        LEFT(rp.register_date, 7) AS reg_month,
        COUNT(DISTINCT rp.id)     AS post_count
    FROM  recruit_posts             rp
    JOIN  recruit_post_specialties  rps ON rps.post_id = rp.id
    WHERE rp.register_date IS NOT NULL
      AND rp.register_date <> ''
      AND rp.region_sido   IS NOT NULL
      AND rp.region_sido   <> ''
    GROUP BY rp.region_sido, rps.specialty, LEFT(rp.register_date, 7)
    ORDER BY reg_month
""", conn)
conn.close()

print(f"총 행 수     : {len(df)}")
print(f"지역 목록    : {sorted(df['region'].unique().tolist())}")
print(f"진료과 수    : {df['specialty'].nunique()}")
print(f"월 범위      : {df['reg_month'].min()}  ~  {df['reg_month'].max()}")
print()
print("=== 월별 전체 집계 ===")
monthly = df.groupby("reg_month")["post_count"].sum().reset_index()
print(monthly.to_string(index=False))
