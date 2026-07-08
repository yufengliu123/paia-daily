import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import WEB_SOURCES, CATEGORIES

MAX_ITEMS_PER_SOURCE = 30
MAX_RETRIES = 2
RETRY_DELAY = 2
RECENCY_DAYS = 7  # 保留最近一周（周末政策更新少）
FETCH_CONTENT = True  # 抓取文章正文以获得更准确的日期和更丰富的摘要
MAX_CONTENT_CHARS = 2000  # 每篇文章最多取2000字正文

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def ensure_absolute_url(base, href):
    """将相对链接转为绝对链接"""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("./"):
        href = href[2:]
    return urljoin(base, href)


def extract_date_from_url(url):
    """从 URL 中提取发布日期，支持多种格式"""
    if not url:
        return ""

    # 完整日期 YYYYMMDD
    m = re.search(r"/(20\d{2})(\d{2})(\d{2})[/_\-]", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # YYYY-MM/DD 或 YYYY-MM-DD
    m = re.search(r"/(20\d{2})-(\d{2})(?:/|-)(\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 仅年月 YYYYMM (Gov.cn 格式)，取该月1号
    m = re.search(r"/(20\d{2})(\d{2})/content", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"

    # YYYY/MM/DD
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # YYMMDD 格式
    m = re.search(r"-(\d{2})(\d{2})(\d{2})\.", url)
    if m:
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return ""


def auto_classify(text):
    """自动分类"""
    text = text or ""
    for cat, keywords in CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return cat
    return "综合"


class WebScraper:
    """通用网页抓取器"""

    def __init__(self, cache_dir=".cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.today = datetime.now().date()

    def fetch_all(self) -> list[dict]:
        all_entries = []
        for source in WEB_SOURCES:
            entries = self._scrape_with_retry(source)
            all_entries.extend(entries)
            time.sleep(1.0)
        result = self._deduplicate(all_entries)
        result = self._filter_recent(result)
        return result

    def _scrape_with_retry(self, source: dict) -> list[dict]:
        name = source["name"]
        url = source["url"]
        selector = source.get("selector", "a")
        title_attr = source.get("title_attr", "text")
        link_attr = source.get("link_attr", "href")
        min_len = source.get("min_length", 12)

        for attempt in range(1, MAX_RETRIES + 2):
            try:
                resp = self.session.get(url, timeout=20)
                resp.encoding = resp.apparent_encoding or "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")

                entries = []
                seen = set()

                for el in soup.select(selector):
                    if title_attr == "text":
                        title = el.get_text(strip=True)
                    else:
                        title = (el.get(title_attr) or "").strip()

                    link_raw = el.get(link_attr, "") or ""
                    link = ensure_absolute_url(url, link_raw)

                    if not title or len(title) < min_len:
                        continue
                    if title in seen:
                        continue

                    pub_date = extract_date_from_url(link)

                    seen.add(title)
                    entries.append({
                        "source": name,
                        "title": title,
                        "link": link,
                        "summary": "",
                        "published": pub_date,
                        "fetched_at": datetime.now().isoformat(),
                        "category": auto_classify(title),
                    })

                    if len(entries) >= MAX_ITEMS_PER_SOURCE:
                        break

                # 批量抓取文章正文以获取准确日期和内容
                if FETCH_CONTENT:
                    self._enrich_entries(entries, name)

                print(f"  [ok] {name}: {len(entries)} items")
                return entries

            except Exception as e:
                if attempt <= MAX_RETRIES:
                    print(f"  [retry {attempt}/{MAX_RETRIES}] {name}: {e}")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  [!!] {name}: {e}")
                    return []

    def _deduplicate(self, entries):
        seen = set()
        unique = []
        for e in entries:
            key = hashlib.md5((e["link"] + e["title"]).encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                unique.append(e)
        print(f"\n[total] {len(unique)} unique out of {len(entries)} raw")
        return unique

    def _enrich_entries(self, entries, source_name):
        """抓取文章详情页获取正文内容和准确发布日期"""
        enriched = 0
        for e in entries:
            link = e.get("link", "")
            if not link or not (link.startswith("http://") or link.startswith("https://")):
                continue
            try:
                resp = self.session.get(link, timeout=12)
                resp.encoding = resp.apparent_encoding or "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")

                # 提取发布时间
                pub = self._extract_pub_date(soup, link)
                if pub:
                    e["published"] = pub

                # 提取正文
                body = self._extract_body(soup)
                if body:
                    e["summary"] = body[:MAX_CONTENT_CHARS]
                    enriched += 1
            except Exception:
                pass
        if enriched:
            print(f"     [content] enriched {enriched} articles with body text")

    @staticmethod
    def _extract_pub_date(soup, url):
        """从页面提取发布日期"""
        import re
        # meta tag
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            prop = (meta.get("property") or "").lower()
            content = meta.get("content", "")
            if "publish" in name or "pubdate" in name or "date" in name or \
               "publish" in prop or "pubdate" in prop:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", content)
                if m:
                    return m.group(1)
        # 包含"来源"或"发布时间"的文本
        for tag in soup.find_all(["span", "div", "p", "em"], string=re.compile(r"(发布时间|日期|时间)")):
            txt = tag.get_text()
            m = re.search(r"(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})", txt)
            if m:
                d = m.group(1).replace("年", "-").replace("月", "-").replace("/", "-").rstrip("日")
                parts = d.split("-")
                if len(parts) == 3:
                    return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        return ""

    @staticmethod
    def _extract_body(soup):
        """从文章页提取正文"""
        # 按优先级查找正文容器
        selectors = [
            "div.article", "div#article", "article",
            "div.detail", "div#detail", "div.content",
            "div.main-content", "div.news-content",
            "div[class*=article]", "div[class*=content]",
            "div.words", "div#zoom",
        ]
        for sel in selectors:
            div = soup.select_one(sel)
            if div:
                text = div.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return text

        # fallback: 找最长的 text block
        candidates = []
        for div in soup.find_all(["div", "article", "section"]):
            txt = div.get_text(separator=" ", strip=True)
            if 100 < len(txt) < 10000:
                candidates.append((len(txt), txt))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        return ""

    def _filter_recent(self, entries: list[dict]) -> list[dict]:
        """只保留最近 RECENCY_DAYS 天的文章"""
        cutoff = self.today - timedelta(days=RECENCY_DAYS)
        recent = []
        no_date = []
        for e in entries:
            pub = e.get("published", "")
            if pub:
                try:
                    d = datetime.strptime(pub[:10], "%Y-%m-%d").date()
                    if d >= cutoff:
                        recent.append(e)
                    else:
                        continue
                except ValueError:
                    no_date.append(e)
            else:
                no_date.append(e)

        # 如果有足够的已确认日期条目，优先用它们；
        # 无日期条目只保留少量作为补充
        result = list(recent)
        if len(recent) >= 10:
            no_date_limit = max(0, len(recent) // 3)  # keep ~1/3 as no-date margin
        else:
            no_date_limit = max(5, len(recent) * 2)     # more lenient when few dated items

        kept_no_date = no_date[:no_date_limit]
        dropped_no_date = len(no_date) - len(kept_no_date)
        dropped_old = len(entries) - len(recent) - len(no_date)

        if dropped_old > 0 or dropped_no_date > 0:
            parts = []
            if dropped_old: parts.append(f"{dropped_old} expired (>{RECENCY_DAYS}d)")
            if dropped_no_date: parts.append(f"{dropped_no_date} undated")
            print(f"[recency] dropped {' + '.join(parts)}, kept {len(result) + len(kept_no_date)}")

        return result + kept_no_date


def fetch_and_cache() -> list[dict]:
    scraper = WebScraper()
    entries = scraper.fetch_all()
    if not entries:
        cache_path = os.path.join(scraper.cache_dir, "latest_entries.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                if old:
                    print(f"[cache] fetch returned 0, keeping {len(old)} cached entries")
                    return old
            except: pass
        return []
    cache_path = os.path.join(scraper.cache_dir, "latest_entries.json")
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    import shutil
    shutil.move(tmp_path, cache_path)
    print(f"[cache] saved to {cache_path}")
    return entries
