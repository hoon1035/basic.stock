# basicstock-data 🗺️

한국 주식 자금흐름 대시보드(basicstock.kr)용 데이터 자동 수집 저장소.

## 구조

```
basicstock-data/
├── collect.py            # 매일 수급 수집 → data.json 생성
├── test_api.py           # API 연결 테스트 (먼저 이걸로 확인!)
├── stocks.json           # 350종목 리스트 (자동 갱신 or 수동)
├── themes.json           # 테마 묶음 (수동 관리) ⭐
├── data.json             # 수집 결과 (자동 생성)
├── requirements.txt      # 파이썬 패키지
└── .github/workflows/
    └── daily.yml         # 매일 자동 실행
```

## 작동 순서

```
[GitHub Actions — 매일 장마감 후]
① collect.py 실행 → API로 350종목 수급 수집
② 시나리오 판정 + 게이트 계산 + RRG 좌표
③ data.json 으로 저장 → 깃허브에 자동 커밋
④ basicstock.kr 이 data.json 읽어서 대시보드 표시
```

## 테마 관리 (themes.json)

새 테마 뜨면 themes.json 에 종목코드 묶어서 추가, 죽으면 삭제.
코드는 안 건드리고 이 파일만 수정하면 메인 화면 테마가 바뀜.

## 시작하기

1. 먼저 `test_api.py` 로 API 연결 확인 (KIS 키 넣고)
2. 되면 `collect.py` 로 전체 수집
3. GitHub Secrets 에 KIS 앱키 등록 (코드에 직접 넣지 말 것!)
4. daily.yml 로 매일 자동 실행
