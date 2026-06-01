"""
collect.py — basicstock 실데이터 수집 (완성판)
=====================================================
1. KRX에서 코스피200+코스닥150 종목 리스트 자동 수집
2. KIS API로 각 종목 외인/기관 수급 (최근 20일)
3. 시나리오 판정 + 3종 게이트 계산 + RRG 좌표
4. data.json 생성 (basicstock.kr 이 읽음)

GitHub Secrets 필요: KIS_APP_KEY, KIS_APP_SECRET
실행: python collect.py
=====================================================
"""
import requests
import json
import os
import time
from datetime import datetime, timedelta

KIS_APP_KEY    = os.environ.get("KIS_APP_KEY", "")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "")
BASE = "https://openapi.koreainvestment.com:9443"

# ───────────────────────────────────────────
# 1. 인증
# ───────────────────────────────────────────
def get_token():
    res = requests.post(f"{BASE}/oauth2/tokenP", data=json.dumps({
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
    }))
    res.raise_for_status()
    return res.json()["access_token"]

# ───────────────────────────────────────────
# 2. 종목 리스트 — themes.json 에서 읽기
#    (themes.json 의 모든 종목코드를 유니버스로)
# ───────────────────────────────────────────
def load_universe():
    with open("themes.json", encoding="utf-8") as f:
        themes = json.load(f)["themes"]
    universe = {}          # code -> [theme_keys]
    theme_meta = {}        # theme_key -> {label, emoji, codes}
    for key, t in themes.items():
        theme_meta[key] = {"label": t["label"], "emoji": t["emoji"], "codes": t["codes"]}
        for code in t["codes"]:
            universe.setdefault(code, []).append(key)
    return universe, theme_meta

# ───────────────────────────────────────────
# 3. KIS 종목별 투자자 수급 (최근 N일)
# ───────────────────────────────────────────
def get_supply(token, code):
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010900",
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    r = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
                     headers=headers, params=params, timeout=10)
    r.raise_for_status()
    rows = r.json().get("output", [])

    days = []
    for row in rows:
        frgn = row.get("frgn_ntby_qty", "").strip()
        orgn = row.get("orgn_ntby_qty", "").strip()
        prsn = row.get("prsn_ntby_qty", "").strip()
        if not frgn:        # 빈 날(장중 당일) 건너뜀
            continue
        days.append({
            "date": row.get("stck_bsop_date", ""),
            "close": int(row.get("stck_clpr", "0") or 0),
            "foreign": int(frgn or 0),
            "inst": int(orgn or 0),
            "retail": int(prsn or 0),
            "chg": float(row.get("prdy_ctrt", "0") or 0),  # 전일대비율
        })
        if len(days) >= 20:
            break
    return days

# ───────────────────────────────────────────
# 4. 현재가 + 등락률 (수급에 chg 없을 때 보강용)
# ───────────────────────────────────────────
def get_price(token, code):
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010100",
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    r = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
                     headers=headers, params=params, timeout=10)
    r.raise_for_status()
    o = r.json().get("output", {})
    return {
        "name": o.get("hts_kor_isnm", code),
        "price": int(o.get("stck_prpr", "0") or 0),
        "chg": float(o.get("prdy_ctrt", "0") or 0),
        "vol": int(o.get("acml_vol", "0") or 0),
    }

# ───────────────────────────────────────────
# 5. 지표 계산 (시나리오 + 게이트 + CMF 근사)
# ───────────────────────────────────────────
def calc_metrics(days):
    if not days:
        return None
    sumF = sum(d["foreign"] for d in days)
    sumI = sum(d["inst"] for d in days)
    sumR = sum(d["retail"] for d in days)

    # CMF 근사: 수급 방향의 누적 강도 (외인+기관 / 거래량 가정)
    netflow = sumF + sumI
    cmf = max(-0.9, min(0.9, netflow / (abs(sumR) + abs(netflow) + 1) ))
    cmf = round(cmf, 2)

    # 20일 VWAP 근사 (종가 평균 — 실제론 거래량 가중)
    closes = [d["close"] for d in days if d["close"] > 0]
    vwap20 = sum(closes) / len(closes) if closes else 0
    cur = days[0]["close"] if days else 0
    vwap_gap = round((cur - vwap20) / vwap20 * 100, 1) if vwap20 else 0

    # A/D선 추세: 누적 순매수 방향 (전반부 vs 후반부)
    half = len(days) // 2 or 1
    recent = sum((d["foreign"]+d["inst"]) for d in days[:half])
    older  = sum((d["foreign"]+d["inst"]) for d in days[half:])
    ad_trend = "up" if recent > older and netflow > 0 else "down" if netflow < 0 else "flat"

    # 거래량-가격 다이버전스: 가격 방향 vs 수급 방향 불일치
    price_up = days[0]["chg"] > 0
    flow_up = netflow > 0
    vol_diverge = price_up != flow_up

    chg = days[0]["chg"]
    # 시나리오 판정 (시안 로직과 동일)
    if netflow < 0 and chg > 0:
        sc = "distribute"
    elif netflow < 0 and chg < 0:
        sc = "exit"
    elif netflow > 0 and chg < 0:
        sc = "stealth"
    elif netflow > 0 and chg >= 0:
        sc = "accumulate"
    else:
        sc = "neutral"

    return {
        "sumF": sumF, "sumI": sumI, "sumR": sumR,
        "cmf": cmf, "vwapGap": vwap_gap, "adTrend": ad_trend,
        "volDiverge": vol_diverge, "scenario": sc,
        "days": days[:7],   # 최근 7일만 저장 (용량)
    }

# ───────────────────────────────────────────
# 6. 메인
# ───────────────────────────────────────────
def main():
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        print("[FAIL] KIS 키 없음 — Secrets 확인")
        return

    print("1) 토큰 발급...")
    token = get_token()
    print("   [OK]")

    print("2) 종목 유니버스 로드 (themes.json)...")
    universe, theme_meta = load_universe()
    print(f"   [OK] {len(universe)}개 종목, {len(theme_meta)}개 테마")

    print("3) 종목별 수급 수집 (KIS)...")
    stocks = {}
    for i, code in enumerate(universe.keys(), 1):
        try:
            price = get_price(token, code)
            time.sleep(0.05)
            days = get_supply(token, code)
            time.sleep(0.05)
            metrics = calc_metrics(days)
            if metrics:
                stocks[code] = {
                    "code": code,
                    "name": price["name"],
                    "price": price["price"],
                    "chg": price["chg"],
                    "vol": price["vol"],
                    "themes": universe[code],
                    **metrics,
                }
            print(f"   [{i}/{len(universe)}] {code} {price['name']} OK")
        except Exception as e:
            print(f"   [{i}/{len(universe)}] {code} 실패: {e}")
        time.sleep(0.1)   # API 호출 제한 (초당 제한 회피)

    # 테마별 집계 (RRG 좌표용)
    theme_agg = {}
    for key, meta in theme_meta.items():
        codes = [c for c in meta["codes"] if c in stocks]
        if not codes:
            continue
        flow = sum(stocks[c]["sumF"] + stocks[c]["sumI"] for c in codes)
        chg_avg = sum(stocks[c]["chg"] for c in codes) / len(codes)
        theme_agg[key] = {
            "label": meta["label"], "emoji": meta["emoji"],
            "flow": flow, "chg": round(chg_avg, 2), "count": len(codes),
        }

    out = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stocks": stocks,
        "themes": theme_agg,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] data.json 생성 완료! 종목 {len(stocks)}개, 테마 {len(theme_agg)}개")

if __name__ == "__main__":
    main()
