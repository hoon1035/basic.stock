"""
test_api.py — KIS OpenAPI 연결 테스트
먼저 이걸로 "진짜 데이터 받아지는지" 확인하고, 되면 collect.py 로 확장.

[사용법]
1. 아래 APP_KEY, APP_SECRET 에 형 KIS 키 넣기 (테스트용. 실제론 환경변수로!)
2. 터미널에서: python test_api.py
3. 삼성전자 외인/기관 순매수가 출력되면 성공!
"""
import requests
import json
import os

# ===== KIS 앱키 (테스트용 — 실전에선 GitHub Secrets 사용) =====
APP_KEY    = os.environ.get("KIS_APP_KEY", "여기에_앱키_붙여넣기")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "여기에_시크릿_붙여넣기")
BASE = "https://openapi.koreainvestment.com:9443"   # 실전투자 도메인

def get_token():
    """접근 토큰 발급"""
    url = f"{BASE}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
    }
    res = requests.post(url, data=json.dumps(body))
    res.raise_for_status()
    return res.json()["access_token"]

def get_investor(token, code):
    """종목별 외국인/기관 순매수 동향
    TR: FHKST01010900 (주식현재가 투자자)
    """
    url = f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010900",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",   # 주식
        "FID_INPUT_ISCD": code,           # 종목코드
    }
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    return res.json()

if __name__ == "__main__":
    print("1) 토큰 발급 중...")
    try:
        token = get_token()
        print(f"   ✅ 토큰 발급 성공: {token[:20]}...")
    except Exception as e:
        print(f"   ❌ 토큰 실패: {e}")
        print("   → APP_KEY/APP_SECRET 확인하세요")
        exit(1)

    print("\n2) 삼성전자(005930) 투자자 동향 조회 중...")
    try:
        data = get_investor(token, "005930")
        print("   ✅ 응답 받음!")
        print("\n=== 원본 응답 (구조 확인용) ===")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
        print("\n→ 이 구조 보고 collect.py 에서 외인/기관 필드 뽑아냅니다.")
    except Exception as e:
        print(f"   ❌ 조회 실패: {e}")
        print("   → TR_ID 나 파라미터가 형 계정 권한과 다를 수 있어요. 응답 메시지 확인.")
