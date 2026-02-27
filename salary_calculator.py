#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국 봉직의 월 실수령액 계산기 (2025년 기준)
─────────────────────────────────────────────
공제 항목
  · 국민연금    4.5%   (기준소득월액 상한 617만원 → 월 최대 277,650원)
  · 건강보험    3.545%
  · 장기요양    건강보험료 × 12.95%
  · 고용보험    0.9%
  · 소득세      누진세율 6~45% (근로소득공제 + 본인 기본공제 150만원 반영)
  · 지방소득세  소득세 × 10%
  · 식대 비과세 월 20만원 적용

퇴직금 월 환산
  · 1년 근무 기준 법정 퇴직금 = 1개월 평균 Gross 임금
  · 월 환산 = Gross_월급 / 12
  · Net 공고: Gross 역산(binary search) 후 동일 방식 적용
"""

import re

# ══════════════════════════════════════════════════════════════
# 상수 (2025년 기준)
# ══════════════════════════════════════════════════════════════
MEAL_NONTAX        = 200_000      # 식대 비과세 월 20만원
PENSION_RATE       = 0.045        # 국민연금 4.5%
PENSION_CAP        = 6_170_000    # 국민연금 기준소득월액 상한
HEALTH_RATE        = 0.03545      # 건강보험 3.545%
LTC_RATIO          = 0.1295       # 장기요양 = 건강보험료 × 12.95%
EMP_RATE           = 0.009        # 고용보험 0.9%

# 소득세 세율표 (과세표준 상한, 세율, 누진공제액)
_TAX_TABLE = [
    (   14_000_000, 0.06,          0),
    (   50_000_000, 0.15,  1_260_000),
    (   88_000_000, 0.24,  5_760_000),
    (  150_000_000, 0.35, 15_440_000),
    (  300_000_000, 0.38, 19_940_000),
    (  500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (  float('inf'), 0.45, 65_940_000),
]


# ══════════════════════════════════════════════════════════════
# 세금 계산 내부 함수
# ══════════════════════════════════════════════════════════════

def _earned_income_deduction(annual_gross):
    """근로소득공제 (한도 2,000만원)"""
    if annual_gross <= 5_000_000:
        d = annual_gross * 0.70
    elif annual_gross <= 15_000_000:
        d = 3_500_000 + (annual_gross - 5_000_000) * 0.40
    elif annual_gross <= 45_000_000:
        d = 7_500_000 + (annual_gross - 15_000_000) * 0.15
    elif annual_gross <= 100_000_000:
        d = 12_000_000 + (annual_gross - 45_000_000) * 0.05
    else:
        d = 14_750_000
    return min(d, 20_000_000)


def _income_tax(taxable):
    """소득세 (누진세율표)"""
    if taxable <= 0:
        return 0
    for limit, rate, deduction in _TAX_TABLE:
        if taxable <= limit:
            return max(0, int(taxable * rate - deduction))
    return int(taxable * 0.45 - 65_940_000)


def _tax_credit(tax, annual_gross):
    """근로소득세액공제"""
    credit = 715_000 + (tax - 1_300_000) * 0.30 if tax > 1_300_000 else tax * 0.55
    if annual_gross <= 33_000_000:
        cap = 740_000
    elif annual_gross <= 70_000_000:
        cap = 660_000
    else:
        cap = 500_000
    return min(credit, cap)


def gross_monthly_to_net_monthly(gross_monthly_won: int) -> int:
    """
    월 Gross(원) → 월 Net 실수령액(원)  ※ 퇴직금 미포함
    식대 비과세 20만원, 부양가족 본인만 적용
    """
    taxable_m = max(0, gross_monthly_won - MEAL_NONTAX)

    pension    = min(taxable_m * PENSION_RATE, PENSION_CAP * PENSION_RATE)
    health     = taxable_m * HEALTH_RATE
    ltc        = health * LTC_RATIO
    employment = taxable_m * EMP_RATE

    annual_g   = taxable_m * 12
    eid        = _earned_income_deduction(annual_g)
    taxable_y  = max(0, annual_g - eid - 1_500_000)   # 본인 기본공제 150만원
    tax_y      = _income_tax(taxable_y)
    credit     = _tax_credit(tax_y, annual_g)
    income_tax = max(0, tax_y - credit) / 12
    local_tax  = income_tax * 0.10

    total_ded = pension + health + ltc + employment + income_tax + local_tax
    return round(gross_monthly_won - total_ded)


def _estimate_gross_from_net(target_net_won: int) -> int:
    """
    Net 월급(원) → 추정 Gross 월급(원)
    binary search (40회 반복, ±1,000원 오차 이내)
    """
    lo, hi = target_net_won, target_net_won * 3
    for _ in range(40):
        mid = (lo + hi) // 2
        computed = gross_monthly_to_net_monthly(mid)
        if abs(computed - target_net_won) <= 1_000:
            return mid
        if computed < target_net_won:
            lo = mid
        else:
            hi = mid
    return (lo + hi) // 2


def calc_net_with_retirement(salary_type: str, monthly_gross_or_net_won: int) -> int:
    """
    최종 월 실수령 + 퇴직금 월 환산 (원 단위 반환)

    salary_type == 'gross':
        net = gross_monthly_to_net_monthly(gross)
        retirement = gross / 12
        return net + retirement

    salary_type == 'net':
        공고 기재 Net 그대로 반환 (퇴직금 미합산)
        return net
    """
    if salary_type == 'gross':
        gross = monthly_gross_or_net_won
        net   = gross_monthly_to_net_monthly(gross)
        return round(net + gross / 12)
    else:  # 'net': 공고 기재 Net 그대로
        return monthly_gross_or_net_won


# ══════════════════════════════════════════════════════════════
# 급여 텍스트 파싱
# ══════════════════════════════════════════════════════════════

_PAT_NET   = re.compile(r'세후|[Nn]et\b|실수령')
_PAT_GROSS = re.compile(r'세전|[Gg]ross\b')
_PAT_ANN   = re.compile(r'연봉|연간|년봉')
_PAT_MON   = re.compile(r'월급|월봉|월\s*수령|/월')
_PAT_NEGO  = re.compile(r'협의|면접\s*후|추후|결정|미정')

# 범위: "1,800이상~1,850미만(만원)" / "1800~1850만원"
_PAT_RANGE = re.compile(
    r'([\d,]+)\s*(?:이상)?\s*[~～]\s*([\d,]+)\s*(?:미만|이하)?\s*(?:\(만원\)|만원|만\s*원)'
)
# 억 단위: "3억", "1억5000만", "2억 5천만"
_PAT_EOK   = re.compile(r'(\d+)\s*억(?:\s*(\d+)\s*(?:천만|천|만))?')
# 만원 단위: "2,000만원", "1800만원", "2,000(만원)"
_PAT_MAN   = re.compile(r'([\d,]+)\s*(?:만원|만\s*원|\(만원\))')
# 3~4자리 단독 숫자 (문맥상 만원 단위)
_PAT_NUM   = re.compile(r'\b(\d{3,4})\b')


def _clean(text: str) -> str:
    """천단위 콤마 제거"""
    return re.sub(r'(\d),(\d{3})\b', r'\1\2', text)


def _parse_eok(m: re.Match) -> int:
    """억 단위 매치 → 만원 정수"""
    val = int(m.group(1)) * 10_000
    if m.group(2):
        sub = int(m.group(2))
        full = m.group(0)
        if '천만' in full:
            val += sub * 1_000
        elif '천' in full:
            val += sub * 1_000   # '천' 단독 = 천만원으로 해석
        else:
            val += sub           # '만' 단독
    return val


def _extract_numbers(raw: str):
    """급여 텍스트 → (min_만원, max_만원) or (None, None)"""
    text = _clean(raw)

    # 1. 범위 "X이상~Y미만(만원)"
    m = _PAT_RANGE.search(text)
    if m:
        v1 = int(m.group(1).replace(',', ''))
        v2 = int(m.group(2).replace(',', ''))
        return v1, v2

    # 2. 억 단위
    eok_matches = list(_PAT_EOK.finditer(text))
    if eok_matches:
        vals = [_parse_eok(m) for m in eok_matches]
        if len(vals) >= 2:
            return vals[0], vals[1]
        return vals[0], vals[0]

    # 3. 명시적 만원 단위
    man_matches = _PAT_MAN.findall(text)
    nums = [int(s.replace(',', '')) for s in man_matches]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]

    # 4. 3~4자리 단독 숫자 (문맥상 만원)
    bare = [int(n) for n in _PAT_NUM.findall(text) if 100 <= int(n) <= 9999]
    if len(bare) >= 2:
        return bare[0], bare[1]
    if len(bare) == 1:
        return bare[0], bare[0]

    return None, None


def parse_salary(raw_text: str) -> dict:
    """
    급여 원본 텍스트 → 파싱 결과 dict

    반환 키:
        salary_type    : 'net' | 'gross' | None
        salary_unit    : 'monthly' | 'annual' | None
        salary_min     : int(만원) | None   ← 원본 단위 그대로
        salary_max     : int(만원) | None
        salary_net_min : int(만원) | None   ← Net 환산 + 퇴직금 포함
        salary_net_max : int(만원) | None
    """
    empty = dict(salary_type=None, salary_unit=None,
                 salary_min=None, salary_max=None,
                 salary_net_min=None, salary_net_max=None)

    if not raw_text or not raw_text.strip():
        return empty

    text = raw_text.strip()

    # 협의 / 미정 → 전부 None
    if _PAT_NEGO.search(text):
        return empty

    # ── Net / Gross ──────────────────────────────────────────
    if _PAT_NET.search(text):
        salary_type = 'net'
    elif _PAT_GROSS.search(text):
        salary_type = 'gross'
    else:
        salary_type = None

    # ── 연봉 / 월급 ──────────────────────────────────────────
    if _PAT_ANN.search(text):
        salary_unit = 'annual'
    elif _PAT_MON.search(text):
        salary_unit = 'monthly'
    else:
        # '월' 단독 등 모호한 경우
        salary_unit = 'monthly' if re.search(r'월', text) else None

    # ── 숫자 추출 ─────────────────────────────────────────────
    s_min, s_max = _extract_numbers(text)

    result = dict(salary_type=salary_type, salary_unit=salary_unit,
                  salary_min=s_min, salary_max=s_max,
                  salary_net_min=None, salary_net_max=None)

    # ── Net 환산 (salary_type 이 명확할 때만) ──────────────────
    if s_min is not None and salary_type is not None:
        # 연봉 → 월급 변환
        if salary_unit == 'annual':
            m_min = s_min / 12
            m_max = (s_max / 12) if s_max else m_min
        else:
            m_min = float(s_min)
            m_max = float(s_max) if s_max else m_min

        # 만원 → 원 단위 변환 후 계산
        net_min_won = calc_net_with_retirement(salary_type, int(m_min * 10_000))
        net_max_won = calc_net_with_retirement(salary_type, int(m_max * 10_000))

        # 원 → 만원 (반올림)
        result['salary_net_min'] = round(net_min_won / 10_000)
        result['salary_net_max'] = round(net_max_won / 10_000)

    return result


# ══════════════════════════════════════════════════════════════
# 단독 실행 시 테스트
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    tests = [
        ("Net (세후) 월급 1,800이상~1,850미만(만원) • 술기 추가 시 인상",
         "Net 월급 범위"),
        ("세전 연봉 3억",
         "Gross 연봉 3억"),
        ("세전 연봉 2억 5천만원",
         "Gross 연봉 2.5억"),
        ("Gross 월급 2,000만원",
         "Gross 월 2000만"),
        ("Net 연봉 2억",
         "Net 연봉 2억"),
        ("협의",
         "협의"),
        ("월 2,000 (세후)",
         "Net 월 2000만 (단독숫자)"),
        ("세전 월급 2500만원~3000만원",
         "Gross 월급 범위"),
    ]

    print(f"{'케이스':<30} {'type':6} {'unit':8} {'min':6} {'max':6} {'net_min':8} {'net_max':8}")
    print('-' * 80)
    for raw, label in tests:
        r = parse_salary(raw)
        print(f"{label:<30} {str(r['salary_type']):6} {str(r['salary_unit']):8} "
              f"{str(r['salary_min']):6} {str(r['salary_max']):6} "
              f"{str(r['salary_net_min']):8} {str(r['salary_net_max']):8}")

    print()
    print("── 세금 계산 검증 (Gross 연봉 3억 = 월 2,500만원) ─────────────")
    net = gross_monthly_to_net_monthly(25_000_000)
    retirement = 25_000_000 // 12
    total = calc_net_with_retirement('gross', 25_000_000)
    print(f"  월 실수령(세후)  : {net:>12,} 원  ({net/10000:.0f}만원)")
    print(f"  퇴직금 월 환산   : {retirement:>12,} 원  ({retirement/10000:.0f}만원)")
    print(f"  합계             : {total:>12,} 원  ({total/10000:.0f}만원)")
