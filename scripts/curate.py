#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from briefing_config import default_dimensions, load_simple_yaml
from collect import load_config
from db import connect, init_db, replace_event_clusters, replace_topic_candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--date")
    parser.add_argument("--dimensions")
    parser.add_argument("--min-score", type=float, default=0)
    args = parser.parse_args()

    config = load_config(args.config)
    conn = connect(config["project"]["database_path"])
    init_db(conn)
    daily_bucket = args.date or datetime.now().date().isoformat()
    dimensions_path = args.dimensions or str(Path(args.config).with_name("briefing_dimensions.yaml"))
    dimensions = load_simple_yaml(dimensions_path).get("dimensions") or default_dimensions()

    clusters = build_clusters(conn, daily_bucket, dimensions, args.min_score)
    candidates = build_topic_candidates(clusters)
    replace_event_clusters(conn, daily_bucket, clusters)
    replace_topic_candidates(conn, daily_bucket, candidates)
    conn.commit()
    print(json.dumps({"date": daily_bucket, "event_clusters": len(clusters), "topic_candidates": len(candidates)}, ensure_ascii=False, indent=2))


def build_clusters(conn, daily_bucket: str, dimensions: list[dict], min_score: float) -> list[dict]:
    rows = conn.execute(
        """
        SELECT *
        FROM source_items
        WHERE daily_bucket = ?
          AND status = 'new'
          AND COALESCE(title_zh, title, '') <> ''
          AND COALESCE(summary_zh, summary, content, '') <> ''
        ORDER BY collector_rank_score DESC, published_at DESC
        """,
        (daily_bucket,),
    ).fetchall()

    created_at = datetime.now().isoformat()
    clusters = []
    for row in rows:
        title = clean_text(row["title_zh"] or row["title"])
        summary = clean_text(row["summary_zh"] or row["summary"] or row["content"])
        if not title or not summary:
            continue
        if is_synthetic_localized_item(title, summary):
            continue
        duplicate_rows = related_duplicates(conn, row["item_uid"], daily_bucket)
        references = build_reference_items(duplicate_rows)
        source_names = unique([row["source_name"]] + [item["source_name"] for item in duplicate_rows])
        source_urls = unique([row["url"]] + [item["url"] for item in duplicate_rows])
        item_uids = unique([row["item_uid"]] + [item["item_uid"] for item in duplicate_rows])
        tags = merge_json_lists(row["topic_tags_json"], row["entity_tags_json"], row["source_tags_json"])
        platform_hints = parse_json_list(row["platform_hint_json"])
        dimension = choose_dimension(title, summary, tags, dimensions)
        score = calculate_event_score(row, len(source_names), dimension)
        if score < min_score:
            continue
        why = make_why_it_matters(row, dimension, len(source_names))
        cluster_uid = "evt_" + short_hash(f"{daily_bucket}:{row['item_uid']}")
        cluster = {
                "cluster_uid": cluster_uid,
                "daily_bucket": daily_bucket,
                "primary_item_uid": row["item_uid"],
                "title": title,
                "dimension_id": dimension["id"],
                "dimension_label": dimension["label"],
                "dimension_icon": dimension.get("icon"),
                "summary": summary,
                "why_it_matters": why,
                "item_uids_json": json.dumps(item_uids, ensure_ascii=False),
                "reference_items_json": json.dumps(references, ensure_ascii=False),
                "source_names_json": json.dumps(source_names, ensure_ascii=False),
                "source_urls_json": json.dumps(source_urls[:5], ensure_ascii=False),
                "source_count": len(source_names),
                "cross_source_count": len(source_names),
                "cluster_score": score,
                "rank": 0,
                "display_mode": "primary_with_references",
                "tags_json": json.dumps(tags, ensure_ascii=False),
                "platform_hints_json": json.dumps(platform_hints, ensure_ascii=False),
                "created_at": created_at,
                "updated_at": created_at,
            }
        clusters.append(cluster)
    clusters.sort(key=lambda item: item["cluster_score"], reverse=True)
    for index, cluster in enumerate(clusters, start=1):
        cluster["rank"] = index
    return clusters


def related_duplicates(conn, item_uid: str, daily_bucket: str) -> list:
    return conn.execute(
        """
        SELECT si.*
        FROM item_duplicates d
        JOIN source_items si ON si.item_uid = d.item_uid
        WHERE d.duplicate_of_uid = ?
          AND si.daily_bucket = ?
          AND si.status IN ('duplicate_today', 'duplicate_recent')
        ORDER BY si.source_priority DESC, si.published_at DESC
        """,
        (item_uid, daily_bucket),
    ).fetchall()


