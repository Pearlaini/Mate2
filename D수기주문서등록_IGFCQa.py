# win+R에서 명령어 실행하면 추가 로그인 필요 없음.열린 창은 닫으면 안 됨!!!
# chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome_temp"
# https://qa-oms.ourbox.co.kr/om/login/login.do

# 샘플화주사 b2c쇼핑몰로 첫번째 상품 등록하기

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException
from datetime import datetime
import time


# 기존 크롬에 연결
options = webdriver.ChromeOptions()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

# 샘플화주사 선택
select_element = wait.until(
    EC.presence_of_element_located((By.ID, "pwn_header_change"))
)
dropdown = Select(select_element)
dropdown.select_by_value("PWN00069")    #J나이스(주)


# 수기 주문서 추가
driver.get("https://qa-oms.i-gfc.co.kr/om/order/order/dome/orderRgst.do")

## 1. J채널(b2c) 판매채널 선택 
select_element = driver.find_element(By.ID, "sach_cd")
select = Select(select_element)
select.select_by_value("SACH0004")

## 2. 첫 번째 상품 선택
driver.find_element(By.ID, "searchProdBtn").click()
time.sleep(2) 

driver.switch_to.window(driver.window_handles[-1])
first_select_btn = WebDriverWait(driver, 15).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".tabulator-row .btn-info"))
)
driver.execute_script("arguments[0].click();", first_select_btn)

## 3. 주문수량 입력
qty_input = wait.until(
    EC.element_to_be_clickable((By.ID, "od_qty"))
)
qty_input.clear()
qty_input.send_keys("3")

## 4. 단가 입력
sale_price_input = wait.until(
    EC.element_to_be_clickable((By.ID, "sach_sale_price"))
)
sale_price_input.clear()
sale_price_input.send_keys("1000")

## 5. 주문상세 클릭
driver.find_element(By.XPATH, "//a[contains(text(), '주문 상세')]").click()

## 6. 번호 입력
current_time = datetime.now().strftime("%Y%m%d%H%M")
od_no = "J" + current_time 
od_no_input = wait.until(
    EC.element_to_be_clickable((By.ID, "mall_od_no"))
)
od_no_input.clear()
od_no_input.send_keys(od_no)

## 7. 주문자명
driver.find_element(By.XPATH, "//a[contains(text(), '주문자 정보')]").click()

od_user_nm_input = wait.until(
    EC.element_to_be_clickable((By.ID, "od_user_nm"))
)
od_user_nm_input.clear()
od_user_nm_input.send_keys("김주문")

## 8. 주문자 전화번호
od_user_tel = "010-" + current_time[0:4] + "-" + current_time[5:9]
od_user_tel_input = wait.until(
    EC.element_to_be_clickable((By.ID, "od_user_tel_no_enc"))
)
od_user_tel_input.clear()
od_user_tel_input.send_keys(od_user_tel)

## 9. 수취인명
driver.find_element(By.XPATH, "//a[contains(text(), '수취인 정보')]").click()
recvr_nm_input = wait.until(
    EC.element_to_be_clickable((By.ID, "recvr_nm"))
)
recvr_nm_input.clear()
recvr_nm_input.send_keys("김수취")

## 10. 수취인 전화번호
recvr_tel = "010-" + current_time[-8:-4] + "-" + current_time[-4:]
recvr_tel_input = wait.until(
    EC.element_to_be_clickable((By.ID, "recvr_mobile_no_enc"))
)
recvr_tel_input.clear()
recvr_tel_input.send_keys(recvr_tel)

## 11. 배송지 주소
driver.find_element(By.XPATH, "//a[contains(text(), '배송 정보')]").click()
address_btn = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "span[onclick*='zipModal']"))
)
address_btn.click()

# 11-1. 팝업창 전환
driver.switch_to.window(driver.window_handles[-1])
# 11-2. 카카오 주소 API는 2중 프레임을 사용합니다.
driver.switch_to.frame(0)
inner_iframes = driver.find_elements(By.TAG_NAME, "iframe")
if len(inner_iframes) > 0:
    driver.switch_to.frame(0)


address_input = wait.until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "input#region_name[title='주소 검색']"))
)

address_input.click() # 포커스 강제 이동
address_input.clear()
address_input.send_keys("지플러스타워")

search_button = wait.until(
    EC.element_to_be_clickable((By.CLASS_NAME, "btn_search"))
)
search_button.click()

#11-3.첫번째 주소 선택 실패로 나머지는 수동으로 작업하기


