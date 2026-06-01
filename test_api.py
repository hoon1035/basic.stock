"""
test_api.py — API 연결 테스트
=====================================================
형이 가진 키를 아래 칸에 넣으세요.
가진 것만 넣으면 됩니다. 없는 건 비워두세요.
=====================================================
"""
import requests
import json

# ╔═══════════════════════════════════════════════════╗
# ║   여기에 형 키를 넣으세요 (가진 것만)              ║
# ╚═══════════════════════════════════════════════════╝

# ───── (1) 한국증권 (한국투자증권 KIS) ─────
#   apiportal.koreainvestment.com 에서 발급
KIS_APP_KEY    = "PSNjkjOsBfFX8lg7aEKqkWDGNVS9ghAmhwcV"      # <-- 여기에 앱키 붙여넣기
KIS_APP_SECRET = "0Z+zdhH0E0KPaaQtyEkchkTgj9L4DxtP3W4UfA9WujEMn2gIpgmeE8/AaUz3yokxNHWXlAVSyKTYPhYGmakyl9XhRIzjlsZMTZIPZ4UauBzfiBDQABHTiIfsl3j2P57yZOQkkw0KQHIzR8NuBRsk8RQ0R5xX2SvVoyv0cgnHzQ6Dck4tAd8="      # <-- 여기에 시크릿 붙여넣기

# ───── (2) 한국거래소 (KRX) ─────
#   data.krx.co.kr — 보통 키 없이도 됨
KRX_API_KEY    = "615bb47a94e9c380440aba06b7c40c36f51654cb"      # <-- 있으면 넣기 (없어도 됨)

# ───── (3) 네이버 ─────
#   네이버 개발자센터 API 키
NAVER_CLIENT_ID     = "CoeqbFMyF8a9EbRzOX57 "   # <-- 네이버 클라이언트 ID
NAVER_CLIENT_SECRET = "CiAgt0Pwh7"   # <-- 네이버 시크릿


# ===================================================
#   아래는 건드리지 마세요 (테스트 코드)
# ===================================================

def test_kis():
    print("\n[ (1) 한국증권 (KIS) 테스트 ]")
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
        print(f"   [OK] 토큰 발급 성공: {token[:15]}...")
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET,
            "tr_id": "FHKST01010900",
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
        r = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
                         headers=headers, params=params)
        r.raise_for_status()
        print("   [OK] 삼성전자 투자자 데이터 받음!")
        print("   --- 응답 일부 ---")
        print("   " + json.dumps(r.json(), ensure_ascii=False)[:300])
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


def test_krx():
    print("\n[ (2) 한국거래소 (KRX) 테스트 ]")
    try:
        url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://data.krx.co.kr/"}
        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "mktId": "STK",
            "trdDd": "20250530",   # 조회일 (영업일로 바꾸세요)
        }
        r = requests.post(url, data=data, headers=headers, timeout=10)
        r.raise_for_status()
        rows = r.json().get("OutBlock_1", [])
        if rows:
            print(f"   [OK] KRX 전종목 {len(rows)}개 받음! (키 불필요)")
            print(f"   --- 첫 종목: {rows[0].get('ISU_ABBRV','?')} ---")
        else:
            print("   [?] 응답은 왔는데 데이터 없음 (날짜를 영업일로 바꿔보세요)")
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


def test_naver():
    print("\n[ (3) 네이버 테스트 ]")
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
        print(f"   [OK] 네이버 API 연결 성공! (뉴스 {r.json().get('total','?')}건)")
    except Exception as e:
        print(f"   [FAIL] 실패: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("  API 연결 테스트 - 가진 키만 자동으로 테스트")
    print("=" * 50)
    test_kis()
    test_krx()
    test_naver()
    print("\n" + "=" * 50)
    print("  [OK] 표시된 게 쓸 수 있는 API입니다.")
    print("  이 결과를 의표형한테 복사해서 보여주세요!")
    print("=" * 50)