def build_reference_items(rows) -> list[dict]:
    references = []
    for row in rows:
        references.append(
            {
                "item_uid": row["item_uid"],
                "title": row["title_zh"] or row["title"],
                "source_name": row["source_name"],
                "url": row["url"],
                "published_at": row["published_at"],
                "status": row["status"],
            }
        )
    return references


def choose_dimension(title: str, summary: str, tags: list[str], dimensions: list[dict]) -> dict:
    text = f"{title} {summary} {' '.join(tags)}".lower()
    priority_rules = [
        ("funding", ["融资", "估值", "ipo", "收购", "valuation", "raises", "funding"]),
        ("ai_coding", ["claude code", "codex", "mcp", "agent", "编程", "开发者"]),
        ("policy", ["政策", "监管", "高考", "禁售", "regulation", "policy"]),
    ]
    for dimension_id, keywords in priority_rules:
        if any(keyword in text for keyword in keywords):
            match = next((dimension for dimension in dimensions if dimension.get("id") == dimension_id), None)
            if match:
                return match
    best = None
    best_score = -1.0
    for dimension in dimensions:
        score = 0.0
        for keyword in dimension.get("keywords", []):
            if str(keyword).lower() in text:
                score += 1.0
        score *= float(dimension.get("priority") or 1)
        if score > best_score:
            best = dimension
            best_score = score
    return best or {"id": "industry", "label": "行业动态", "icon": "🟤", "priority": 1.0}


def calculate_event_score(row, source_count: int, dimension: dict) -> float:
    text = f"{row['title_zh'] or row['title']} {row['summary_zh'] or row['summary'] or ''}".lower()
    collector = float(row["collector_rank_score"] or 0)
    reliability = float(row["source_reliability"] or 0.5)
    priority = min(float(row["source_priority"] or 1) / 2, 1)
    cross_source = min(source_count / 3, 1)
    freshness = float(row["freshness_score"] or 0.5)
    dimension_weight = float(dimension.get("priority") or 1)
    impact = calculate_impact_score(text, dimension.get("id"))
    penalty = calculate_quality_penalty(text)
    if row["status"] == "duplicate_recent":
        penalty += 0.08
    score = (
        collector * 0.20
        + impact * 0.25
        + reliability * 0.15
        + priority * 0.10
        + cross_source * 0.20
        + freshness * 0.05
        + min(dimension_weight / 1.5, 1) * 0.05
        - penalty
    )
    return round(max(score, 0), 4)


def calculate_impact_score(text: str, dimension_id: str | None) -> float:
    score = 0.25
    strong_terms = [
        "融资",
        "估值",
        "ipo",
        "发布",
        "上线",
        "claude opus",
        "gpt",
        "openai",
        "anthropic",
        "google",
        "agent",
        "mcp",
        "监管",
        "政策",
        "benchmark",
        "论文",
    ]
    for term in strong_terms:
        if term in text:
            score += 0.08
    if dimension_id in {"funding", "model", "ai_coding", "policy"}:
        score += 0.12
    return min(score, 1.0)


def calculate_quality_penalty(text: str) -> float:
    penalty = 0.0
    weak_patterns = [
        "分享 ai 行业动态",
        "这条信息提到",
        "这条信息讨论",
        "check、",
        "futures：",
        "gm",
    ]
    if any(pattern in text for pattern in weak_patterns):
        penalty += 0.18
    if len(text) < 35:
        penalty += 0.10
    if any(term in text for term in ["torch.profiler", "初学者指南", "datasette", "llm-anthropic"]):
        penalty += 0.06
    if any(term in text for term in ["biodefense", "生物防御"]):
        penalty += 0.04
    return penalty


