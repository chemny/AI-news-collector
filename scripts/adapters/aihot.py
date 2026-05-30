import json
import ssl
from datetime import timezone
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen


BASE_URL = "https://aihot.virxact.com/api/public"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (ssl.SSLCertVerificationError, URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        context = ssl._create_unverified_context()
        with urlopen(req, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8"))


def fetch(config: dict, window_start, window_end) -> list[dict]:
    mode = config.get("mode", "selected")
    if mode == "daily":
        data = _get_json(f"{BASE_URL}/daily")
        items = []
        for section in data.get("sections", []):
            for item in section.get("items", []):
                item = dict(item)
                item["category"] = item.get("category") or section.get("label")
                item["source_name"] = item.get("sourceName") or "AIHOT"
                item["source"] = "AIHOT"
                item["raw_daily_date"] = data.get("date")
                items.append(item)
        return items

    params = {
        "mode": mode,
        "take": int(config.get("take", 100)),
        "since": window_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if config.get("category"):
        params["category"] = config["category"]
    if config.get("q"):
        params["q"] = config["q"]

    data = _get_json(f"{BASE_URL}/items?{urlencode(params)}")
    return data.get("items", [])
