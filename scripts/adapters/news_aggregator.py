import json
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError
from xml.etree import ElementTree as ET

try:
    import yaml
except ImportError:
    yaml = None


VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor/news-aggregator"
import sys

sys.path.insert(0, str(VENDOR_DIR))
from rss_parser import parse_rss_content


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

AI_NEWSLETTER_SOURCES = [
    ("Latent Space AINews", "https://www.latent.space/feed"),
    ("Interconnects", "https://www.interconnects.ai/feed"),
    ("One Useful Thing", "https://www.oneusefulthing.org/feed"),
    ("ChinAI", "https://chinai.substack.com/feed"),
    ("Memia", "https://memia.substack.com/feed"),
    ("AI to ROI", "https://ai2roi.substack.com/feed"),
    ("KDnuggets", "https://www.kdnuggets.com/feed"),
]

DEFAULT_AI_KEYWORDS = "AI,artificial intelligence,LLM,agent,OpenAI,Claude,GPT,Gemini,Anthropic,MCP"


def _fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read()
    except (ssl.SSLCertVerificationError, URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        context = ssl._create_unverified_context()
        with urlopen(req, timeout=timeout, context=context) as response:
            return response.read()


def _fetch_json(url: str, timeout: int = 20) -> dict:
    return json.loads(_fetch_bytes(url, timeout).decode("utf-8"))


def _within_window(item: dict, window_start, window_end) -> bool:
    value = item.get("published_at") or item.get("time")
    if not value:
        return True
    try:
        if isinstance(value, str) and value.lower() in {"today", "hot", "real-time"}:
            return True
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(str(value))
        except Exception:
            return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return window_start <= dt.astimezone(window_start.tzinfo) <= window_end


def _filter(items: list[dict], keyword: str | None, window_start, window_end, limit: int) -> list[dict]:
    if keyword:
        keywords = [part.strip().lower() for part in keyword.split(",") if part.strip()]
        items = [
            item
            for item in items
            if any(word in (item.get("title", "") + " " + item.get("summary", "")).lower() for word in keywords)
        ]
    items = [item for item in items if _within_window(item, window_start, window_end)]
    return items[:limit]


def fetch_hackernews(limit: int, keyword: str | None, window_start, window_end) -> list[dict]:
    items = []
    timestamp = int(window_start.timestamp())
    keyword = keyword or DEFAULT_AI_KEYWORDS
    if keyword:
        query = quote(" OR ".join(part.strip() for part in keyword.split(",") if part.strip()))
        url = f"https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=created_at_i>{timestamp}&hitsPerPage={limit * 2}&query={query}"
    else:
        url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={limit * 2}"
    try:
        data = _fetch_json(url)
        for hit in data.get("hits", []):
            item_id = hit.get("objectID")
            items.append(
                {
                    "source": "Hacker News",
                    "source_name": "Hacker News",
                    "title": hit.get("title") or hit.get("story_title"),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                    "summary": hit.get("story_text") or hit.get("comment_text") or "",
                    "published_at": datetime.fromtimestamp(hit.get("created_at_i", 0), timezone.utc).isoformat()
                    if hit.get("created_at_i")
                    else hit.get("created_at"),
                    "heat": f"{hit.get('points', 0)} points",
                    "like_count": hit.get("points"),
                    "comment_count": hit.get("num_comments"),
                    "engagement_raw": {
                        "points": hit.get("points"),
                        "comments": hit.get("num_comments"),
                    },
                    "source_type": "news",
                    "platform": "web",
                    "source_tags": ["hacker-news"],
                }
            )
    except Exception:
        pass
    if items:
        return _filter(items, keyword=None, window_start=window_start, window_end=window_end, limit=limit)

    try:
        html = _fetch_bytes("https://news.ycombinator.com/news").decode("utf-8", errors="ignore")
    except Exception:
        return []
    import re

    rows = re.findall(r'<tr class="athing" id="(\d+)">([\s\S]*?)</tr>', html)
    scores = dict(re.findall(r'<span class="score" id="score_(\d+)">([^<]+)</span>', html))
    for item_id, row in rows:
        title_match = re.search(r'<span class="titleline"><a href="([^"]+)">([\s\S]*?)</a>', row)
        if not title_match:
            continue
        href, title = title_match.groups()
        title = re.sub(r"<[^>]+>", "", title)
        if href.startswith("item?id="):
            href = "https://news.ycombinator.com/" + href
        items.append(
            {
                "source": "Hacker News",
                "source_name": "Hacker News",
                "title": title,
                "url": href,
                "summary": "",
                "published_at": None,
                "heat": scores.get(item_id, "0 points"),
                "like_count": scores.get(item_id, "0 points"),
                "engagement_raw": {"score": scores.get(item_id, "0 points")},
                "source_type": "news",
                "platform": "web",
                "source_tags": ["hacker-news"],
            }
        )
    return _filter(items, keyword=keyword, window_start=window_start, window_end=window_end, limit=limit)


def fetch_github(limit: int, keyword: str | None, window_start, window_end) -> list[dict]:
    url = "https://github.com/trending"
    if keyword:
        primary = keyword.split(",")[0].strip()
        url = f"https://github.com/topics/{quote(primary)}?o=desc&s=updated"
    try:
        html = _fetch_bytes(url).decode("utf-8", errors="ignore")
    except Exception:
        return []

    import re

    items = []
    for match in re.finditer(r'<article[\s\S]*?</article>', html):
        block = match.group(0)
        repo_match = re.search(r'href="/([^"/]+/[^"/]+)"', block)
        if not repo_match:
            continue
        repo = repo_match.group(1)
        desc_match = re.search(r'<p[^>]*>([\s\S]*?)</p>', block)
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc_match.group(1))).strip() if desc_match else ""
        star_match = re.search(r'href="/' + re.escape(repo) + r'/stargazers"[^>]*>([\s\S]*?)</a>', block)
        stars = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", star_match.group(1))).strip() if star_match else ""
        fork_match = re.search(r'href="/' + re.escape(repo) + r'/forks"[^>]*>([\s\S]*?)</a>', block)
        forks = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", fork_match.group(1))).strip() if fork_match else ""
        items.append(
            {
                "source": "GitHub Trending",
                "source_name": "GitHub Trending",
                "title": f"{repo} - {desc}" if desc else repo,
                "url": f"https://github.com/{repo}",
                "summary": desc,
                "published_at": None,
                "heat": f"{stars} stars" if stars else None,
                "like_count": stars,
                "repost_count": forks,
                "engagement_raw": {"stars": stars, "forks": forks},
                "source_type": "github",
                "platform": "github",
                "source_tags": ["github-trending"],
            }
        )
    return _filter(items, keyword=keyword if not keyword else None, window_start=window_start, window_end=window_end, limit=limit)


