from datetime import datetime

import requests

# 네이버 증권 API — 검색·시세정보와 유사한 고시 환율
# 매매기준·갱신 시각: exchange 단건, 현찰 살 때 등: 일별 prices 첫 행(가장 최근 영업일)
NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
NAVER_USDKRW_DETAIL = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW"
NAVER_USDKRW_PRICES = (
    "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW"
    "/prices?page=1&pageSize=1"
)


def _comma_price_to_float(value: str) -> float:
    """API에서 오는 '1,494.50' 형태 문자열을 float으로 변환한다."""
    return float(value.replace(",", ""))


detail_res = requests.get(
    NAVER_USDKRW_DETAIL, headers=NAVER_HEADERS, timeout=15
)
detail_res.raise_for_status()
detail = detail_res.json().get("exchangeInfo")
if not detail:
    raise RuntimeError(f"네이버 시세 본문 없음: {detail_res.text[:200]}")

prices_res = requests.get(NAVER_USDKRW_PRICES, headers=NAVER_HEADERS, timeout=15)
prices_res.raise_for_status()
price_rows = prices_res.json()
if not price_rows:
    raise RuntimeError("일별 시세(prices)가 비어 있습니다.")

krw_rate = _comma_price_to_float(detail["closePrice"])
traded_at = datetime.fromisoformat(detail["localTradedAt"])
now = f"{traded_at.strftime('%Y-%m-%d')} {traded_at.strftime('%H:%M')}"

latest_daily = price_rows[0]
cash_buy = _comma_price_to_float(latest_daily["cashBuyValue"])

# 환율우대 50%: 고시 현찰 살 때(불리한 쪽)와 매매기준 사이 스프레드의 절반만 반영한 추정 환율(참고용, 은행별 산식 상이)
스프레드_현찰살때 = cash_buy - krw_rate
cash_buy_우대50 = round(krw_rate + 스프레드_현찰살때 * 0.5, 2)

print(f"{now} 기준 원달러 매매기준율은 {krw_rate}원입니다.")
print(
    f"현찰 살 때 환율은 {cash_buy}원, 환율우대 50%(추정) {cash_buy_우대50}원입니다."
)
