#!/usr/bin/env python3
"""채용공고 수집기.

1) 기관 목록(구글 시트 CSV 또는 sources.default.csv)을 읽는다.
2) robots.txt를 확인하고 허용된 게시판만 수집한다.
3) data/jobs.json 에 누적 저장하고 docs/jobs.json 으로 복사한다(사이트용).
4) 새 공고 중 키워드 조건에 맞는 것만 메일로 보낸다.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import smtplib
import sys
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from urllib import robotparser
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data", "jobs.json")
SITE_PATH = os.path.join(ROOT, "docs", "jobs.json")
KST = dt.timezone(dt.timedelta(hours=9))
UA = "JobBoardBot/1.0 (personal use, hourly)"
TIMEOUT = 20
MAX_JOBS = 3000
NOTIFY_WINDOW_DAYS = 3  # 이 기간보다 오래된 미발송 공고는 알림에서 제외


def now_iso():
    return dt.datetime.now(KST).isoformat(timespec="seconds")


def clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


# ---------------------------------------------------------------- 설정 읽기
def read_csv_text(env_name, default_file):
    url = os.environ.get(env_name, "").strip()
    if url:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
            return r.content.decode("utf-8-sig")
        except requests.RequestException as e:
            print(f"[경고] {env_name} 읽기 실패, 기본 파일 사용: {e}")
    path = os.path.join(ROOT, default_file)
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    return ""


def load_sources():
    rows = csv.DictReader(io.StringIO(read_csv_text("SOURCES_CSV_URL", "sources.default.csv")))
    out = []
    for r in rows:
        name = clean(r.get("기관명"))
        url = clean(r.get("URL"))
        if not name or not url:
            continue
        if clean(r.get("사용", "Y")).upper() in ("N", "X", "아니오", "FALSE"):
            continue
        out.append({"name": name, "url": url, "manual": clean(r.get("방식")) == "링크만"})
    return out


def load_keywords():
    include, exclude = [], []
    rows = csv.DictReader(io.StringIO(read_csv_text("KEYWORDS_CSV_URL", "keywords.default.csv")))
    for r in rows:
        kind, kw = clean(r.get("구분")), clean(r.get("키워드"))
        if not kw:
            continue
        (exclude if kind == "제외" else include).append(kw)
    return include, exclude


def matches(job, include, exclude):
    text = f"{job['title']} {job.get('dept', '')}"
    if any(k in text for k in exclude):
        return False
    return not include or any(k in text for k in include)


# ---------------------------------------------------------------- robots.txt
_robots_cache = {}


def robots_allows(url):
    """True: 허용, False: 금지, None: 판단 불가(이번엔 수집하지 않음)."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
        except requests.RequestException:
            _robots_cache[base] = None
        else:
            if 400 <= r.status_code < 500:
                _robots_cache[base] = True  # robots.txt 없음 = 제한 없음
            elif r.status_code >= 500:
                _robots_cache[base] = None
            else:
                rp = robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
                _robots_cache[base] = rp
    entry = _robots_cache[base]
    if entry is None:
        return None
    if entry is True:
        return True
    return entry.can_fetch(UA, url)


# ---------------------------------------------------------------- 파서
def parse_ui4u(html, source_url):
    """의정부시청 채용 공고 게시판."""
    mid = parse_qs(urlparse(source_url).query).get("mId", ["0301110000"])[0]
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("td.taL a")
        if not a:
            continue
        m = re.search(r"boardView\('(\d+)',\s*'(\d+)'\)", a.get("onclick", ""))
        if not m:
            continue
        badge = a.select_one(".ico_ing, .ico_end, .ico_close")
        status = clean(badge.get_text()) if badge else ""
        for s in a.select("span"):
            s.extract()
        date = tr.select_one("td.date")
        dept = tr.select_one("td.list_division")
        jobs.append({
            "id": m.group(2),
            "title": clean(a.get_text()),
            "dept": clean(dept.get_text()) if dept else "",
            "date": clean(date.get_text()) if date else "",
            "status": status,
            "url": f"https://www.ui4u.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo={m.group(2)}&mId={mid}",
        })
    return jobs


def parse_uiuc(html, source_url):
    """의정부도시공사 채용공고. 상세 링크가 암호화된 POST라 목록 주소로 연결한다."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a.board_title")
        num = tr.select_one(".board_num")
        if not a or not num:
            continue
        date = tr.select_one(".edit_date")
        jobs.append({
            "id": clean(num.get_text()),
            "title": clean(a.get_text()),
            "dept": "",
            "date": clean(date.get_text()) if date else "",
            "status": "",
            "url": source_url,
        })
    return jobs


DATE_RE = re.compile(r"(\d{4})[-./](\d{2})[-./](\d{2})")


def parse_generic(html, source_url):
    """일반 게시판(표 형태) 추정 파서. 새 기관 추가용 기본값."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for tr in soup.select("table tr"):
        links = [a for a in tr.select("a") if len(clean(a.get_text())) >= 5]
        if not links:
            continue
        a = max(links, key=lambda x: len(clean(x.get_text())))
        title = clean(a.get_text())
        m = DATE_RE.search(tr.get_text(" "))
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
        href = a.get("href", "")
        url = source_url
        if href and not href.startswith(("javascript", "#")):
            url = requests.compat.urljoin(source_url, href)
        key = hashlib.sha1(f"{title}|{date}".encode()).hexdigest()[:12]
        jobs.append({"id": key, "title": title, "dept": "", "date": date, "status": "", "url": url})
    return jobs


