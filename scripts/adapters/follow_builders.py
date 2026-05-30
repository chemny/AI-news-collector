import json
import ssl
import time
from http.client import IncompleteRead
from urllib.error import URLError
from urllib.request import Request, urlopen


FEEDS = {
    "x": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json",
    "podcasts": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-podcasts.json",
    "blogs": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-blogs.json",
}


def _get_json(url: str) -> dict:
    last_error = None
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (ssl.SSLCertVerificationError, URLError) as exc:
            reason = getattr(exc, "reason", exc)
            if not isinstance(reason, ssl.SSLCertVerificationError):
                last_error = exc
            else:
                context = ssl._create_unverified_context()
                try:
                    with urlopen(req, timeout=30, context=context) as response:
                        return json.loads(response.read().decode("utf-8"))
                except Exception as retry_exc:
                    last_error = retry_exc
        except IncompleteRead as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(1 + attempt)
    raise last_error


def fetch(config: dict, window_start, window_end) -> list[dict]:
    selected_feeds = config.get("feeds") or ["x", "podcasts", "blogs"]
    items = []

    if "x" in selected_feeds:
        data = _get_json(FEEDS["x"])
        for builder in data.get("x", []):
            for tweet in builder.get("tweets", []):
                items.append(
                    {
                        "title": tweet.get("text", "")[:120] or f"Tweet by {builder.get('name')}",
                        "summary": tweet.get("text"),
                        "content": tweet.get("text"),
                        "url": tweet.get("url"),
                        "author": builder.get("name"),
                        "builder": builder.get("name"),
                        "source_name": "Follow Builders",
                        "source": "Follow Builders",
                        "source_type": "x",
                        "platform": "x",
                        "published_at": tweet.get("created_at") or tweet.get("publishedAt"),
                        "category": "builder-update",
                        "raw_feed": "x",
                    }
                )

    if "podcasts" in selected_feeds:
        data = _get_json(FEEDS["podcasts"])
        for podcast in data.get("podcasts", []):
            items.append(
                {
                    "title": podcast.get("title") or podcast.get("name"),
                    "summary": podcast.get("summary"),
                    "content": podcast.get("transcript"),
                    "url": podcast.get("url"),
                    "author": podcast.get("name"),
                    "source_name": "Follow Builders",
                    "source": "Follow Builders",
                    "source_type": "podcast",
                    "platform": "youtube" if "youtube.com" in (podcast.get("url") or "") else "web",
                    "published_at": podcast.get("publishedAt"),
                    "category": "podcast",
                    "raw_feed": "podcasts",
                }
            )

    if "blogs" in selected_feeds:
        data = _get_json(FEEDS["blogs"])
        for blog in data.get("blogs", []):
            items.append(
                {
                    "title": blog.get("title"),
                    "summary": blog.get("summary"),
                    "content": blog.get("content"),
                    "url": blog.get("url"),
                    "author": blog.get("name") or blog.get("source"),
                    "source_name": blog.get("name") or "Follow Builders",
                    "source": "Follow Builders",
                    "source_type": "blog",
                    "platform": "web",
                    "published_at": blog.get("publishedAt"),
                    "category": "official-blog",
                    "raw_feed": "blogs",
                }
            )

    return [item for item in items if item.get("title") and item.get("url")]