def fetch_arxiv(limit: int, keyword: str | None, window_start, window_end) -> list[dict]:
    cats = "cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG"
    query = quote(keyword.split(",")[0].strip()) if keyword else cats
    search_query = f"all:{query}" if keyword else cats
    url = f"https://export.arxiv.org/api/query?search_query={search_query}&sortBy=submittedDate&sortOrder=descending&max_results={limit * 2}"
    try:
        xml = _fetch_bytes(url, timeout=45)
    except Exception:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").replace("\n", " ").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").replace("\n", " ").strip()
        published = entry.findtext("atom:published", default="", namespaces=ns)
        link = ""
        for link_node in entry.findall("atom:link", ns):
            if link_node.attrib.get("rel") == "alternate":
                link = link_node.attrib.get("href", "")
                break
        items.append(
            {
                "source": "arXiv",
                "source_name": "arXiv",
                "title": title,
                "url": link,
                "summary": summary,
                "published_at": published,
                "heat": None,
                "source_type": "paper",
                "platform": "web",
                "source_tags": ["arxiv"],
            }
        )
    return _filter(items, keyword=None, window_start=window_start, window_end=window_end, limit=limit)


def fetch_rss(url: str, name: str, limit: int, keyword: str | None, window_start, window_end) -> list[dict]:
    try:
        items = parse_rss_content(_fetch_bytes(url), name, limit * 2)
    except Exception:
        return []
    return _filter(items, keyword=keyword, window_start=window_start, window_end=window_end, limit=limit)


def load_source_registry(path: str | None) -> dict:
    if not path:
        return {"sources": []}
    registry_path = Path(path)
    if not registry_path.exists():
        return {"sources": []}
    text = registry_path.read_text(encoding="utf-8")
    if registry_path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            return parse_source_registry_yaml_subset(text)
        return yaml.safe_load(text) or {"sources": []}
    return json.loads(text)


def parse_source_registry_yaml_subset(text: str) -> dict:
    sources = []
    external_curated_sources = []
    section = None
    current = None
    current_list_key = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line.endswith(":"):
            if current is not None and section in {"sources", "external_curated_sources"}:
                (sources if section == "sources" else external_curated_sources).append(current)
            section = line[:-1]
            current = None
            current_list_key = None
            continue
        if section not in {"sources", "external_curated_sources"}:
            continue
        if line.startswith("- "):
            value = line[2:].strip()
            if current is not None and current_list_key and indent > 2:
                current.setdefault(current_list_key, []).append(parse_scalar(value))
                continue
            if current is not None:
                (sources if section == "sources" else external_curated_sources).append(current)
            current = {}
            current_list_key = None
            if value and ":" in value:
                key, value = value.split(":", 1)
                current[key.strip()] = parse_scalar(value)
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                current[key] = []
                current_list_key = key
            else:
                current[key] = parse_scalar(value)
                current_list_key = None

    if current is not None and section in {"sources", "external_curated_sources"}:
        (sources if section == "sources" else external_curated_sources).append(current)
    return {"sources": sources, "external_curated_sources": external_curated_sources}