PARSERS = {"ui4u.go.kr": parse_ui4u, "uiuc.or.kr": parse_uiuc}


def pick_parser(url):
    host = urlparse(url).netloc.lower()
    for domain, fn in PARSERS.items():
        if host.endswith(domain):
            return fn
    return parse_generic


# ---------------------------------------------------------------- 수집
def crawl_source(src):
    """(jobs, status_message) 반환. 실패하면 jobs=None."""
    allowed = robots_allows(src["url"])
    if allowed is False:
        return None, "robots.txt가 자동 수집을 금지함"
    if allowed is None:
        return None, "robots.txt를 확인하지 못해 건너뜀"
    try:
        r = requests.get(src["url"], headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        return None, f"접속 실패: {e.__class__.__name__}"
    jobs = pick_parser(src["url"])(r.content, src["url"])
    if not jobs:
        return None, "공고를 찾지 못함(페이지 구조가 바뀌었을 수 있음)"
    return jobs, "정상"


# ---------------------------------------------------------------- 메일
def send_mail(jobs):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    to = os.environ.get("MAIL_TO", "")
    if not (user and pw and to):
        print("[경고] SMTP_USER/SMTP_PASS/MAIL_TO 미설정: 메일을 보내지 않음")
        return False
    site = os.environ.get("SITE_URL", "")
    lines_html, lines_txt = [], []
    for j in jobs:
        lines_html.append(
            f'<li><b>[{escape(j["source"])}]</b> <a href="{escape(j["url"])}">{escape(j["title"])}</a>'
            f' <span style="color:#888">{escape(j.get("date", ""))}</span></li>'
        )
        lines_txt.append(f'[{j["source"]}] {j["title"]} ({j.get("date", "")})\n  {j["url"]}')
    body_html = f"<p>새 채용공고 {len(jobs)}건</p><ul>{''.join(lines_html)}</ul>"
    if site:
        body_html += f'<p><a href="{escape(site)}">전체 공고 보기</a></p>'
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"[채용공고] 새 공고 {len(jobs)}건", "utf-8")
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText("\n".join(lines_txt), "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, pw)
            s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        print(f"[오류] 메일 발송 실패: {e.__class__.__name__}: {e}")
        return False
    print(f"메일 발송 완료: {len(jobs)}건 -> {to}")
    return True


# ---------------------------------------------------------------- 메인
def load_state():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"updated": "", "sources": {}, "jobs": {}}


def main():
    state = load_state()
    sources = load_sources()
    include, exclude = load_keywords()
    now = now_iso()
    new_sources_state = {}

    for src in sources:
        name = src["name"]
        prev = state["sources"].get(name, {})
        entry = {"url": src["url"], "manual": src["manual"], "checked": now,
                 "status": "링크만 제공", "last_ok": prev.get("last_ok", ""), "ok": True}
        if src["manual"]:
            new_sources_state[name] = entry
            continue
        jobs, msg = crawl_source(src)
        entry["status"] = msg
        if jobs is None:
            entry["ok"] = False
            new_sources_state[name] = entry
            print(f"[{name}] 실패: {msg}")
            continue
        entry["last_ok"] = now
        baseline = not prev.get("last_ok")  # 처음 수집하는 기관은 알림 없이 기준선만 저장
        added = 0
        for j in jobs:
            key = f"{name}|{j['id']}"
            if key in state["jobs"]:
                state["jobs"][key].update({k: j[k] for k in ("title", "dept", "date", "status", "url")})
                continue
            rec = dict(j, source=name, first_seen=now, notified=baseline)
            state["jobs"][key] = rec
            added += 1
        print(f"[{name}] {len(jobs)}건 읽음, 신규 {added}건{' (기준선)' if baseline else ''}")
        new_sources_state[name] = entry

    # 사용 중단된 기관의 상태는 지우고, 공고는 보관
    state["sources"] = new_sources_state

    # 알림 대상: 아직 안 보냈고, 최근이고, 키워드에 맞는 것
    cutoff = dt.datetime.now(KST) - dt.timedelta(days=NOTIFY_WINDOW_DAYS)
    pending = []
    for rec in state["jobs"].values():
        if rec.get("notified"):
            continue
        if dt.datetime.fromisoformat(rec["first_seen"]) < cutoff:
            rec["notified"] = True
            continue
        if matches(rec, include, exclude):
            pending.append(rec)
        else:
            rec["notified"] = True  # 키워드 불일치는 알림 대상에서 제외(사이트에는 표시)
    if pending:
        pending.sort(key=lambda r: r.get("date", ""), reverse=True)
        if send_mail(pending):
            for rec in pending:
                rec["notified"] = True

    # 오래된 공고 정리
    if len(state["jobs"]) > MAX_JOBS:
        keep = sorted(state["jobs"].items(), key=lambda kv: kv[1]["first_seen"], reverse=True)[:MAX_JOBS]
        state["jobs"] = dict(keep)

    state["updated"] = now
    for path in (DATA_PATH, SITE_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
