# Mate2QA — 사이트 주소(URL) 바꾸는 방법

다른 QA 서버로 바꿀 때 **로그인 URL 한 줄**만 수정하면, 주문목록·주문서처리 URL이 **같은 서버 경로**로 자동 연결됩니다.

## 수정하는 파일

| 우선순위 | 파일 | 무엇을 바꾸나요 |
|----------|------|----------------|
| 1 (권장) | **`Mate2QA_site_config.py`** | `_DEFAULT_LOGIN_URL` (로그인 페이지 전체 URL) |
| 2 | 같은 파일 | `ORDER_LIST_PATH` 등 (필요 시 경로만) |
| 3 | **`Mate2QA_login.env`** | `LOGIN_URL=https://...` (있으면 ①보다 **우선**) |

## 예시

```python
# Mate2QA_site_config.py
_DEFAULT_LOGIN_URL = "https://qa-oms.ourbox.co.kr/om/login/login.do"

ORDER_LIST_PATH = "/om/order/order/orderList.do"
PUT_ORDER_LIST_PATH = "/om/order/putOrder/putOrderList.do"
```

자동으로 만들어지는 주소:

- 로그인: `https://qa-oms.ourbox.co.kr/om/login/login.do`
- 주문목록: `https://qa-oms.ourbox.co.kr` + `/om/order/order/orderList.do`
- 주문서처리: `https://qa-oms.ourbox.co.kr` + `/om/order/putOrder/putOrderList.do`

## 실행할 때 확인

```powershell
cd D:\py3
python Mate2QA_site_config.py
```

## 검색·로그인 계정 (별도)

- **`search_filter_domestic.json`** — 검색 6개·선택 주문일련번호
- **`Mate2QA_login.env`** — `ID`, `PW`
