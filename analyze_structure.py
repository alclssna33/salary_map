#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공고 카드 구조 정밀 분석 - 파일로 저장"""
import re
from bs4 import BeautifulSoup

with open('new_site_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
lines = []

def add(txt):
    lines.append(str(txt))

# 총 공고 수 확인
add("=== 총 공고 수 ===")
total_count_divs = soup.find_all(string=re.compile(r'5,\d{3}건'))
for t in total_count_divs:
    add(f"  총 건수 텍스트: {t.strip()!r}")

# /recruit/숫자 링크 찾기
recruit_links = [
    a for a in soup.find_all('a')
    if re.match(r'^/recruit/\d+$', a.get('href', ''))
]
add(f"\n=== /recruit/숫자 링크 수: {len(recruit_links)} ===")

# 카드 컨테이너 파악
if recruit_links:
    # 첫 링크의 부모 체인을 올라가며 "여러 형제를 가진" div 찾기
    add("\n--- 카드 컨테이너 탐색 ---")
    first_link = recruit_links[0]
    card_elem = first_link
    for _ in range(8):
        card_elem = card_elem.parent
        if not card_elem or card_elem.name in ['html', 'body']:
            break
        sibling_count = sum(
            1 for s in card_elem.parent.children
            if getattr(s, 'get', None) and s.get('class') == card_elem.get('class')
        )
        if sibling_count >= 10:
            add(f"카드 컨테이너: <{card_elem.name} class='{' '.join(card_elem.get('class',[]))[:80]}'>")
            add(f"  형제 수: {sibling_count}")
            break

    add("\n--- 첫 번째 카드 텍스트 (pipe 구분) ---")
    add(card_elem.get_text(separator=' | ', strip=True)[:400])

    add("\n--- 너비 기반 div 분석 ---")
    for width in ['220px', '130px', '120px', '90px']:
        divs = card_elem.select(f'div[class*="w-[{width}]"]')
        add(f"\n  w-[{width}] div ({len(divs)}개):")
        for d in divs:
            add(f"    텍스트: {d.get_text(separator='/', strip=True)!r}")

    add("\n--- 각 카드 요약 (처음 10개) ---")
    for i, link in enumerate(recruit_links[:10]):
        card = link
        for _ in range(8):
            card = card.parent
            if not card or card.name in ['html','body']:
                break
            sc = sum(1 for s in card.parent.children
                     if getattr(s,'get',None) and s.get('class') == card.get('class'))
            if sc >= 10:
                break

        # 너비별 컬럼 추출
        w220 = card.select_one('div[class*="w-[220px]"]')
        w130 = card.select_one('div[class*="w-[130px]"]')
        w120 = card.select_one('div[class*="w-[120px]"]')

        hospital_name = w220.get_text(separator='/', strip=True) if w220 else '?'
        region_employ = w130.get_text(separator='/', strip=True) if w130 else '?'
        date_info     = w120.get_text(separator='/', strip=True) if w120 else '?'

        # 제목 (버튼 텍스트)
        btn = card.select_one('button')
        title = btn.get_text(strip=True)[:60] if btn else '?'

        # 전공 태그 (my-1n83qxm 클래스)
        spec_spans = card.select('span.my-1n83qxm')
        specialties = [s.get_text(strip=True) for s in spec_spans]

        add(f"\n공고 {i+1} href={link.get('href')!r}")
        add(f"  병원: {hospital_name!r}")
        add(f"  지역/고용: {region_employ!r}")
        add(f"  날짜: {date_info!r}")
        add(f"  제목: {title!r}")
        add(f"  전공: {specialties}")

# 페이지네이션 분석
add("\n\n=== 페이지네이션 ===")
pag_elements = soup.select('[class*="pag"]')
add(f"  pag* 클래스 요소: {len(pag_elements)}")
for p in pag_elements[:5]:
    add(f"  {p.name} class={' '.join(p.get('class',[]))!r}: {p.get_text(strip=True)[:80]!r}")

# 숫자 페이지 버튼
page_buttons = [
    a for a in soup.find_all('a')
    if a.get_text(strip=True).isdigit()
]
add(f"\n  숫자 페이지 버튼: {[a.get_text(strip=True) for a in page_buttons]}")
for a in page_buttons[:5]:
    add(f"  href={a.get('href','')!r} class={' '.join(a.get('class',[]))[:50]!r}")

with open('structure_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("분석 완료! structure_analysis.txt 파일을 확인하세요.")
