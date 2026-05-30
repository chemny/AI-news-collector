import hashlib
import json
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from localize import localize_record


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "ref",
    "fbclid",
    "gclid",
}


PROCESSING_VERSION = "source-items-v3"
AI_PROCESSING_MODEL = "local-extractive"
AI_PROCESSING_VERSION = "title-summary-v1"


OFFICIAL_SOURCE_KEYWORDS = {
    "anthropic",
    "openai",
    "google",
    "deepmind",
    "microsoft",
    "meta",
    "mistral",
    "github",
    "hugging face",
    "nvidia",
    "claude",
}

PRIMARY_SOURCE_TYPES = {"blog", "github", "paper", "podcast", "video"}


def sha256_short(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parts.path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(query, doseq=True),
            "",
        )
    )


def normalize_title(title: str) -> str:
    title = (title or "").strip().lower().replace("\u3000", " ")
    title = re.sub(r"\s+-\s+reuters$", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def detect_language(text: str) -> str:
    text = text or ""
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    if zh and en:
        return "mixed"
    if zh:
        return "zh"
    if en:
        return "en"
    return "unknown"


def clean_inline_text(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    value = strip_emoji(str(value))
    value = re.sub(r"\s+", " ", str(value)).strip()
    if not value:
        return None
    if max_length is not None:
        return value[:max_length]
    return value


def clean_summary_text(value: str | None, source_type: str | None = None, max_length: int = 150) -> str | None:
    value = clean_inline_text(value)
    if not value:
        return None
    # Social posts often include handles, links, hashtags, and CTA copy. These
    # are useful as raw payload, but noisy as a daily-briefing summary.
    value = strip_emoji(value)
    value = re.sub(r"https?[:：]//\S+", "", value)
    value = re.sub(r"www\.\S+", "", value)
    value = re.sub(r"@\w+", "", value)
    value = re.sub(r"#\w+", "", value)
    value = re.sub(r"(了解更多|阅读更多|learn more|read more)[:：]?\s*\S*", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" ，。:：-")
    if not value:
        return None
    # Drop handle/list-only summaries. A summary must contain at least one
    # substantive sentence-like phrase.
    meaningful = re.sub(r"[，。、,.:\s·&和与及+]+", "", value)
    if len(meaningful) < 12:
        return None
    return summarize_text(value, max_length)


def clean_content_text(value: str | None, max_length: int = 2000) -> str | None:
    value = clean_inline_text(value)
    if not value:
        return None
    value = re.sub(r"https?[:：]//\S+", "", value)
    value = re.sub(r"www\.\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ，。:：-")
    if not value:
        return None
    meaningful = re.sub(r"[，。、,.:\s·&和与及+]+", "", value)
    if len(meaningful) < 12:
        return None
    return value[:max_length]


def split_sentences(text: str | None) -> list[str]:
    text = clean_content_text(text, 4000)
    if not text:
        return []
    parts = re.split(r"(?<=[。！？.!?])\s+|[。！？!?]\s*", text)
    sentences = []
    for part in parts:
        part = clean_inline_text(part)
        if not part:
            continue
        if is_noise_text(part):
            continue
        sentences.append(part)
    return sentences


def is_noise_text(text: str | None) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    lower = value.lower()
    if re.search(r"https?[:：]//|www\.", value):
        return True
    if re.fullmatch(r"[@#\w\s,，、:：.-]+", value) and len(value) < 40:
        return True
    noise_phrases = (
        "了解更多",
        "阅读更多",
        "点击查看",
        "博客文章完成了思考",
        "引用",
        "learn more",
        "read more",
        "subscribe",
        "sign up",
    )
    return any(phrase in lower for phrase in noise_phrases)


def title_quality_flags(title: str | None, source_type: str | None = None) -> list[str]:
    flags = []
    if not title:
        return ["missing_title"]
    value = title.strip()
    if len(value) > 80:
        flags.append("too_long")
    generic_patterns = (
        r"分享\s*AI\s*行业动态",
        r"AI\s*行业动态",
        r"分享.*动态",
        r"博文?文章完成了思考",
    )
    if any(re.search(pattern, value, flags=re.I) for pattern in generic_patterns):
        flags.append("generic_title")
    if re.search(r"https?[:：]//|www\.", value):
        flags.append("contains_url")
    if source_type in {"x", "twitter"} and len(value) > 40:
        flags.append("social_title_too_long")
    return flags


def summary_quality_flags(summary: str | None) -> list[str]:
    flags = []
    if not summary:
        return ["missing_summary"]
    value = summary.strip()
    if len(value) < 40:
        flags.append("too_short")
    if re.search(r"https?[:：]//|www\.", value):
        flags.append("contains_url")
    if re.search(r"@\w+|#\w+", value):
        flags.append("contains_social_noise")
    if is_noise_text(value):
        flags.append("noise_summary")
    return flags


def build_generated_title(text: str | None, raw: dict, max_length: int = 20) -> str | None:
    text = clean_content_text(text, 1200)
    if not text:
        return None
    if detect_language(text) in {"zh", "mixed"}:
        for sentence in split_sentences(text):
            sentence = re.sub(r"^[【\[]?引用[】\]]?[：: ]*", "", sentence).strip()
            clause = re.split(r"[，,；;。.!?！？]", sentence)[0].strip()
            if len(clause) >= 6:
                return truncate_display_title(clause, max_length)
    entities = []
    for key in ("author", "builder", "sourceName", "source"):
        value = clean_inline_text(raw.get(key), 24)
        if value and value.lower() not in {"aihot", "x"}:
            entities.append(value)
            break
    for match in re.findall(r"\b(OpenAI|Anthropic|Claude|Gemini|Google|GitHub|Mistral|NVIDIA|Meta|Microsoft|Perplexity|Cursor|Grok|DeepMind)\b", text, flags=re.I):
        canonical = match[0].upper() + match[1:] if match.islower() else match
        if canonical not in entities:
            entities.append(canonical)
    lower = text.lower()
    if any(word in lower for word in ("launch", "release", "rollout", "introduce", "announce")):
        action = "发布新功能"
    elif any(word in lower for word in ("paper", "research", "benchmark", "report")):
        action = "披露研究进展"
    elif any(word in lower for word in ("developer", "coding", "code", "api", "sdk")):
        action = "更新开发工具"
    elif any(word in lower for word in ("agent", "workflow", "automation")):
        action = "推进智能体能力"
    elif any(word in lower for word in ("funding", "raise", "valuation", "invest")):
        action = "获得融资进展"
    else:
        action = "更新AI产品"
    subject = entities[0] if entities else "AI"
    return truncate_display_title(f"{subject}{action}", max_length)


def build_generated_summary(text: str | None, max_length: int = 200) -> str | None:
    sentences = split_sentences(text)
    if not sentences:
        return None
    selected = []
    total = 0
    for sentence in sentences:
        sentence = sentence.strip(" ，,。.!?！？")
        if len(sentence) < 12:
            continue
        selected.append(sentence)
        total += len(sentence)
        if total >= 120 or len(selected) >= 3:
            break
    if not selected:
        return None
    language = detect_language(" ".join(selected))
    separator = "。" if language in {"zh", "mixed"} else ". "
    summary = separator.join(selected)
    if language in {"zh", "mixed"} and not summary.endswith("。"):
        summary += "。"
    elif language == "en" and not summary.endswith("."):
        summary += "."
    return truncate_summary(summary, max_length)


def truncate_display_title(text: str, max_length: int) -> str:
    text = clean_inline_text(text) or ""
    text = text.strip(" ，,。:：-")
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip("，,：: -")


def truncate_summary(text: str, max_length: int) -> str:
    text = clean_inline_text(text) or ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip("，,；;：: ") + "…"


def as_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, tuple | set):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [item for item in parsed if item not in (None, "")]
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def as_json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def parse_count(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().lower().replace(",", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1000000
        text = text[:-1]
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return int(float(match.group(1)) * multiplier)


def first_count(raw: dict, keys: list[str]) -> int | None:
    for key in keys:
        if key in raw:
            count = parse_count(raw.get(key))
            if count is not None:
                return count
    metrics = raw.get("metrics") or raw.get("stats") or raw.get("engagement") or {}
    if isinstance(metrics, dict):
        for key in keys:
            if key in metrics:
                count = parse_count(metrics.get(key))
                if count is not None:
                    return count
    return None


def extract_metrics(raw: dict) -> dict:
    heat = raw.get("heat")
    metrics = {
        "like_count": first_count(raw, ["like_count", "likes", "likeCount", "favorite_count", "favorites"]),
        "comment_count": first_count(raw, ["comment_count", "comments", "commentCount", "num_comments", "descendants"]),
        "repost_count": first_count(raw, ["repost_count", "reposts", "retweet_count", "retweets", "shares", "share_count"]),
        "favorite_count": first_count(raw, ["favorite_count", "favorites", "bookmark_count", "bookmarks", "saved_count", "saves"]),
        "view_count": first_count(raw, ["view_count", "views", "viewCount", "play_count", "plays"]),
        "quote_count": first_count(raw, ["quote_count", "quotes", "quoteCount"]),
        "reply_count": first_count(raw, ["reply_count", "replies", "replyCount"]),
        "author_followers": first_count(raw, ["author_followers", "followers", "follower_count", "followers_count"]),
    }
    if heat and metrics["like_count"] is None:
        heat_text = str(heat).lower()
        if "star" in heat_text or "point" in heat_text:
            metrics["like_count"] = parse_count(heat)
    if heat and metrics["comment_count"] is None and "comment" in str(heat).lower():
        metrics["comment_count"] = parse_count(heat)
    return metrics


def calculate_engagement_score(metrics: dict) -> float:
    weights = {
        "like_count": 1.0,
        "comment_count": 2.0,
        "repost_count": 2.5,
        "favorite_count": 1.8,
        "view_count": 0.3,
        "quote_count": 2.2,
        "reply_count": 1.8,
    }
    score = 0.0
    for key, weight in weights.items():
        value = metrics.get(key)
        if value is not None and value > 0:
            score += math.log1p(value) * weight
    return round(score, 4)


def calculate_freshness_score(published_at: str | None, collected_at: str) -> float:
    published = parse_iso(published_at)
    collected = parse_iso(collected_at)
    if not published or not collected:
        return 0.5
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=published.tzinfo)
    age_hours = max((collected.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600, 0)
    if age_hours >= 24:
        return 0.0
    return round(1 - (age_hours / 24), 4)


def calculate_velocity_score(engagement_score: float, published_at: str | None, collected_at: str) -> float:
    published = parse_iso(published_at)
    collected = parse_iso(collected_at)
    if not published or not collected or engagement_score <= 0:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=published.tzinfo)
    age_hours = max((collected.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600, 0.25)
    return round(engagement_score / age_hours, 4)


def normalize_source_priority(value: float | int | None) -> float:
    if value is None:
        return 0.5
    return round(max(min(float(value) / 2, 1), 0), 4)


def normalize_velocity(value: float | int | None) -> float:
    if value is None or value <= 0:
        return 0.0
    return round(max(min(math.log1p(float(value)) / math.log1p(20), 1), 0), 4)


def calculate_collector_rank_score(
    platform_engagement_percentile: float | None,
    engagement_velocity_score: float,
    source_priority: float,
    source_reliability: float,
    freshness_score: float,
) -> float:
    percentile = 0.5 if platform_engagement_percentile is None else platform_engagement_percentile
    score = (
        percentile * 0.35
        + normalize_velocity(engagement_velocity_score) * 0.25
        + normalize_source_priority(source_priority) * 0.20
        + max(min(source_reliability, 1), 0) * 0.15
        + max(min(freshness_score, 1), 0) * 0.05
    )
    return round(score, 4)


def infer_tags(title: str, summary: str | None, raw: dict) -> tuple[list[str], list[str], list[str], dict]:
    text = f"{title} {summary or ''} {raw.get('content') or ''}".lower()
    entities = []
    entity_map = {
        "OpenAI": ["openai", "chatgpt", "gpt-"],
        "Anthropic": ["anthropic", "claude"],
        "Google": ["google", "gemini", "deepmind"],
        "Microsoft": ["microsoft", "github copilot"],
        "Meta": ["meta", "llama"],
        "Mistral": ["mistral"],
        "NVIDIA": ["nvidia"],
        "GitHub": ["github"],
        "Hugging Face": ["hugging face", "huggingface"],
    }
    for label, needles in entity_map.items():
        if any(needle in text for needle in needles):
            entities.append(label)

    topics = []
    topic_map = {
        "模型发布": ["model", "模型", "gpt", "claude", "gemini", "llama"],
        "AI 编程": ["coding", "code", "编程", "developer", "copilot", "codex"],
        "Agent": ["agent", "智能体"],
        "MCP": ["mcp", "model context protocol"],
        "视频生成": ["video", "视频", "veo", "sora"],
        "图像生成": ["image", "图片", "图像"],
        "开源项目": ["github", "open source", "开源"],
        "论文研究": ["arxiv", "paper", "research", "论文"],
        "产品发布": ["launch", "release", "发布", "上线"],
        "安全合规": ["security", "safety", "安全", "policy", "合规"],
    }
    for label, needles in topic_map.items():
        if any(needle in text for needle in needles):
            topics.append(label)

    audience = []
    audience_map = {
        "程序员": ["coding", "developer", "github", "api", "编程", "代码"],
        "产品经理": ["product", "launch", "feature", "产品", "功能"],
        "创作者": ["video", "image", "creator", "内容", "小红书", "抖音"],
        "创业者": ["startup", "business", "market", "商业", "创业"],
        "研究者": ["paper", "arxiv", "research", "论文", "研究"],
    }
    for label, needles in audience_map.items():
        if any(needle in text for needle in needles):
            audience.append(label)

    confidence = {
        "entity": 0.7 if entities else 0,
        "topic": 0.65 if topics else 0,
        "audience": 0.6 if audience else 0,
    }
    return entities, topics, audience, confidence


def infer_platform_hints(source_type: str, platform: str, topic_tags: list[str], audience_tags: list[str]) -> list[str]:
    hints = set()
    if source_type in {"blog", "paper", "news"}:
        hints.add("wechat")
    if "AI 编程" in topic_tags or "开源项目" in topic_tags:
        hints.update(["wechat", "bilibili", "x"])
    if "视频生成" in topic_tags or "图像生成" in topic_tags or "创作者" in audience_tags:
        hints.update(["xiaohongshu", "douyin", "bilibili"])
    if platform == "x":
        hints.add("x")
    if not hints:
        hints.update(["wechat", "x"])
    return sorted(hints)


def infer_content_type(source_type: str, raw: dict, title: str, summary: str | None) -> str:
    value = raw.get("content_type") or raw.get("type")
    if value:
        return str(value).lower()
    text = f"{title} {summary or ''}".lower()
    if source_type == "paper":
        return "paper"
    if source_type == "github":
        return "repo"
    if "launch" in text or "发布" in text or "release" in text:
        return "launch"
    if "how to" in text or "tutorial" in text or "指南" in text:
        return "tutorial"
    if source_type == "x":
        return "discussion"
    return "news"


def infer_source_quality(raw: dict, source_name: str, source_type: str, platform: str, content_type: str) -> tuple[float, float, int, int]:
    configured_reliability = raw.get("source_reliability")
    configured_priority = raw.get("source_priority")
    if configured_reliability is not None:
        reliability = float(configured_reliability)
    elif source_type in {"paper", "github"}:
        reliability = 0.75
    elif source_type == "blog":
        reliability = 0.7
    elif platform == "x":
        reliability = 0.45
    else:
        reliability = 0.55

    haystack = f"{source_name} {raw.get('author') or ''} {raw.get('source') or ''}".lower()
    is_official = int(bool(raw.get("is_official_source")) or any(keyword in haystack for keyword in OFFICIAL_SOURCE_KEYWORDS))
    is_primary = int(bool(raw.get("is_primary_source")) or is_official or source_type in PRIMARY_SOURCE_TYPES)
    if is_official:
        reliability = max(reliability, 0.85)
    if is_primary:
        reliability = max(reliability, 0.7)

    if configured_priority is not None:
        priority = float(configured_priority)
    else:
        priority = 1.0
        if is_official:
            priority += 0.5
        if content_type in {"launch", "paper", "repo"}:
            priority += 0.2
    return round(reliability, 3), round(priority, 3), is_official, is_primary


def summarize_text(value: str, max_length: int = 150) -> str:
    value = strip_emoji(value)
    value = re.sub(r"https?[:：]//\S+", "", value)
    value = re.sub(r"www\.\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_length:
        return value
    parts = re.split(r"(?<=[。！？.!?])\s*", value)
    summary = ""
    for part in parts:
        if not part:
            continue
        if len(summary) + len(part) <= max_length:
            summary += part
        else:
            break
    if summary:
        return summary.strip()
    return value[: max_length - 1].rstrip("，,；;：: ") + "…"


def strip_emoji(value: str) -> str:
    return re.sub(
        "["
        "\U0001F1E6-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "]+",
        "",
        value,
    )


def infer_source_type(raw: dict) -> str:
    value = (raw.get("source_type") or raw.get("type") or "").lower()
    if value:
        return value
    source = (raw.get("source") or raw.get("source_name") or "").lower()
    url = (raw.get("url") or "").lower()
    if "x.com" in url or "twitter.com" in url:
        return "x"
    if "youtube.com" in url or "youtu.be" in url:
        return "video"
    if "github.com" in url or "github" in source:
        return "github"
    if "paper" in source or "arxiv" in source:
        return "paper"
    if "podcast" in source:
        return "podcast"
    return "news"


def infer_platform(raw: dict) -> str:
    platform = (raw.get("platform") or "").lower()
    if platform:
        return platform
    url = (raw.get("url") or "").lower()
    source = (raw.get("source") or raw.get("source_name") or "").lower()
    if "x.com" in url or "twitter.com" in url:
        return "x"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "github.com" in url or "github" in source:
        return "github"
    if url:
        return "web"
    return "other"


def normalize_item(raw: dict, raw_source: str, collected_at: str, daily_bucket: str) -> dict | None:
    url = raw.get("url") or raw.get("sourceUrl") or raw.get("link")
    if not url:
        return None

    canonical_url = canonicalize_url(url)
    source_type = infer_source_type(raw)
    content = clean_content_text(raw.get("content") or raw.get("transcript"))
    raw_title = clean_inline_text(raw.get("title") or raw.get("title_zh") or raw.get("name"))
    raw_summary_value = raw.get("summary") or raw.get("description")
    raw_summary = clean_summary_text(raw_summary_value, source_type, 200)
    text_fallback = clean_content_text(raw.get("text"), 2000)
    source_text = content or text_fallback or raw_summary or raw_title

    title_flags = title_quality_flags(raw_title, source_type)
    if raw_title and "generic_title" not in title_flags and "contains_url" not in title_flags:
        title = raw_title
        title_source = "cleaned" if title != (raw.get("title") or raw.get("title_zh") or raw.get("name")) else "raw"
    else:
        title = build_generated_title(source_text, raw)
        title_source = "generated" if title else "missing"
        title_flags = title_quality_flags(title, source_type)
    if not title:
        return None

    summary_flags = summary_quality_flags(raw_summary)
    if raw_summary and not any(flag in summary_flags for flag in ("too_short", "contains_url", "contains_social_noise", "noise_summary")):
        summary = raw_summary
        summary_source = "cleaned" if summary != raw_summary_value else "raw"
    else:
        summary = build_generated_summary(source_text, 200)
        summary_source = "generated" if summary else "missing"
        summary_flags = summary_quality_flags(summary)

    normalized_title = normalize_title(title)
    if not summary and not content:
        return None
    title_zh, summary_zh, translation_status = localize_record(raw, title, summary)
    title_zh = clean_inline_text(title_zh)
    summary_zh = clean_summary_text(summary_zh, source_type, 200)
    author = clean_inline_text(
        raw.get("author")
        or raw.get("builder")
        or raw.get("sourceName")
        or raw.get("source")
    )
    author_handle = clean_inline_text(raw.get("author_handle") or raw.get("handle"))
    source_name = raw.get("source_name") or raw.get("source") or raw.get("sourceName") or raw_source
    published_at = raw.get("published_at") or raw.get("publishedAt") or raw.get("time")
    tags = as_json_list(raw.get("tags") or raw.get("topics") or raw.get("categories"))
    metrics = extract_metrics(raw)
    engagement_score = raw.get("engagement_score")
    if engagement_score is None:
        engagement_score = calculate_engagement_score(metrics)
    engagement_score = float(engagement_score or 0)
    source_tags = as_json_list(raw.get("source_tags") or raw.get("sourceTags") or tags)
    entity_tags = as_json_list(raw.get("entity_tags") or raw.get("entityTags"))
    topic_tags = as_json_list(raw.get("topic_tags") or raw.get("topicTags"))
    audience_tags = as_json_list(raw.get("audience_tags") or raw.get("audienceTags"))
    inferred_entities, inferred_topics, inferred_audience, tag_confidence = infer_tags(title, summary, raw)
    entity_tags = sorted(set(entity_tags + inferred_entities))
    topic_tags = sorted(set(topic_tags + inferred_topics))
    if not topic_tags:
        if source_type == "paper":
            topic_tags = ["论文研究"]
        elif source_type == "github":
            topic_tags = ["开源项目"]
        elif source_type in {"podcast", "video"}:
            topic_tags = ["视频内容"]
        else:
            topic_tags = ["AI 资讯"]
    audience_tags = sorted(set(audience_tags + inferred_audience))
    platform = infer_platform(raw)
    platform_hint = as_json_list(raw.get("platform_hint") or raw.get("platform_hints") or raw.get("target_platforms"))
    if not platform_hint:
        platform_hint = infer_platform_hints(source_type, platform, topic_tags, audience_tags)
    content_type = infer_content_type(source_type, raw, title, summary)
    source_reliability, source_priority, is_official_source, is_primary_source = infer_source_quality(
        raw, source_name, source_type, platform, content_type
    )
    platform_engagement_percentile = raw.get("platform_engagement_percentile")
    if platform_engagement_percentile is not None:
        platform_engagement_percentile = float(platform_engagement_percentile)
    freshness_score = calculate_freshness_score(published_at, collected_at)
    engagement_velocity_score = calculate_velocity_score(engagement_score, published_at, collected_at)
    collector_rank_score = calculate_collector_rank_score(
        platform_engagement_percentile,
        engagement_velocity_score,
        source_priority,
        source_reliability,
        freshness_score,
    )
    engagement_raw = as_json_dict(raw.get("engagement_raw") or raw.get("metrics") or raw.get("stats") or raw.get("engagement"))
    if raw.get("heat") is not None:
        engagement_raw.setdefault("heat", raw.get("heat"))
    media_urls = as_json_list(raw.get("media_urls") or raw.get("media") or raw.get("images") or raw.get("image"))
    related_urls = as_json_list(raw.get("related_urls") or raw.get("links"))
    missing_fields = []
    for field_name, field_value in (
        ("title", title),
        ("url", url),
        ("published_at", published_at),
        ("source_name", source_name),
    ):
        if not field_value:
            missing_fields.append(field_name)
    quality_flags = []
    quality_flags.extend(f"title_{flag}" for flag in title_flags)
    quality_flags.extend(f"summary_{flag}" for flag in summary_flags)
    if not content:
        quality_flags.append("missing_content")
    if translation_status == "needs_translation":
        quality_flags.append("needs_translation")
    mapping_status = "ok" if not missing_fields else "partial"

    text_for_hash = f"{normalized_title}\n{summary or ''}\n{(content or '')[:500]}"
    content_hash = "content:" + sha256_short(text_for_hash)
    dedupe_key = "url:" + sha256_short(canonical_url) if canonical_url else content_hash
    raw_identity = json.dumps(raw, ensure_ascii=False, sort_keys=True)[:2000]
    uid_seed = f"{daily_bucket}:{raw_source}:{source_name}:{dedupe_key}:{normalized_title}:{raw_identity}"

    return {
        "item_uid": "src_" + sha256_short(uid_seed, 20),
        "title": title,
        "title_zh": title_zh,
        "title_source": title_source,
        "title_quality_flags_json": json.dumps(title_flags, ensure_ascii=False),
        "normalized_title": normalized_title,
        "source_name": source_name,
        "source_type": source_type,
        "platform": platform,
        "url": url,
        "canonical_url": canonical_url,
        "author": author,
        "author_handle": author_handle,
        "published_at": published_at,
        "collected_at": collected_at,
        "updated_at": collected_at,
        "summary": summary if summary else None,
        "summary_zh": summary_zh,
        "summary_source": summary_source,
        "summary_quality_flags_json": json.dumps(summary_flags, ensure_ascii=False),
        "content": content,
        "category": raw.get("category"),
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "language": raw.get("language") or detect_language(f"{title} {summary or ''}"),
        "heat": raw.get("heat"),
        "like_count": metrics.get("like_count"),
        "comment_count": metrics.get("comment_count"),
        "repost_count": metrics.get("repost_count"),
        "favorite_count": metrics.get("favorite_count"),
        "view_count": metrics.get("view_count"),
        "quote_count": metrics.get("quote_count"),
        "reply_count": metrics.get("reply_count"),
        "engagement_score": engagement_score,
        "platform_engagement_percentile": platform_engagement_percentile,
        "engagement_velocity_score": engagement_velocity_score,
        "freshness_score": freshness_score,
        "collector_rank_score": collector_rank_score,
        "engagement_raw_json": json.dumps(engagement_raw, ensure_ascii=False),
        "source_tags_json": json.dumps(source_tags, ensure_ascii=False),
        "entity_tags_json": json.dumps(entity_tags, ensure_ascii=False),
        "topic_tags_json": json.dumps(topic_tags, ensure_ascii=False),
        "audience_tags_json": json.dumps(audience_tags, ensure_ascii=False),
        "platform_hint_json": json.dumps(platform_hint, ensure_ascii=False),
        "tag_confidence_json": json.dumps(tag_confidence, ensure_ascii=False),
        "source_reliability": source_reliability,
        "source_priority": source_priority,
        "author_followers": metrics.get("author_followers"),
        "author_verified": int(bool(raw.get("author_verified") or raw.get("verified"))),
        "author_profile_json": json.dumps(as_json_dict(raw.get("author_profile")), ensure_ascii=False),
        "is_official_source": is_official_source,
        "is_primary_source": is_primary_source,
        "content_type": content_type,
        "media_urls_json": json.dumps(media_urls, ensure_ascii=False),
        "related_urls_json": json.dumps(related_urls, ensure_ascii=False),
        "raw_metrics_at": raw.get("raw_metrics_at") or raw.get("metrics_at") or collected_at,
        "provider": raw.get("provider"),
        "is_repost": int(bool(raw.get("is_repost"))),
        "original_author": clean_inline_text(raw.get("original_author")),
        "original_handle": clean_inline_text(raw.get("original_handle")),
        "raw_record_uid": raw.get("_raw_record_uid"),
        "raw_source": raw_source,
        "dedupe_key": dedupe_key,
        "content_hash": content_hash,
        "daily_bucket": daily_bucket,
        "status": "new",
        "translation_status": translation_status,
        "mapping_status": mapping_status,
        "missing_fields_json": json.dumps(missing_fields, ensure_ascii=False),
        "quality_flags_json": json.dumps(quality_flags, ensure_ascii=False),
        "processing_version": PROCESSING_VERSION,
        "ai_processing_model": AI_PROCESSING_MODEL if title_source == "generated" or summary_source == "generated" else None,
        "ai_processing_version": AI_PROCESSING_VERSION if title_source == "generated" or summary_source == "generated" else None,
    }


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return parsedate_to_datetime(value)
    except Exception:
        pass
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