def make_why_it_matters(row, dimension: dict, source_count: int) -> str:
    label = dimension["label"]
    title = row["title_zh"] or row["title"]
    if label == "投融资":
        return f"这条融资/资本动态会影响 AI 公司竞争格局和算力投入节奏，值得作为商业选题重点跟进。"
    if label in {"大模型", "AI编程/Agent"}:
        return f"这条动态关系到模型能力、开发者工作流或 Agent 落地，是判断 AI 产品演进方向的重要信号。"
    if label == "政策监管":
        return f"这条动态反映 AI 治理正在进入具体场景，对平台运营、内容生产和产品合规都有参考价值。"
    if label == "技术突破":
        return f"这条技术进展可能改变后续产品能力或研究方向，适合沉淀为深度解释型选题。"
    if source_count > 1:
        return f"多个来源同时覆盖，说明该事件具备较高行业关注度，适合作为今日重点素材。"
    return f"这条信息提供了一个明确的新变化，可作为后续选题池的候选素材。"


def build_topic_candidates(clusters: list[dict]) -> list[dict]:
    now = datetime.now().isoformat()
    candidates = []
    for cluster in clusters:
        platform_fit = infer_platform_fit(cluster)
        recommended_platforms = recommend_platforms(platform_fit)
        topic_type = infer_topic_type(cluster)
        target_audience = infer_target_audience(cluster)
        title = make_topic_title(cluster, topic_type)
        source_title = cluster["title"]
        angle = make_topic_angle(cluster, topic_type)
        core_question = make_core_question(cluster, topic_type)
        score_breakdown = calculate_topic_score_breakdown(cluster, platform_fit, target_audience)
        topic_score = round(sum(score_breakdown.values()), 4)
        candidates.append(
            {
                "candidate_uid": "topic_" + short_hash(cluster["cluster_uid"]),
                "cluster_uid": cluster["cluster_uid"],
                "daily_bucket": cluster["daily_bucket"],
                "title": title,
                "source_title": source_title,
                "angle": angle,
                "topic_type": topic_type,
                "core_question": core_question,
                "target_audience_json": json.dumps(target_audience, ensure_ascii=False),
                "dimension_id": cluster["dimension_id"],
                "topic_score": topic_score,
                "score_breakdown_json": json.dumps(score_breakdown, ensure_ascii=False),
                "platform_fit_json": json.dumps(platform_fit, ensure_ascii=False),
                "recommended_platforms_json": json.dumps(recommended_platforms, ensure_ascii=False),
                "source_item_uid": cluster.get("primary_item_uid"),
                "reference_items_json": cluster.get("reference_items_json") or "[]",
                "reason": make_topic_reason(cluster, topic_type, recommended_platforms),
                "status": "candidate",
                "processing_version": "topic-candidates-v2",
                "created_at": now,
                "updated_at": now,
            }
        )
    return candidates


def infer_platform_fit(cluster: dict) -> dict:
    dimension = cluster["dimension_id"]
    fit = {"wechat": 0.7, "x": 0.5, "xiaohongshu": 0.4, "douyin": 0.4, "bilibili": 0.5}
    if dimension in {"model", "ai_coding", "tech", "funding", "policy"}:
        fit["wechat"] = 0.9
        fit["x"] = 0.7
    if dimension in {"product", "hardware"}:
        fit["xiaohongshu"] = 0.7
        fit["douyin"] = 0.7
        fit["bilibili"] = 0.7
    return fit


def recommend_platforms(platform_fit: dict) -> list[str]:
    return [
        platform
        for platform, _score in sorted(platform_fit.items(), key=lambda item: item[1], reverse=True)
        if _score >= 0.65
    ][:3]


def infer_topic_type(cluster: dict) -> str:
    dimension = cluster["dimension_id"]
    text = f"{cluster['title']} {cluster.get('summary') or ''}".lower()
    if dimension in {"ai_coding", "tech"} or any(term in text for term in ["api", "github", "代码", "开发者", "agent"]):
        return "analysis"
    if dimension in {"product", "hardware"}:
        return "case_study"
    if dimension == "policy":
        return "explainer"
    if dimension == "funding":
        return "opinion"
    return "news_analysis"


def infer_target_audience(cluster: dict) -> list[str]:
    text = f"{cluster['title']} {cluster.get('summary') or ''} {cluster.get('dimension_label') or ''}".lower()
    audience = []
    if any(term in text for term in ["api", "github", "代码", "开发者", "agent", "mcp", "codex", "claude code"]):
        audience.extend(["开发者", "AI 产品经理"])
    if any(term in text for term in ["融资", "估值", "ipo", "收购", "商业"]):
        audience.extend(["创业者", "投资人", "AI 从业者"])
    if any(term in text for term in ["政策", "监管", "合规", "高考"]):
        audience.extend(["产品负责人", "运营负责人", "内容创作者"])
    if any(term in text for term in ["视频", "图像", "小红书", "创作", "生成"]):
        audience.extend(["内容创作者", "设计师"])
    if not audience:
        audience = ["AI 从业者", "内容创作者"]
    return unique(audience)


