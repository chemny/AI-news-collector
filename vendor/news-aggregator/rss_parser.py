from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree as ET


def _text(node, name):
    child = node.find(name)
    if child is None or child.text is None:
        return ""
    return unescape(child.text.strip())


def parse_rss_content(content: bytes | str, source_name: str, limit: int = 20) -> list[dict]:
    if isinstance(content, str):
        content = content.encode("utf-8", errors="ignore")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    items = []
    channel = root.find("channel")
    if channel is not None:
        nodes = channel.findall("item")
        for node in nodes[:limit]:
            title = _text(node, "title")
            link = _text(node, "link") or _text(node, "guid")
            summary = _text(node, "description")
            pub_date = _text(node, "pubDate")
            items.append(
                {
                    "source": source_name,
                    "source_name": source_name,
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "published_at": _parse_date(pub_date),
                    "time": pub_date,
                    "source_type": "rss",
                    "platform": "rss",
                }
            )
        return [item for item in items if item.get("title") and item.get("url")]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for node in root.findall("atom:entry", ns)[:limit]:
        title = _text_ns(node, "title", ns)
        link = ""
        for link_node in node.findall("atom:link", ns):
            href = link_node.attrib.get("href")
            if href:
                link = href
                break
        summary = _text_ns(node, "summary", ns) or _text_ns(node, "content", ns)
        published = _text_ns(node, "published", ns) or _text_ns(node, "updated", ns)
        items.append(
            {
                "source": source_name,
                "source_name": source_name,
                "title": title,
                "url": link,
                "summary": summary,
                "published_at": _parse_date(published),
                "time": published,
                "source_type": "rss",
                "platform": "rss",
            }
        )
    return [item for item in items if item.get("title") and item.get("url")]


def _text_ns(node, name, ns):
    child = node.find(f"atom:{name}", ns)
    if child is None or child.text is None:
        return ""
    return unescape(child.text.strip())


def _parse_date(value: str):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except Exception:
        return value

