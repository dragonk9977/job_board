"""수집 → 신규 감지 → 키워드 필터 → 메일 호출 흐름 테스트(네트워크 없음)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crawler  # noqa: E402


def job(i, title, dept="", date="2026-11-17"):
    return {"id": str(i), "title": title, "dept": dept, "date": date, "status": "", "url": f"https://x/{i}"}


def run_once(tmp, pages, mail_ok=True):
    crawler.DATA_PATH = os.path.join(tmp, "data", "jobs.json")
    crawler.SITE_PATH = os.path.join(tmp, "docs", "jobs.json")
    sent = []
    crawler.load_sources = lambda: [
        {"name": "A기관", "url": "https://a.kr/list", "manual": False},
        {"name": "B공단", "url": "https://b.kr/list", "manual": True},
    ]
    crawler.load_keywords = lambda: (["기간제", "사무"], ["강사"])
    crawler.crawl_source = lambda src: (pages, "정상") if pages is not None else (None, "접속 실패")

    def fake_send(jobs):
        sent.append([j["title"] for j in jobs])
        return mail_ok
    crawler.send_mail = fake_send
    crawler.main()
    with open(crawler.DATA_PATH, encoding="utf-8") as f:
        return json.load(f), sent


def main():
    with tempfile.TemporaryDirectory() as tmp:
        # 1회차: 처음 수집 → 기준선만 저장, 메일 없음
        state, sent = run_once(tmp, [job(1, "기간제근로자 모집"), job(2, "주민센터 강사 모집")])
        assert sent == [], sent
        assert len(state["jobs"]) == 2
        assert state["sources"]["B공단"]["manual"] is True
        print("통과: 첫 수집은 알림 없이 기준선 저장")

        # 2회차: 신규 3건(키워드 일치 1, 제외 1, 불일치 1) → 일치 1건만 메일
        pages = [job(1, "기간제근로자 모집"), job(2, "주민센터 강사 모집"),
                 job(3, "사무보조 기간제 채용"), job(4, "기간제 강사 모집"), job(5, "시설 청소 용역")]
        state, sent = run_once(tmp, pages)
        assert sent == [["사무보조 기간제 채용"]], sent
        assert state["jobs"]["A기관|3"]["notified"] is True
        print("통과: 신규 중 키워드 일치 공고만 메일")

        # 3회차: 변화 없음 → 메일 없음
        state, sent = run_once(tmp, pages)
        assert sent == []
        print("통과: 변화 없으면 메일 없음")

        # 4회차: 신규 + 메일 실패 → 다음 회차에 재시도
        pages2 = pages + [job(6, "공무직 사무원 채용")]
        state, sent = run_once(tmp, pages2, mail_ok=False)
        assert sent == [["공무직 사무원 채용"]] and state["jobs"]["A기관|6"]["notified"] is False
        state, sent = run_once(tmp, pages2, mail_ok=True)
        assert sent == [["공무직 사무원 채용"]] and state["jobs"]["A기관|6"]["notified"] is True
        print("통과: 발송 실패 시 다음 회차에 재시도")

        # 5회차: 수집 실패 → 기존 공고 유지, 상태에 실패 표시
        state, sent = run_once(tmp, None)
        assert state["sources"]["A기관"]["ok"] is False and len(state["jobs"]) == 6
        print("통과: 수집 실패해도 기존 공고 유지")


if __name__ == "__main__":
    main()