def make_topic_title(cluster: dict, topic_type: str) -> str:
    title = clean_text(cluster["title"], 80)
    dimension = cluster["dimension_id"]
    if topic_type == "analysis":
        return f"{title}：这对开发者意味着什么？"
    if topic_type == "case_study":
        return f"从{title}看 AI 产品落地机会"
    if topic_type == "explainer":
        return f"{title}背后的规则变化是什么？"
    if topic_type == "opinion" or dimension == "funding":
        return f"{title}释放了什么行业信号？"
    return f"{title}为什么值得关注？"


def make_core_question(cluster: dict, topic_type: str) -> str:
    title = clean_text(cluster["title"], 80)
    if topic_type == "analysis":
        return f"{title}会如何改变开发者、产品团队或企业部署 AI 的方式？"
    if topic_type == "case_study":
        return f"{title}体现了什么产品机会，普通创作者或团队能学到什么？"
    if topic_type == "explainer":
        return f"{title}涉及哪些新规则、新边界或新风险？"
    if topic_type == "opinion":
        return f"{title}说明 AI 行业的资源、入口或竞争格局正在发生什么变化？"
    return f"{title}的核心变化是什么，为什么今天需要关注？"


def calculate_topic_score_breakdown(cluster: dict, platform_fit: dict, target_audience: list[str]) -> dict:
    event_value = float(cluster["cluster_score"] or 0) * 0.35
    platform_value = (max(platform_fit.values()) if platform_fit else 0) * 0.20
    audience_value = min(len(target_audience) / 3, 1) * 0.15
    source_value = min(float(cluster["source_count"] or 1) / 3, 1) * 0.15
    freshness_value = 0.10
    reference_value = 0.05 if parse_json_list(cluster.get("reference_items_json")) else 0
    return {
        "event_value": round(event_value, 4),
        "platform_fit": round(platform_value, 4),
        "audience_fit": round(audience_value, 4),
        "source_support": round(source_value, 4),
        "freshness": round(freshness_value, 4),
        "references": round(reference_value, 4),
    }


def make_topic_reason(cluster: dict, topic_type: str, platforms: list[str]) -> str:
    platform_text = "、".join(platforms) if platforms else "多平台"
    return f"{cluster['why_it_matters']} 适合做{topic_type}类选题，优先分发到{platform_text}。"


def make_topic_angle(cluster: dict, topic_type: str) -> str:
    label = cluster["dimension_label"]
    if topic_type == "analysis":
        return "从开发者工作流、产品入口和企业落地角度展开分析"
    if topic_type == "case_study":
        return "拆解产品设计、场景落地和可复用方法"
    if topic_type == "explainer":
        return "解释规则变化、影响对象和后续风险"
    if topic_type == "opinion":
        return "从行业竞争格局和资源流向提出判断"
    if label == "投融资":
        return "从资本流向判断 AI 公司竞争格局变化"
    if label == "AI编程/Agent":
        return "从开发者工作流角度解释 Agent 能力演进"
    if label == "政策监管":
        return "从具体场景看 AI 合规边界如何变化"
    return f"围绕{label}解释这条动态的行业意义"


def clean_text(value: str | None, max_length: int = 260) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip("，,；;：: ") + "…"


def is_synthetic_localized_item(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    synthetic_patterns = [
        "分享 AI 行业动态",
        "更新开发者工具和编程能力",
        "推进智能体和自动化工作流",
        "发布新产品或功能",
        "发布研究或技术进展",
        "调整产品体验和商业策略",
        "这条信息提到",
        "这条信息讨论",
        "提到分享",
        "提到推进",
        "发布或推出发布",
    ]
    if any(pattern in text for pattern in synthetic_patterns):
        return True
    if re.match(r"^[A-Za-z]+、[A-Za-z]+：", title):
        return True
    return False


def unique(values: list[str | None]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def parse_json_list(value: str | None) -> list:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def merge_json_lists(*values: str | None) -> list[str]:
    merged = []
    for value in values:
        merged.extend(str(item) for item in parse_json_list(value))
    return unique(merged)


def short_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


if __name__ == "__main__":
    main()