def parse_scalar(value: str):
    value = value.strip()
    if value in {"null", "Null", "NULL", ""}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def fetch_registry_sources(config: dict, keyword: str | None, window_start, window_end) -> list[dict]:
    registry = load_source_registry(config.get("registry_path"))
    keyword = keyword or config.get("registry_keyword")
    statuses = set(config.get("registry_statuses") or ["owned", "verify"])
    per_source_limit = int(config.get("registry_per_source_limit") or 5)
    total_limit = int(config.get("registry_total_limit") or config.get("limit", 30))
    items = []
    for source in registry.get("sources", []):
        if not source.get("enabled", True):
            continue
        if source.get("migration_status") not in statuses:
            continue
        rss = source.get("rss")
        if not rss:
            continue
        source_items = fetch_rss(rss, source.get("name") or source.get("id"), per_source_limit, keyword, window_start, window_end)
        source_items = [item for item in source_items if item.get("published_at")]
        for item in source_items:
            item.update(
                {
                    "source": source.get("name") or item.get("source"),
                    "source_name": source.get("name") or item.get("source_name"),
                    "source_type": source.get("type") or item.get("source_type") or "rss",
                    "platform": source.get("platform") or item.get("platform") or "web",
                    "category": item.get("category") or "registry-source",
                    "source_tags": source.get("tags") or [],
                    "entity_tags": [value for value in [source.get("company_id")] if value],
                    "source_priority": source.get("priority"),
                    "source_reliability": source.get("reliability"),
                    "is_official_source": int(source.get("type") == "official_blog"),
                    "is_primary_source": int(source.get("type") in {"official_blog", "blog", "changelog"}),
                    "registry_source_id": source.get("id"),
                    "registry_migration_status": source.get("migration_status"),
                }
            )
        items.extend(source_items)
        if len(items) >= total_limit:
            break
        time.sleep(float(config.get("registry_request_interval_seconds", 0.1)))
    return items[:total_limit]


def fetch_ai_newsletters(limit: int, keyword: str | None, window_start, window_end) -> list[dict]:
    items = []
    for name, url in AI_NEWSLETTER_SOURCES:
        items.extend(fetch_rss(url, name, max(2, limit // 3), keyword, window_start, window_end))
        time.sleep(0.1)
    return items[:limit]


def find_opml(config: dict) -> Path | None:
    paths = []
    if config.get("opml_path"):
        paths.append(Path(config["opml_path"]))
    paths.append(Path.home() / ".config/news-aggregator/user_sources.opml")
    for path in paths:
        if path.exists():
            return path
    return None


def fetch_user(limit: int, keyword: str | None, window_start, window_end, config: dict) -> list[dict]:
    opml = find_opml(config)
    if not opml:
        return []
    try:
        root = ET.fromstring(opml.read_text(encoding="utf-8"))
    except Exception:
        return []
    feeds = []
    for node in root.iter("outline"):
        url = node.attrib.get("xmlUrl")
        if url:
            feeds.append((node.attrib.get("title") or node.attrib.get("text") or "User Feed", url))
    items = []
    for name, url in feeds:
        items.extend(fetch_rss(url, name, 3, keyword, window_start, window_end))
        if len(items) >= limit:
            break
    return items[:limit]


def fetch(config: dict, window_start, window_end) -> list[dict]:
    requested = config.get("sources") or ["github", "hackernews", "ai_newsletters"]
    limit = int(config.get("limit", 15))
    keyword = config.get("keyword")
    all_items = []
    for source in requested:
        if source == "hackernews":
            all_items.extend(fetch_hackernews(limit, keyword, window_start, window_end))
        elif source == "github":
            all_items.extend(fetch_github(limit, keyword, window_start, window_end))
        elif source == "arxiv":
            all_items.extend(fetch_arxiv(limit, keyword, window_start, window_end))
        elif source == "ai_newsletters":
            all_items.extend(fetch_ai_newsletters(limit, keyword, window_start, window_end))
        elif source == "aihot":
            all_items.extend(fetch_rss("https://aihot.virxact.com/rss", "AIHOT", limit, keyword, window_start, window_end))
        elif source == "source_registry":
            all_items.extend(fetch_registry_sources(config, keyword, window_start, window_end))
        elif source == "user":
            all_items.extend(fetch_user(limit, keyword, window_start, window_end, config))
    return all_items
