# 채용공고 모음

매시간 게시판을 확인해서 새 공고를 사이트에 모으고, 키워드에 맞는 새 공고만 메일로 알려줍니다.
서버 없이 GitHub(Actions + Pages)만으로 동작합니다.

## 설치 순서 (처음 한 번)

### 1. GitHub 저장소 만들기
1. GitHub에서 새 저장소를 만듭니다(예: `jobboard`). 공개/비공개 모두 가능하지만, **Pages를 무료로 쓰려면 공개**가 간단합니다.
2. 이 폴더의 파일을 전부 올립니다(`.github` 폴더 포함).

### 2. 사이트 켜기
저장소 Settings → Pages → Source를 `Deploy from a branch`, Branch를 `main` / `/docs`로 지정합니다.
주소는 `https://<아이디>.github.io/<저장소이름>/` 입니다.

### 3. 메일 설정 (보내는 계정 = 본인 계정)
저장소 Settings → Secrets and variables → Actions

**Secrets**
| 이름 | 값 |
|---|---|
| `SMTP_USER` | 보내는 메일 주소 (예: 본인 Gmail) |
| `SMTP_PASS` | 앱 비밀번호 (일반 로그인 비밀번호가 아님) |
| `MAIL_TO` | `hamae@kakao.com` (여러 명이면 쉼표로 구분) |

**Variables** (선택)
| 이름 | 값 |
|---|---|
| `SMTP_HOST` | 기본 `smtp.gmail.com` |
| `SMTP_PORT` | 기본 `465` |
| `SITE_URL` | 위 3번의 사이트 주소(메일에 "전체 공고 보기" 링크로 들어감) |

Gmail 앱 비밀번호: Google 계정 → 보안 → 2단계 인증 켜기 → "앱 비밀번호" 생성(16자리).
비밀번호는 GitHub 비밀값에만 입력하고 다른 곳에는 적지 마세요.

### 4. 첫 실행
Actions 탭 → `crawl` → Run workflow. 첫 실행은 **현재 공고를 기준선으로 저장만** 하고 메일은 보내지 않습니다.
이후 새로 올라온 공고부터 알림이 갑니다.

## 기관·키워드를 구글 시트로 관리하기

시트 1개에 탭 2개를 만듭니다.

**탭 `기관`** (1행은 제목 그대로)
| 기관명 | URL | 사용 | 방식 |
|---|---|---|---|
| 의정부시청 | https://www.ui4u.go.kr/portal/saeol/gosiList.do?seCode=05&mId=0301110000 | Y | 자동 |
| 의정부도시공사 | https://www.uiuc.or.kr/companyNotice/employmentPage/employment/list.do | Y | 자동 |
| 도봉구시설관리공단 | https://www.dobongsiseol.or.kr/contents/employment.html?menu1=1&menu2=4&menu3=2 | Y | 링크만 |

**탭 `키워드`**
| 구분 | 키워드 |
|---|---|
| 포함 | 기간제 |
| 제외 | 강사 |

- `포함`이 하나도 없으면 제외 키워드에 걸리지 않는 모든 새 공고를 알립니다.
- 키워드는 **알림 메일에만** 적용됩니다. 사이트에는 전체 공고가 보이고 검색창으로 거를 수 있습니다.

각 탭을 `파일 → 공유 → 웹에 게시`에서 **CSV** 형식으로 게시하고, 나온 주소를 저장소 Variables에 넣습니다.
- `SOURCES_CSV_URL` = `기관` 탭 CSV 주소
- `KEYWORDS_CSV_URL` = `키워드` 탭 CSV 주소

(설정하지 않으면 저장소의 `sources.default.csv`, `keywords.default.csv`를 사용합니다.)

## 새 기관 추가하기
`기관` 탭에 한 줄 추가합니다. 표 형태의 일반 게시판이면 기본 파서가 읽습니다.
- 사이트 화면의 기관 칩 아래에 "수집 실패" 안내가 뜨면 그 사이트는 구조가 달라 전용 파서가 필요합니다.
- 해당 사이트의 `robots.txt`가 자동 수집을 막아 둔 경우 수집하지 않고, "링크만"으로 두면 사이트에 바로가기만 표시됩니다.

## 알아둘 점
- GitHub Actions의 예약 실행은 몇 분씩 늦어질 수 있습니다.
- 저장소에 60일간 아무 활동이 없으면 GitHub가 예약 실행을 멈춥니다. 새 공고가 생겨 결과 파일이 갱신되면 활동으로 계속 집계됩니다.
- 의정부시청과 도시공사는 개별 글 주소를 직접 만들 수 없는 경우가 있어, 그런 공고는 게시판 목록으로 연결됩니다.

## 개발자용
```
pip install -r requirements.txt
python tests/test_parsers.py
python tests/test_flow.py
python crawler.py
```
