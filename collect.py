"""
collect.py — basicstock 실데이터 수집 (KISClient 검증판 사용)
- 코스피200+코스닥150 자동 (pykrx)
- KISClient: 토큰캐싱 + 429재시도 → 350개 안정적
- 시나리오/게이트/RRG 계산 → data.json
"""
import json, time
from datetime import datetime, timedelta
from kis_client import KISClient

# ── 종목 유니버스 (KIS 시가총액 상위) ──
def build_universe(kis):
    """KIS API로 코스피+코스닥 시총 상위 종목 수집"""
    codes = []
    try:
        kospi = kis.get_top_marketcap("0001", count=200)   # 코스피 상위 200
        print(f"   코스피 시총상위: {len(kospi)}개")
        kosdaq = kis.get_top_marketcap("1001", count=150)  # 코스닥 상위 150
        print(f"   코스닥 시총상위: {len(kosdaq)}개")
        codes = list(dict.fromkeys(kospi + kosdaq))
    except Exception as e:
        print(f"   [경고] 시총상위 수집 실패: {e}")
    return codes, {}

def load_themes():
    with open("themes.json", encoding="utf-8") as f:
        themes = json.load(f)["themes"]
    universe = {}
    meta = {}
    for key, t in themes.items():
        meta[key] = t
        for code in t["codes"]:
            universe.setdefault(code, []).append(key)
    return universe, meta

def load_names():
    try:
        with open("names.json", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

# ── 지표 계산 ──
def calc_metrics(days, day_chg):
    if not days: return None
    sumF = sum(d["foreign"] for d in days)
    sumI = sum(d["inst"] for d in days)
    sumR = sum(d["retail"] for d in days)
    netflow = sumF + sumI
    cmf = round(max(-0.9, min(0.9, netflow / (abs(sumR) + abs(netflow) + 1))), 2)
    closes = [d["close"] for d in days if d["close"] > 0]
    vwap20 = sum(closes) / len(closes) if closes else 0
    cur = days[0]["close"] if days else 0
    vwap_gap = round((cur - vwap20) / vwap20 * 100, 1) if vwap20 else 0
    half = len(days) // 2 or 1
    recent = sum((d["foreign"]+d["inst"]) for d in days[:half])
    older = sum((d["foreign"]+d["inst"]) for d in days[half:])
    ad_trend = "up" if recent > older and netflow > 0 else "down" if netflow < 0 else "flat"
    vol_diverge = (day_chg > 0) != (netflow > 0)
    if netflow < 0 and day_chg > 0: sc = "distribute"
    elif netflow < 0 and day_chg < 0: sc = "exit"
    elif netflow > 0 and day_chg < 0: sc = "stealth"
    elif netflow > 0 and day_chg >= 0: sc = "accumulate"
    else: sc = "neutral"
    return {"sumF": sumF, "sumI": sumI, "sumR": sumR, "cmf": cmf,
        "vwapGap": vwap_gap, "adTrend": ad_trend, "volDiverge": vol_diverge,
        "scenario": sc, "days": days[:7]}

# ── 메인 ──
def main():
    kis = KISClient()
    if not kis.app_key or not kis.app_secret:
        print("[FAIL] KIS 키 없음")
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump({"error": "KIS 키 없음", "stocks": {}, "themes": {}}, f, ensure_ascii=False, indent=2)
        return

    print("1) 종목 유니버스 구성...")
    uni_codes, uni_names = build_universe(kis)
    theme_universe, theme_meta = load_themes()
    file_names = load_names()
    names = {**uni_names, **file_names}
    all_codes = list(dict.fromkeys(uni_codes + list(theme_universe.keys())))
    if not all_codes:
        all_codes = list(theme_universe.keys())
    print(f"   [OK] 총 {len(all_codes)}개 종목, 테마 {len(theme_meta)}개")

    print("2) 수급 수집 (KISClient 토큰캐싱+재시도)...")
    stocks = {}
    for i, code in enumerate(all_codes, 1):
        try:
            price = kis.get_price(code)
            days = kis.get_investor_trend(code, days=20)
            metrics = calc_metrics(days, price.get("chg", 0))
            if metrics:
                stocks[code] = {
                    "code": code, "name": names.get(code) or price.get("name", code),
                    "price": price.get("price", 0), "chg": price.get("chg", 0),
                    "vol": price.get("vol", 0), "foreignRatio": price.get("foreign_ratio", 0),
                    "themes": theme_universe.get(code, []), **metrics,
                }
        except Exception as e:
            print(f"   [{i}] {code} 실패: {e}")
        if i % 25 == 0 or i == len(all_codes):
            print(f"   진행 [{i}/{len(all_codes)}]...")

    # 테마 집계
    theme_agg = {}
    for key, meta in theme_meta.items():
        codes = [c for c in meta["codes"] if c in stocks]
        if not codes: continue
        flow = sum(stocks[c]["sumF"] + stocks[c]["sumI"] for c in codes)
        chg_avg = sum(stocks[c]["chg"] for c in codes) / len(codes)
        theme_agg[key] = {"label": meta["label"], "emoji": meta["emoji"],
            "flow": flow, "chg": round(chg_avg, 2), "count": len(codes)}

    out = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stocks": stocks, "themes": theme_agg}
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] data.json 생성! 종목 {len(stocks)}개, 테마 {len(theme_agg)}개")

if __name__ == "__main__":
    main()
