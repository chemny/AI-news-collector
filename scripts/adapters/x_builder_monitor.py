import json
import html
import re
import ssl
import sys
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

try:
    import yaml
except ImportError:
    yaml = None


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DEFAULT_NITTER_INSTANCES = ["https://nitter.net"]


def fetch(config: dict, window_start, window_end) -> list[dict]:
    profiles_data = load_profiles_data(config)
    companies = {company.get("id"): company for company in profiles_data.get("companies", [])}
    profiles = profiles_data.get("builders", [])
    handles = config.get("handles")
    if handles:
        allowed = {handle.lower().lstrip("@") for handle in handles}
        profiles = [profile for profile in profiles if profile.get("handle", "").lower() in allowed]

    instances = config.get("nitter_instances") or DEFAULT_NITTER_INSTANCES
    max_items = int(config.get("max_items_per_builder", 5))
    include_reposts = bool(config.get("include_reposts", True))
    items = []

    for profile in profiles:
        handle = profile.get("handle", "").lstrip("@")
        if not handle:
            continue
        profile_max_items = int(profile.get("max_items") or max_items)
        try:
            feed_items, provider_url = fetch_first_available_feed(instances, handle)
        except Exception as exc:
            print(f"[x_builder_monitor] skip @{handle}: {exc}", file=sys.stderr)
            continue
        for raw_item in feed_items[:profile_max_items]:
            item = convert_rss_item(raw_item, profile, companies.get(profile.get("company_id")), handle, provider_url)
            if not item:
                continue
            if item["is_repost"] and not include_reposts:
                continue
            items.append(item)
        time.sleep(float(config.get("request_interval_seconds", 0.2)))
    return items


def load_profiles_data(config: dict) -> dict:
    path = config.get("profiles_path")
    if path:
        text = Path(path).read_text(encoding="utf-8")
        if path.endswith((".yaml", ".yml")):
            if yaml is None:
                data = parse_simple_profiles_yaml(text)
            else:
                data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        if isinstance(data, list):
            return {"builders": data, "companies": []}
        return {"builders": data.get("builders", []), "companies": data.get("companies", [])}
    return {"builders": config.get("builders", []), "companies": config.get("companies", [])}


def parse_simple_profiles_yaml(text: str) -> dict:
    builders = []
    companies = []
    section = None
    current = None
    current_list_key = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line.endswith(":"):
            if current:
                (builders if section == "builders" else companies).append(current)
            section = line[:-1]
            current = None
            current_list_key = None
            continue
        if line.startswith("- "):
            value = line[2:].strip()
            if current is not None and current_list_key and indent > 2:
                current.setdefault(current_list_key, []).append(parse_scalar(value))
                continue
            if current:
                (builders if section == "builders" else companies).append(current)
            current = {}
            current_list_key = None
            if value:
                key, value = value.split(":", 1)
                current[key.strip()] = parse_scalar(value)
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            if value.strip() == "":
                current[key] = []
                current_list_key = key
            else:
                current[key] = parse_scalar(value)
                current_list_key = None
    if current:
        (builders if section == "builders" else companies).append(current)
    return {"builders": builders, "companies": companies}


def parse_scalar(value: str):
    value = value.strip()
    if value in ("", "null", "Null", "NULL"):
        return None
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


def fetch_first_available_feed(instances: list[str], handle: str) -> tuple[list[ET.Element], str]:
    errors = []
    for base in instances:
        url = f"{base.rstrip('/')}/{handle}/rss"
        try:
            xml = fetch_bytes(url)
            root = ET.fromstring(xml)
            return root.findall(".//item"), url
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
    raise RuntimeError("; ".join(errors))


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    try:
        with urlopen(req, timeout=20) as response:
            return response.read()
    except (ssl.SSLCertVerificationError, URLError, HTTPError):
        context = ssl._create_unverified_context()
        with urlopen(req, timeout=20, context=context) as response:
            return response.read()


def convert_rss_item(node: ET.Element, profile: dict, company: dict | None, handle: str, provider_url: str) -> dict | None:
    title = clean_text(node.findtext("title") or "")
    description = clean_html(node.findtext("description") or "")
    text = clean_text(description or title)
    if not text:
        return None

    link = node.findtext("link") or ""
    url = normalize_x_url(link)
    published_at = parse_pub_date(node.findtext("pubDate") or "")
    is_repost = detect_repost(title, text, handle)
    original_handle = extract_handle_from_x_url(url) if is_repost else None
    display_name = profile.get("name") or handle

    source_priority = float(profile.get("priority") or (company or {}).get("priority") or 1.1)
    company_name = (company or {}).get("name")
    tags = ["builder-update", "x-builder"]
    tags.extend(profile.get("topics") or [])
    if company_name:
        tags.append(str(company_name))

    return {
        "title": text[:120],
        "content": text,
        "url": url,
        "author": display_name,
        "author_handle": handle,
        "source_name": f"X：{display_name} (@{handle})",
        "source": "X Builder Monitor",
        "source_type": "x",
        "platform": "x",
        "published_at": published_at,
        "category": "builder-update",
        "tags": tags,
        "source_tags": tags,
        "entity_tags": [value for value in [display_name, company_name] if value],
        "builder_id": profile.get("id"),
        "builder_role": profile.get("role"),
        "builder_type": profile.get("type"),
        "company_id": profile.get("company_id"),
        "company_name": company_name,
        "company_type": (company or {}).get("type"),
        "company_official_sources": (company or {}).get("official_sources") or [],
        "provider": "nitter",
        "provider_url": provider_url,
        "is_repost": is_repost,
        "original_handle": original_handle,
        "original_author": original_handle,
        "source_priority": source_priority,
        "source_reliability": 0.45,
        "raw_title": title,
        "raw_description": description,
    }


def normalize_x_url(url: str) -> str:
    url = (url or "").strip().replace("#m", "")
    url = url.replace("https://nitter.net/", "https://x.com/")
    return url


def parse_pub_date(value: str) -> str | None:
    if not value:
        return None
    dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def detect_repost(title: str, text: str, handle: str) -> bool:
    value = f"{title} {text}"
    match = re.search(r"RT by @([A-Za-z0-9_]+)", value)
    if match:
        return True
    return False


def extract_handle_from_x_url(url: str) -> str | None:
    match = re.search(r"https://x\.com/([^/]+)/status/", url or "")
    if not match:
        return None
    return match.group(1)


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return clean_text(value)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value
