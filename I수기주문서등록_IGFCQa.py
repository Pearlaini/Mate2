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
driver.get("https://qa-oms.i-gfc.co.kr/om/order/order/intl/orderRgst.do")

current_time = datetime.now().strftime("%Y%m%d%H%M")
current_day = current_time[-8:-4]

## 1. J채널(b2c) 판매채널 선택 
select_element = driver.find_element(By.ID, "sach_cd")
select = Select(select_element)
select.select_by_value("SACH0006")

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
qty_input.send_keys(3)

## 4. 단가 입력
sale_price_input = wait.until(
    EC.element_to_be_clickable((By.ID, "sach_sale_price"))
)
sale_price_input.clear()
sale_price_input.send_keys("1000")

## 5. 주문상세 클릭
driver.find_element(By.XPATH, "//a[contains(text(), '주문 상세')]").click()

## 6. 주문번호 입력
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
od_user_tel = "+8110-" + current_day + "-" + current_time[5:9]
od_user_tel_input = wait.until(
    EC.element_to_be_clickable((By.ID, "od_user_tel_no_enc"))
)
od_user_tel_input.clear()
od_user_tel_input.send_keys(od_user_tel)

## 9. 수취인명
driver.find_element(By.XPATH, "//a[contains(text(), '수취인 정보')]").click()

recvr_nm_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_nm_loc"))
)
recvr_nm_input.clear()
recvr_nm_input.send_keys("김수취")

## 10. 수취인명(영어)
recvr_nm_eng_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_nm"))
)
recvr_nm_eng_input.clear()
recvr_nm_eng_input.send_keys("KimReciver")

## 11. 수취인명(이니셜)
recvr_nm_init_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_nm_init"))
)
recvr_nm_init_input.clear()
recvr_nm_init_input.send_keys("K.R.")

## 12. 수취인 휴대번호
recvr_mobile = "+8110" + current_day + "-" + current_time[-4:]
recvr_mobile_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_mobile"))
)
recvr_mobile_input.clear()
recvr_mobile_input.send_keys(recvr_mobile)

## 12. 수취인 전화번호
recvr_tel = "+812" + current_day + "-" + current_time[-4:]
recvr_tel_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_tel"))
)
recvr_tel_input.clear()
recvr_tel_input.send_keys(recvr_tel)

## 13. 수취인 이메일
recvr_email = current_day + "@test.com"
recvr_email_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_email_loc"))
)
recvr_email_input.clear()
recvr_email_input.send_keys(recvr_email)

## 14. 배송정보
driver.find_element(By.XPATH, "//a[contains(text(), '배송 정보')]").click()

## 15. 도착국가
#country = wait.until(
#    EC.presence_of_element_located((By.ID, "dest_country_cd"))
#)
#Select(country).select_by_value("JP")
country = wait.until(
    EC.presence_of_element_located((By.ID, "dest_country_cd"))
)

driver.execute_script(
    "arguments[0].value='JP'; arguments[0].dispatchEvent(new Event('change'));",
    country
)

## 16. 배송지 전체 주소
recvr_addr_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_addr_loc"))
)
recvr_addr_input.clear()
recvr_addr_input.send_keys("Japan")

## 17. 배송지 우편번호
recvr_zip_input = wait.until(
    EC.element_to_be_clickable((By.ID, "consignee_zipcode"))
)
recvr_zip_input.clear()
recvr_zip_input.send_keys("12345")

## 18. 사전통지구분
jp_notice_radio = wait.until(
    EC.presence_of_element_located((By.ID, "jp_notice_type_y"))
)
driver.execute_script("arguments[0].click();", jp_notice_radio)

## 19. 수신타입
jp_receive_type_radio = wait.until(
    EC.presence_of_element_located((By.ID, "jp_receive_type_phone"))
)
driver.execute_script("arguments[0].click();", jp_receive_type_radio)


## 20. 배달시간
jp_dlvr_time = wait.until(
    EC.presence_of_element_located((By.ID, "jp_dlvr_time_type"))
)
Select(jp_dlvr_time).select_by_value("AM")


## 21. 배송 메세지
dlvr_msg_input = wait.until(
    EC.element_to_be_clickable((By.ID, "dlvr_msg"))
)
dlvr_msg_input.clear()
dlvr_msg_input.send_keys("도착전 전화")

## 22. 기타>비고
driver.find_element(By.XPATH, "//a[contains(text(), '기타')]").click()
remark_info_input = wait.until(
    EC.element_to_be_clickable((By.ID, "remark_info"))
)
remark_info_input.clear()
remark_info_input.send_keys("해외배송" + current_day)

## 23. 저장
save_btn = wait.until(
    EC.element_to_be_clickable((By.ID, "saveBtn"))
#    EC.element_to_be_clickable((By.XPATH, "//button[@id='saveBtn']"))
)

save_btn.click()




