#수동 로그인 후 샘플 화주에서 일괄 기본발송인 처리

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

driver = webdriver.Chrome()

driver.get("https://qa-oms.ourbox.co.kr/om/login/login.do")

input("로그인 후 엔터를 누르세요...")

driver.get("https://qa-oms.ourbox.co.kr/om/order/putOrder/putOrderList.do")

wait = WebDriverWait(driver, 10)
# 샘플 화주선택
select_element = wait.until(
    EC.presence_of_element_located((By.ID, "pwn_header_change"))
)
dropdown = Select(select_element)
dropdown.select_by_value("PWN00002")


# 1.발송인 등록 버튼 클릭
sender_btn = wait.until(
    EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'발송인 등록')]"))
)
sender_btn.click()

# 2.일괄 발송인 등록 클릭
bulk_sender_btn = wait.until(
    EC.element_to_be_clickable((By.XPATH, "//a[@id='all_sender_rgst']"))
)
bulk_sender_btn.click()

# 3.기본 발송인 선택 클릭
basic_button = wait.until(
    EC.element_to_be_clickable((By.ID, "selectDefaultSender"))
)
basic_button.click()

# 4. alert창 OK 버튼 클릭
for _ in range(3):
    try:
        ok_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".swal2-confirm"))
        )
        ok_button.click()
    except:
        break
        

time.sleep(1000)