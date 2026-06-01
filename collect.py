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
def load_names():
    try:
        with open("names.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

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
# 2-B. KRX 지수구성종목 자동 수집 (코스피200 + 코스닥150)
# ───────────────────────────────────────────
def fetch_index_components(idx_code, mkt):
    """KRX 지수 구성종목 코드 리스트
    idx_code: 코스피200=1028, 코스닥150=2203
    mkt: STK(코스피) / KSQ(코스닥)
    """
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    }
    # 최근 영업일 (오늘부터 거꾸로 시도)
    for back in range(0, 7):
        d = (datetime.now() - timedelta(days=back)).strftime("%Y%m%d")
        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT00601",
            "locale": "ko_KR",
            "tboxindIdx_finder_equidx0_2": "",
            "indIdx": "1" if mkt=="STK" else "2",
            "indIdx2": idx_code,
            "codeNmindIdx_finder_equidx0_2": "",
            "param1indIdx_finder_equidx0_2": "",
            "trdDd": d,
            "money": "1", "csvxls_isNo": "false",
        }
        try:
            r = requests.post(url, data=data, headers=headers, timeout=10)
            r.raise_for_status()
            rows = r.json().get("output", [])
            if rows:
                codes = [row.get("ISU_SRT_CD","").strip() for row in rows if row.get("ISU_SRT_CD")]
                names = {row.get("ISU_SRT_CD","").strip(): row.get("ISU_ABBRV","").strip() for row in rows}
                return codes, names
        except Exception as e:
            continue
    return [], {}

def build_universe_350():
    """코스피200 + 코스닥150 = 약 350개 자동 수집"""
    print("   코스피200 수집 중...")
    k200, n1 = fetch_index_components("1028", "STK")
    print(f"   코스피200: {len(k200)}개")
    print("   코스닥150 수집 중...")
    kq150, n2 = fetch_index_components("2203", "KSQ")
    print(f"   코스닥150: {len(kq150)}개")
    allcodes = list(dict.fromkeys(k200 + kq150))  # 중복 제거
    allnames = {**n1, **n2}
    return allcodes, allnames

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
def calc_metrics(days, day_chg=0):
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
    price_up = day_chg > 0
    flow_up = netflow > 0
    vol_diverge = price_up != flow_up

    chg = day_chg  # 현재가 등락률 사용 (days의 chg는 0으로 오는 경우 많음)
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
        print(f"   KIS_APP_KEY 길이: {len(KIS_APP_KEY)}")
        print(f"   KIS_APP_SECRET 길이: {len(KIS_APP_SECRET)}")
        print("   → Settings > Secrets and variables > Actions 에 등록했는지 확인")
        # 빈 파일이라도 만들어서 커밋 에러 방지
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump({"error": "KIS 키 없음", "stocks": {}, "themes": {}}, f, ensure_ascii=False, indent=2)
        return

    print("1) 토큰 발급...")
    token = get_token()
    print("   [OK]")

    print("2) 종목 유니버스 구성...")
    # 350개 자동 수집 (코스피200 + 코스닥150)
    uni_codes, uni_names = build_universe_350()
    # 테마(themes.json) — 메인에 보여줄 묶음
    theme_universe, theme_meta = load_universe()
    file_names = load_names()
    # 이름 우선순위: names.json > KRX > 코드
    names = {**uni_names, **file_names}
    # 테마 종목도 유니버스에 포함 (혹시 350개에 없으면)
    all_codes = list(dict.fromkeys(uni_codes + list(theme_universe.keys())))
    if not all_codes:
        print("   [경고] KRX 수집 실패 — themes.json 종목만 사용")
        all_codes = list(theme_universe.keys())
    print(f"   [OK] 총 {len(all_codes)}개 종목, 테마 {len(theme_meta)}개")

    print("3) 종목별 수급 수집 (KIS) — 시간 좀 걸려요...")
    stocks = {}
    for i, code in enumerate(all_codes, 1):
        try:
            price = get_price(token, code)
            time.sleep(0.05)
            days = get_supply(token, code)
            time.sleep(0.05)
            metrics = calc_metrics(days, price["chg"])
            if metrics:
                stocks[code] = {
                    "code": code,
                    "name": names.get(code) or price["name"],
                    "price": price["price"],
                    "chg": price["chg"],
                    "vol": price["vol"],
                    "themes": theme_universe.get(code, []),
                    **metrics,
                }
            if i % 25 == 0 or i == len(all_codes):
                print(f"   진행 [{i}/{len(all_codes)}]...")
        except Exception as e:
            print(f"   [{i}/{len(all_codes)}] {code} 실패: {e}")
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
