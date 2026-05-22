# Jupyter 노트북 사용 안내 (Mate2QA)

## 사이트 URL 바꾸기 (QA / 다른 서버)

**한 줄만 수정:** `Mate2QA_site_config.py` 의 `_DEFAULT_LOGIN_URL`
또는 `Mate2QA_login.env` 의 `LOGIN_URL=...`

자세한 설명: **`Mate2QA_URL설정안내.md`**

---

## 터미널에 `Jupyter: Create...` 를 치면 안 됩니다

PowerShell/터미널은 **명령어**만 받습니다.
`Jupyter: Create New Jupyter Notebook` 은 **Cursor 명령 팔레트**용 문구입니다.

| 하고 싶은 일 | 방법 |
|-------------|------|
| 새 노트북 만들기 | `Ctrl+Shift+P` → `Jupyter: Create New Blank Jupyter Notebook` |
| 기존 노트북 열기 | `D:\py3\Jupeter\Mate2QA_login.ipynb` 더블클릭 |
| 커널 선택 | 노트북 우측 상단 또는 `Ctrl+Shift+P` → `Notebook: Select Notebook Kernel` → **Python (py3 Mate2QA)** |
| 셀 실행 | 셀 선택 후 `Shift+Enter` |

## 준비된 노트북

| 파일 | 원본 스크립트 |
|------|----------------|
| `Jupeter\Mate2QA_login.ipynb` | 단계별 로그인 (1:페이지열기 → 2:ID → 3:PWD → 4:화주) |
| `Jupeter\Mate2QA_AddDomesticOrderForm.ipynb` | `Mate2QA_AddDomesticOrderForm.py` |

노트북을 다시 만들려면 (`.py` 수정 후):

```powershell
cd D:\py3
python _build_mate2qa_notebooks.py
```

## 셀 실행 순서

1. **위에서 아래로** 1번 셀부터 순서대로 실행합니다.
2. 함수 정의 셀을 건너뛰면 마지막 실행 셀에서 `NameError`가 납니다.
3. 브라우저가 열린 뒤에는 **마지막 실행 셀만** 다시 돌리지 말고, 브라우저를 닫거나 커널을 재시작한 뒤 처음부터 실행하는 것이 안전합니다.

## Cursor에서 AI로 셀 단위 작성

채팅에 예시처럼 요청합니다.

> `Jupeter\Mate2QA_login.ipynb` 3번 셀만 수정해줘. networkidle 타임아웃을 30초로.

Agent 모드이면 노트북 파일을 직접 수정할 수 있습니다.
