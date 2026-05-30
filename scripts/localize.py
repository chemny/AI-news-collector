import re


KEYWORD_TRANSLATIONS = {
    "agent": "智能体",
    "agents": "智能体",
    "ai": "AI",
    "api": "API",
    "app": "应用",
    "benchmark": "评测",
    "cache": "缓存",
    "claude": "Claude",
    "code": "代码",
    "coding": "编程",
    "developer": "开发者",
    "developers": "开发者",
    "gemini": "Gemini",
    "github": "GitHub",
    "gpt": "GPT",
    "launch": "发布",
    "model": "模型",
    "models": "模型",
    "openai": "OpenAI",
    "paper": "论文",
    "product": "产品",
    "prompt": "提示词",
    "release": "发布",
    "research": "研究",
    "tool": "工具",
    "tools": "工具",
    "update": "更新",
    "video": "视频",
}

ENTITY_STOPWORDS = {
    "a",
    "acm",
    "ai",
    "aie",
    "also",
    "an",
    "and",
    "before",
    "fast",
    "if",
    "in",
    "introducing",
    "it",
    "latest",
    "of",
    "on",
    "or",
    "our",
    "read",
    "rt",
    "they",
    "the",
    "this",
    "that",
    "we",
    "when",
    "with",
    "you",
    "your",
}


def has_chinese(text: str | None) -> bool:
    return bool(text and re.search(r"[\u4e00-\u9fff]", text))


def localize_record(raw: dict, title: str, summary: str | None) -> tuple[str | None, str | None, str]:
    """Return Chinese title, Chinese summary, and translation status.

    This hook is deliberately conservative. It does not invent translations without
    a configured translation backend. Many upstream sources, especially AIHOT,
    already provide Chinese titles and summaries; those pass through as source_zh.
    """
    explicit_title = raw.get("title_zh") or raw.get("titleZh") or raw.get("zh_title")
    explicit_summary = raw.get("summary_zh") or raw.get("summaryZh") or raw.get("zh_summary")
    if explicit_title or explicit_summary:
        return explicit_title or title, explicit_summary or summary, "source_zh"

    if has_chinese(title) or has_chinese(summary):
        return title, summary, "source_zh"

    return None, None, "needs_translation"


def make_compact_zh_title(text: str | None) -> str | None:
    text = sanitize_english(text)
    if not text:
        return None
    entities = extract_entities(text)
    theme = infer_theme(text)
    if entities:
        return f"{'、'.join(entities[:2])}：{theme}"
    return theme


def make_compact_zh_summary(text: str | None, max_length: int = 150) -> str | None:
    text = sanitize_english(text)
    if not text:
        return None
    entities = extract_entities(text)
    theme = infer_theme(text)
    subject = "这条信息"
    if entities:
        subject = "、".join(entities[:2])
    mapped_terms = extract_mapped_terms(text)
    details = f"，涉及{ '、'.join(mapped_terms[:4]) }" if mapped_terms else ""
    action = infer_action(text)
    summary = f"{subject}{action}{theme}{details}。"
    return truncate_zh(summary, max_length)


def sanitize_english(text: str | None) -> str:
    text = strip_emoji(text or "")
    text = re.sub(r"https?[:：]//\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\btiktok\.com/\S+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ，。:：-")
    return text


def extract_entities(text: str) -> list[str]:
    entities = []
    for match in re.findall(r"\b[A-Z][A-Za-z0-9._-]{1,}\b", text):
        if match.lower() in ENTITY_STOPWORDS:
            continue
        if match not in entities:
            entities.append(match)
    for name in ("OpenAI", "Anthropic", "Claude", "Gemini", "Google", "GitHub", "Mistral", "NVIDIA", "Meta"):
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.I) and name not in entities:
            entities.insert(0, name)
    return entities[:4]


def extract_mapped_terms(text: str) -> list[str]:
    terms = []
    lower = text.lower()
    for key, label in KEYWORD_TRANSLATIONS.items():
        if re.search(rf"\b{re.escape(key)}\b", lower) and label not in terms:
            terms.append(label)
    return terms


def infer_theme(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("launch", "release", "rollout", "introduce", "announce")):
        return "发布新产品或功能"
    if any(word in lower for word in ("paper", "research", "technical report", "benchmark")):
        return "发布研究或技术进展"
    if any(word in lower for word in ("developer", "coding", "code", "api", "prompt")):
        return "更新开发者工具和编程能力"
    if any(word in lower for word in ("limit", "pricing", "subscription", "marketplace")):
        return "调整产品体验和商业策略"
    if any(word in lower for word in ("agent", "workflow", "automation")):
        return "推进智能体和自动化工作流"
    return "分享 AI 行业动态"


def infer_action(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("launch", "release", "rollout", "introduce", "announce")):
        return "发布或推出"
    if any(word in lower for word in ("feedback", "fix", "improve", "update")):
        return "更新"
    if any(word in lower for word in ("paper", "research", "report", "benchmark")):
        return "披露"
    if any(word in lower for word in ("build", "building", "developer", "coding")):
        return "讨论"
    return "提到"


def truncate_zh(text: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip("，,；;：: ") + "…"


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
