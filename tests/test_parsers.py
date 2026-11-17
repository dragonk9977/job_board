"""파서 테스트: 실제 게시판에서 확인한 행(2026-11-17)을 고정 자료로 사용한다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crawler  # noqa: E402

UI4U = """
<table><tbody>
<tr> <td class="num">2259</td> <td>의정부시 호원1동 공고 <br> 제2026-54호</td>
<td class="taL"> <a href="#" onclick="javascript:boardView('1', '69976');return false;">
<span class="ico_ing">진행</span> 2027년 호원1동 주민자치센터 프로그램 강사 서류전형 합격자 결정 및 면접시험 시행계획 공고&nbsp;<span class="ico_new">새글</span> </a> </td>
<td class="list_division">호원1동</td> <td class="date">2026-11-17</td> </tr>
<tr> <td class="num">2257</td> <td>의정부시 공고 <br> 제2026-2198호</td>
<td class="taL"> <a href="#" onclick="javascript:boardView('1', '69959');return false;">
<span class="ico_ing">진행</span> 2026년 하반기 농어민 기회소득 업무보조 기간제근로자 서류전형 합격자 발표 및 면접전형 시행 공고 </a> </td>
<td class="list_division">도시농업과</td> <td class="date">2026-11-16</td> </tr>
</tbody></table>
"""

UIUC = """
<table><tbody>
<tr bgcolor="#ffffff"> <td><p class="board_num">620</p></td>
<td id="NTT_SJ0" style="text-align: left;"> <a class="board_title" href="javascript:goViewContents('ec/abc');">2026년 제3회 동계체육팀 기간제근로자 채용 공고[육아휴직대체 전기, 기계]</a> </td>
<td><span class="hidden_txt">조회수</span> <p class="viewers">180</p></td>
<td><span class="hidden_txt">조회수</span> <p class="edit_date">2026-11-13</p></td> </tr>
<tr bgcolor="#ffffff"> <td><p class="board_num">618</p></td>
<td> <a class="board_title" href="javascript:goViewContents('ec/def');">의정부도시공사 임원(비상임이사) 공개모집 최종합격자 공고</a> </td>
<td><p class="viewers">93</p></td> <td><p class="edit_date">2026-11-09</p></td> </tr>
</tbody></table>
"""

GENERIC = """
<table><tr><td>1</td><td><a href="/view?id=7">2026년 기간제 근로자 채용 공고</a></td><td>2026.11.10</td></tr>
<tr><td>2</td><td><a href="#" onclick="x()">시설관리 직원 모집 안내</a></td><td>2026-11-09</td></tr></table>
"""


def test_ui4u():
    src = "https://www.ui4u.go.kr/portal/saeol/gosiList.do?seCode=05&mId=0301110000"
    jobs = crawler.parse_ui4u(UI4U, src)
    assert len(jobs) == 2
    j = jobs[1]
    assert j["id"] == "69959"
    assert j["title"].startswith("2026년 하반기 농어민 기회소득")
    assert "진행" not in j["title"]
    assert j["dept"] == "도시농업과" and j["date"] == "2026-11-16" and j["status"] == "진행"
    assert j["url"] == "https://www.ui4u.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo=69959&mId=0301110000"
    assert "새글" not in jobs[0]["title"]


def test_uiuc():
    src = "https://www.uiuc.or.kr/companyNotice/employmentPage/employment/list.do"
    jobs = crawler.parse_uiuc(UIUC, src)
    assert [j["id"] for j in jobs] == ["620", "618"]
    assert jobs[0]["date"] == "2026-11-13" and jobs[0]["url"] == src


def test_generic():
    jobs = crawler.parse_generic(GENERIC, "https://example.go.kr/list")
    assert len(jobs) == 2
    assert jobs[0]["url"] == "https://example.go.kr/view?id=7" and jobs[0]["date"] == "2026-11-10"
    assert jobs[1]["url"] == "https://example.go.kr/list"


def test_pick_parser():
    assert crawler.pick_parser("https://www.ui4u.go.kr/x") is crawler.parse_ui4u
    assert crawler.pick_parser("https://www.uiuc.or.kr/x") is crawler.parse_uiuc
    assert crawler.pick_parser("https://other.kr/x") is crawler.parse_generic


def test_keyword_match():
    job = {"title": "2026년 기간제근로자 채용", "dept": "도시농업과"}
    assert crawler.matches(job, ["기간제"], [])
    assert not crawler.matches(job, ["공무직"], [])
    assert not crawler.matches(job, ["기간제"], ["도시농업"])
    assert crawler.matches(job, [], [])  # 포함 키워드가 비면 전체 허용


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("통과:", name)
