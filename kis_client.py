"""
KISClient — 한국투자증권 OpenAPI 래퍼 (SIGVIEW 검증판 기반)
- 토큰 자동 발급/캐싱 (23시간)
- 429 재시도 (지수 백오프)
- 외인/기관 일별 매매 시계열
"""
import os, time, json, requests
from datetime import datetime, timedelta
from threading import Lock

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = '.kis_token_cache.json'

class KISClient:
    def __init__(self):
        self.app_key = os.environ.get('KIS_APP_KEY', '')
        self.app_secret = os.environ.get('KIS_APP_SECRET', '')
        self.token = None
        self.token_expires = None
        self.lock = Lock()
        self.last_call_time = 0
        self.min_interval = 0.06
        self._load_token_cache()

    def _load_token_cache(self):
        try:
            if os.path.exists(TOKEN_CACHE_FILE):
                with open(TOKEN_CACHE_FILE) as f:
                    cache = json.load(f)
                exp = datetime.fromisoformat(cache['expires'])
                if datetime.now() < exp - timedelta(minutes=30):
                    self.token = cache['token']
                    self.token_expires = exp
        except: pass

    def _save_token_cache(self):
        try:
            with open(TOKEN_CACHE_FILE, 'w') as f:
                json.dump({'token': self.token, 'expires': self.token_expires.isoformat()}, f)
        except: pass

    def _get_token(self):
        if not self.app_key or not self.app_secret:
            raise Exception("KIS 키 없음")
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token
        # 403(1분 1회 제한) 대비 재시도
        for attempt in range(5):
            r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                headers={"content-type": "application/json"},
                data=json.dumps({"grant_type": "client_credentials",
                    "appkey": self.app_key, "appsecret": self.app_secret}), timeout=10)
            if r.status_code == 200:
                self.token = r.json()['access_token']
                self.token_expires = datetime.now() + timedelta(hours=23)
                self._save_token_cache()
                return self.token
            elif r.status_code in (403, 429):
                print(f"   토큰 발급 제한 — {60}초 대기 (시도 {attempt+1}/5)")
                time.sleep(62)  # 1분 1회 제한 → 62초 대기
            else:
                r.raise_for_status()
        raise Exception("토큰 발급 실패 (403 지속)")

    def _rate_limit(self):
        with self.lock:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call_time = time.time()

    def _call(self, path, tr_id, params, max_retries=3):
        self._rate_limit()
        token = self._get_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret,
            "tr_id": tr_id, "custtype": "P",
        }
        for attempt in range(max_retries):
            try:
                r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=10)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 401:
                    self.token = None
                    headers['authorization'] = f"Bearer {self._get_token()}"
                    continue
                elif r.status_code == 429:
                    time.sleep(2 ** attempt); continue
            except Exception:
                if attempt == max_retries - 1: raise
                time.sleep(1)
        return None

    def get_investor_trend(self, stock_code, days=20):
        """외인/기관 일별 매매 시계열"""
        result = self._call("/uapi/domestic-stock/v1/quotations/inquire-investor",
            "FHKST01010900", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code})
        if not result or result.get('rt_cd') != '0':
            return []
        parsed = []
        for row in result.get('output', []):
            frgn = row.get('frgn_ntby_qty', '').strip()
            if not frgn:  # 빈 날(장중) 스킵
                continue
            try:
                parsed.append({
                    'date': row.get('stck_bsop_date', ''),
                    'close': int(row.get('stck_clpr', 0) or 0),
                    'foreign': int(frgn or 0),
                    'inst': int(row.get('orgn_ntby_qty', 0) or 0),
                    'retail': int(row.get('prsn_ntby_qty', 0) or 0),
                })
            except: continue
            if len(parsed) >= days: break
        return parsed

    def get_top_marketcap(self, market="0000", count=200):
        """시가총액 상위 종목 코드 리스트
        market: 0000=전체, 0001=코스피, 1001=코스닥
        """
        codes = []
        result = self._call("/uapi/domestic-stock/v1/ranking/market-cap",
            "FHPST01740000", {
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20174",
                "fid_div_cls_code": "0",
                "fid_input_iscd": market,
                "fid_trgt_cls_code": "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
            })
        if result and result.get('rt_cd') == '0':
            for row in result.get('output', [])[:count]:
                code = row.get('mksc_shrn_iscd', '').strip()
                if code:
                    codes.append(code)
        return codes

    def get_price(self, stock_code):
        """현재가 + 등락률 + 외인소진율"""
        result = self._call("/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code})
        if not result or result.get('rt_cd') != '0':
            return {}
        o = result.get('output', {})
        try:
            return {
                'name': o.get('hts_kor_isnm', stock_code),
                'price': int(o.get('stck_prpr', 0) or 0),
                'chg': float(o.get('prdy_ctrt', 0) or 0),
                'vol': int(o.get('acml_vol', 0) or 0),
                'foreign_ratio': float(o.get('hts_frgn_ehrt', 0) or 0),
            }
        except:
            return {}
