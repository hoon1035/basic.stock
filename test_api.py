"""
test_api.py — API 연결 테스트 (v2 — 수급 값 채워진 날 표시)
=====================================================
형이 가진 키를 아래 칸에 넣으세요. 가진 것만 넣으면 됩니다.
Secrets로 넣으면 빈칸 그대로 둬도 됩니다.
=====================================================
"""
import requests
import json
import os

# ───── (1) 한국증권 (한국투자증권 KIS) ─────
KIS_APP_KEY    = os.environ.get("KIS_APP_KEY", "")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "")

# ───── (3) 네이버 ─────
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")


def test_kis():
    print("\n[ (1) 한국증권 (KIS) - 삼성전자 외인/기관 수급 ]")
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        print("   - 키 안 넣음, 건너뜀")
        return
    try:
        BASE = "https://openapi.koreainvestment.com:9443"
        res = requests.post(f"{BASE}/oauth2/tokenP", data=json.dumps({
            "grant_type": "client_credentials",
            "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
        }))
        res.raise_for_status()
        token = res.json()["access_token"]
        print(f"   [OK] 토큰 발급 성공")

        headers = {
            "authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
            "tr_id": "FHKST01010900",
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
        r = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
                         headers=headers, params=params)
        r.raise_for_status()
        rows = r.json().get("output", [])
        print(f"   [OK] 응답 {len(rows)}일치 받음")

        # 수급 값이 채워진 날(장마감 확정)만 골라서 보여주기
        print("\n   === 최근 수급 (채워진 날 = 장마감 확정) ===")
        shown = 0
        for row in rows:
            frgn = row.get("frgn_ntby_qty", "").strip()
            orgn = row.get("orgn_ntby_qty", "").strip()
            prsn = row.get("prsn_ntby_qty", "").strip()
            date = row.get("stck_bsop_date", "?")
            clpr = row.get("stck_clpr", "?")
            if frgn:  # 값이 있으면
                print(f"   {date} | 종가 {clpr} | 외인 {frgn} | 기관 {orgn} | 개인 {prsn}")
                shown += 1
            if shown >= 5:
                break
        if shown == 0:
            print("   [?] 수급 값이 다 비어있음 — 장중이거나 권한 문제")
        else:
            print(f"\n   [OK] 수급 데이터 정상! 외인/기관 순매수 숫자 확인됨")
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


def test_krx():
    print("\n[ (2) 한국거래소 (KRX) - 전종목 시세 ]")
    try:
        url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
        }
        # 영업일 자동 계산 대신 고정 영업일 사용 (테스트)
        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "locale": "ko_KR",
            "mktId": "STK",
            "trdDd": "20260530",
            "share": "1", "money": "1", "csvxls_isNo": "false",
        }
        r = requests.post(url, data=data, headers=headers, timeout=10)
        r.raise_for_status()
        rows = r.json().get("OutBlock_1", [])
        if rows:
            print(f"   [OK] KRX 전종목 {len(rows)}개! (키 불필요)")
            print(f"   --- 예: {rows[0].get('ISU_ABBRV','?')} 종가 {rows[0].get('TDD_CLSPRC','?')}")
        else:
            print("   [?] 데이터 없음 (날짜를 최근 영업일로)")
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


def test_naver():
    print("\n[ (3) 네이버 ]")
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("   - 키 안 넣음, 건너뜀")
        return
    try:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }
        r = requests.get(url, headers=headers, params={"query": "삼성전자"})
        r.raise_for_status()
        print(f"   [OK] 네이버 연결 성공 (뉴스 {r.json().get('total','?')}건)")
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


if __name__ == "__main__":
    print("=" * 52)
    print("  API 연결 테스트 v2 - 수급 값 확인")
    print("=" * 52)
    test_kis()
    test_krx()
    test_naver()
    print("\n" + "=" * 52)
    print("  결과를 의표형한테 복사해서 보여주세요!")
    print("=" * 52)
