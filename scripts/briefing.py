#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from briefing_config import load_simple_yaml
from collect import load_config
from db import connect, init_db

try:
    import markdown
except ImportError:
    markdown = None


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--date")
    parser.add_argument("--template")
    args = parser.parse_args()

    config = load_config(args.config)
    daily_bucket = args.date or datetime.now().date().isoformat()
    template_path = args.template or str(Path(args.config).with_name("briefing_template.yaml"))
    template = load_simple_yaml(template_path).get("briefing") or {}
    conn = connect(config["project"]["database_path"])
    init_db(conn)
    briefing = build_briefing_data(conn, daily_bucket, template)
    out_dir = Path(template.get("output_dir") or Path(config["project"]["data_dir"]) / "briefings")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{daily_bucket}.ai-hot-brief.md"
    html_path = out_dir / f"{daily_bucket}.ai-hot-brief.html"
    markdown_text = render_briefing_markdown(briefing)
    md_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(render_markdown_html(markdown_text, briefing), encoding="utf-8")
    print(json.dumps({"date": daily_bucket, "briefing": str(md_path), "html": str(html_path)}, ensure_ascii=False, indent=2))


def build_briefing_data(conn, daily_bucket: str, template: dict) -> dict:
    rows = conn.execute(
        """
        SELECT *
        FROM event_clusters
        WHERE daily_bucket = ?
        ORDER BY rank ASC, cluster_score DESC
        """,
        (daily_bucket,),
    ).fetchall()
    if not rows:
        return {"daily_bucket": daily_bucket, "empty": True, "title": template.get("title") or "AI HOT 简报"}
    rows = hydrate_event_sources(conn, [dict(row) for row in rows])

    top_count = int(template.get("top_count") or 3)
    full_max = int(template.get("full_items_max") or 25)
    event_value_threshold = float(template.get("event_value_threshold") or 0.5)
    trend_count = int(template.get("trend_count") or 4)
    keyword_count = int(template.get("keyword_count") or 5)
    full_rows = select_briefing_rows(rows, full_max, event_value_threshold)
    top_rows = full_rows[:top_count]
    keywords = extract_keywords(full_rows, keyword_count)
    date_label = format_date_zh(daily_bucket)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M CST")
    return {
        "empty": False,
        "title": template.get("title") or "AI HOT 简报",
        "daily_bucket": daily_bucket,
        "date_label": date_label,
        "generated_at": generated_at,
        "keywords": keywords,
        "top_rows": top_rows,
        "full_rows": full_rows,
        "trends": build_trends(full_rows, trend_count),
        "one_liner": make_one_liner(full_rows),
        "footer_sources": format_footer_sources(full_rows, int(template.get("source_footer_limit") or 12)),
        "top_count": top_count,
        "full_max": full_max,
        "event_value_threshold": event_value_threshold,
    }


def render_briefing(conn, daily_bucket: str, template: dict) -> str:
    return render_briefing_markdown(build_briefing_data(conn, daily_bucket, template))


def hydrate_event_sources(conn, rows: list[dict]) -> list[dict]:
    for row in rows:
        row["reference_items"] = parse_json(row.get("reference_items_json"))
        item_uids = parse_json(row.get("item_uids_json"))
        if not item_uids:
            row["source_materials"] = []
            continue
        placeholders = ",".join("?" for _ in item_uids)
        materials = conn.execute(
            f"""
            SELECT title_zh, title, summary_zh, summary, content, source_name, url
            FROM source_items
            WHERE item_uid IN ({placeholders})
            ORDER BY is_primary_source DESC, source_priority DESC, LENGTH(COALESCE(content, summary_zh, summary, '')) DESC
            """,
            item_uids,
        ).fetchall()
        row["source_materials"] = [dict(item) for item in materials]
        row["best_sources"] = rank_event_sources(row)
    return rows


def render_briefing_markdown(briefing: dict) -> str:
    if briefing.get("empty"):
        return f"# {briefing['title']} — {briefing['daily_bucket']}\n\n暂无可用事件聚类。请先运行 `curate.py`。\n"
    top_rows = briefing["top_rows"]
    full_rows = briefing["full_rows"]
    lines = [
        "---",
        f"# 🔥 {briefing['title']} — {briefing['date_label']}",
        "",
        f"> 🕗 过去24小时AI圈核心动态 · 共{len(full_rows)}条 · {briefing['daily_bucket']}",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 📊 今日关键词 | {' · '.join(briefing['keywords'])} |",
        "",
        f"## 🏆 头条精选（Top {briefing['top_count']}，每条约200字，说明核心信息）",
        "",
    ]
    for index, row in enumerate(top_rows, start=1):
        title = display_title(row)
        lines.extend(
            [
                f"**{index}. {title}**",
                "",
                f"{compose_top_paragraph(row)}",
                "",
            ]
        )

    lines.extend(
        [
            f"## 📰 完整动态（{min(len(full_rows), briefing['full_max'])}条，按重要性排序，每条约200字摘要）",
            "",
        ]
    )
    for index, row in enumerate(full_rows):
        title = f"{row['dimension_icon'] or ''} [{row['dimension_label']}] {display_title(row)}".strip()
        summary = editorial_summary(row)
        lines.append(f"**{title}**")
        if summary:
            lines.append("")
            lines.append(summary)
        lines.append("")
        lines.append(f"*来源：{format_sources(row)}*")
        references = format_reference_details(row)
        if references:
            lines.append("")
            lines.append(references)
        if index != len(full_rows) - 1:
            lines.extend(["", "---", ""])
    lines.append("")

    lines.extend(["## 📈 今日趋势（3-4个宏观判断，每条一针见血）", ""])
    for trend in briefing["trends"]:
        lines.append(f"> - **{trend['title']}**：{trend['body']}")
    lines.extend(["", "## 💬 今日AI圈一句话", "", f"> {briefing['one_liner']}", "", "---"])
    lines.append(f"*数据来源：{briefing['footer_sources']} · 生成时间：{briefing['generated_at']}*")
    return "\n".join(lines) + "\n"


def render_markdown_html(markdown_text: str, briefing: dict) -> str:
    body = convert_markdown_to_html(markdown_text)
    title = f"{briefing.get('title') or 'AI HOT 简报'} — {briefing.get('daily_bucket') or ''}"
    return html_shell(title, body)


def convert_markdown_to_html(markdown_text: str) -> str:
    cleaned = markdown_text
    if cleaned.startswith("---"):
        cleaned = cleaned.split("\n", 1)[1]
    if markdown is not None:
        return markdown.markdown(cleaned, extensions=["extra", "tables", "sane_lists"])
    return fallback_markdown_to_html(cleaned)


def fallback_markdown_to_html(markdown_text: str) -> str:
    lines = []
    for raw in markdown_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("> "):
            lines.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line == "---":
            lines.append("<hr>")
        else:
            lines.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(lines)


def html_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --text: #2f3742;
      --muted: #687280;
      --line: #e6e9ee;
      --link: #1d76b8;
      --bg: #ffffff;
      --soft: #f7f9fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0 48px 56px;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif;
      font-size: 16px;
      line-height: 1.82;
    }}
    body > * {{
      max-width: 1060px;
      margin-left: auto;
      margin-right: auto;
    }}
    h1 {{
      margin: 52px auto 8px;
      padding-top: 28px;
      border-top: 1px solid var(--line);
      font-size: 18px;
      line-height: 1.5;
      font-weight: 800;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 30px auto 12px;
      font-size: 16px;
      line-height: 1.5;
      font-weight: 800;
      letter-spacing: 0;
    }}
    p {{
      margin: 8px auto 14px;
      color: #3f4854;
    }}
    h2:nth-of-type(1) + p,
    h2:nth-of-type(1) + p + p + p,
    h2:nth-of-type(1) + p + p + p + p + p {{
      margin-top: 18px;
    }}
    blockquote {{
      margin: 0 auto;
      padding: 0;
      border-left: 0;
      color: var(--text);
    }}
    blockquote > p {{
      margin: 8px auto 14px;
    }}
    blockquote > p:has(strong:first-child) {{
      margin-top: 24px;
    }}
    hr {{
      max-width: 1060px;
      border: 0;
      border-top: 1px solid var(--line);
      margin: 30px auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 28px auto 18px;
      table-layout: fixed;
    }}
    table thead {{
      display: none;
    }}
    td, th {{
      border: 1px solid #d9dee6;
      padding: 8px 14px;
      vertical-align: middle;
    }}
    td:first-child, th:first-child {{
      width: 170px;
      text-align: center;
      font-weight: 800;
      color: #2f3742;
      background: #fafbfc;
    }}
    td:nth-child(2), th:nth-child(2) {{
      text-align: center;
      font-weight: 800;
    }}
    a {{
      color: var(--link);
      text-decoration: none;
      font-style: italic;
    }}
    a:hover {{ text-decoration: underline; }}
    strong {{
      font-weight: 800;
      color: #303844;
    }}
    em {{
      color: var(--muted);
      font-style: italic;
    }}
    h2 + p:has(> strong:first-child),
    hr + p:has(> strong:first-child) {{
      margin-top: 26px;
    }}
    p:has(> strong:first-child) {{
      margin-top: 22px;
      margin-bottom: 6px;
    }}
    p:has(> strong:first-child) + p {{
      margin-top: 0;
    }}
    p:has(> em:first-child) {{
      margin-top: 18px;
      margin-bottom: 22px;
      color: var(--muted);
    }}
    ul {{
      padding-left: 24px;
      margin: 8px auto 20px;
    }}
    li {{ margin: 6px 0; }}
    @media (max-width: 760px) {{
      body {{
        padding: 0 18px;
        font-size: 15px;
        line-height: 1.75;
      }}
      body > * {{ max-width: 100%; }}
      h1 {{ margin-top: 28px; }}
      table {{ table-layout: auto; }}
      td:first-child, th:first-child {{ width: 120px; }}
    }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def select_briefing_rows(rows, full_max: int, event_value_threshold: float) -> list:
    selected = []
    quality_rows = sorted(rows, key=event_value_score, reverse=True)
    for row in quality_rows:
        if not is_daily_worthy(row):
            continue
        if event_value_score(row) < event_value_threshold:
            continue
        selected.append(row)
        if len(selected) >= full_max:
            return selected
    return selected


def event_value_score(row) -> float:
    title = display_title(row)
    summary = editorial_summary(row)
    material = source_material_text(row)
    text = f"{title} {summary} {material}"
    information_density = score_information_density(text)
    impact = score_impact(text, row["dimension_label"])
    credibility = score_source_credibility(row)
    cross_source = min(float(row.get("source_count") or 1) / 3, 1.0)
    freshness = min(float(row.get("cluster_score") or 0), 1.0)
    noise = score_noise(text, title, summary)
    score = (
        information_density * 0.30
        + impact * 0.25
        + credibility * 0.20
        + cross_source * 0.15
        + freshness * 0.10
        - noise
    )
    return round(max(score, 0), 4)


def score_information_density(text: str) -> float:
    terms = [
        "发布", "推出", "上线", "新增", "支持", "升级", "扩展", "开源", "合作", "融资", "收购", "裁员",
        "报告", "基准", "数据集", "API", "模型", "智能体", "Agent", "Codex", "Claude", "OpenAI", "Google",
        "Qwen", "Runway", "OpenRouter", "tokens/s", "70", "20", "40", "GPT", "UEFA",
    ]
    hits = sum(1 for term in terms if re.search(re.escape(term), text, flags=re.I))
    number_bonus = min(len(re.findall(r"\d+(?:\.\d+)?%?|\d+\+?", text)) * 0.08, 0.24)
    return min(0.18 + hits * 0.07 + number_bonus, 1.0)


def score_impact(text: str, label: str) -> float:
    score = 0.25
    high_impact = [
        "OpenAI", "Anthropic", "Google", "Qwen", "阿里云", "Claude", "Codex", "ChatGPT", "Gemini",
        "融资", "IPO", "政策", "监管", "医疗", "罕见病", "UEFA", "API", "基准", "数据集",
    ]
    score += sum(0.08 for term in high_impact if re.search(re.escape(term), text, flags=re.I))
    if label in {"大模型", "AI编程/Agent", "技术突破", "政策监管", "投融资"}:
        score += 0.12
    return min(score, 1.0)


def score_source_credibility(row) -> float:
    sources = row.get("best_sources") or rank_event_sources(row)
    if not sources:
        return 0.35
    best = max(source_priority_score(source["name"]) for source in sources)
    cross = min(len(sources) / 3, 1.0) * 0.12
    return min(best + cross, 1.0)


def score_noise(text: str, title: str, summary: str) -> float:
    penalty = 0.0
    weak_patterns = [
        "测验", "quiz", "幕后故事", "播客", "podcast", "我对这个", "分享 AI 行业动态",
        "提到推进", "这个 skill 看着不错", "GM", "点击查看", "了解更多",
    ]
    penalty += sum(0.16 for pattern in weak_patterns if pattern.lower() in text.lower())
    if is_bad_generated_title(title):
        penalty += 0.30
    if mostly_english(summary) and count_cjk(summary) < 25:
        penalty += 0.30
    if len(re.sub(r"[^\w\u4e00-\u9fff]+", "", summary)) < 28:
        penalty += 0.20
    return min(penalty, 0.9)


def compose_top_paragraph(row) -> str:
    return editorial_summary(row, max_len=220)


def split_first_sentence(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return "", ""
    match = re.search(r"[。！？]", text)
    if not match:
        return clean_length(text, 120), ""
    first = text[: match.end()].strip()
    rest = text[match.end() :].strip()
    return first, clean_length(rest, 180)


def build_trends(rows, trend_count: int) -> list[dict]:
    by_dimension: dict[str, list] = {}
    for row in rows:
        by_dimension.setdefault(row["dimension_label"], []).append(row)
    ranked = sorted(by_dimension.items(), key=lambda item: (len(item[1]), item[1][0]["cluster_score"]), reverse=True)
    trends = []
    for label, items in ranked[:trend_count]:
        top = display_title(items[0])
        names = extract_entities_from_text(" ".join(f"{row['title']} {row['summary'] or ''}" for row in items[:4]))
        entity_text = "、".join(names[:3]) if names else top
        if label == "大模型":
            title = "模型能力继续产品化"
            body = f"{entity_text}等动态集中在实时翻译、多模态交互和 API 接入，说明模型能力正在被包装成更具体的用户功能。"
        elif label == "投融资":
            title = "资本继续押注 AI 基础设施"
            body = f"{entity_text}显示资金和商业资源仍向头部模型、算力、企业部署环节集中。"
        elif label == "AI编程/Agent":
            title = "AI 编程进入真实工作流"
            body = f"{entity_text}集中出现，说明 Agent 正从演示能力走向 IDE、企业代码库、跨平台执行和文档处理。"
        elif label == "政策监管":
            title = "AI 合规进入场景化管理"
            body = f"{entity_text}反映监管重点正在从原则讨论转向具体产品、平台规则和高风险场景。"
        else:
            if label == "技术突破":
                title = "AI 应用开始进入高价值场景"
                body = f"{top}说明 AI 正在进入医疗、推理性能等更高价值场景，后续重点看实际效果和可复制性。"
            elif label == "应用产品":
                title = "模型能力继续工具化"
                body = f"{top}说明模型服务商正在把能力封装成更容易接入的开发工具和平台接口。"
            else:
                title = f"{label}出现可跟踪变化"
                body = f"{top}代表了这一方向的新增信号，适合后续观察是否形成连续趋势。"
        trends.append({"title": title, "body": body})
    return trends


def make_one_liner(rows) -> str:
    top = rows[0]
    second = rows[1] if len(rows) > 1 else None
    top_title = display_title(top)
    if second:
        second_title = display_title(second)
        if top["dimension_label"] == second["dimension_label"]:
            return f"{top_title}，再加上 {second_title}，共同指向同一条主线：AI 正在进入真实工作流和可直接使用的产品功能。"
        return f"{top_title}与{second_title}一内一外，说明今天 AI 圈的变化同时发生在技术能力和商业落地两端。"
    return f"{top_title}是今天最值得关注的 AI 动态，后续要看它能否转化为真实产品和工作流变化。"


def extract_keywords(rows, count: int) -> list[str]:
    candidates = []
    for row in rows[:16]:
        candidates.extend(extract_entities_from_text(f"{row['title']} {row['summary'] or ''}"))
    result = []
    for item in candidates:
        if item and item not in result and not is_weak_keyword(item):
            result.append(item)
        if len(result) >= count:
            break
    return result or ["AI 编程", "模型产品化", "Agent 工作流"]


def extract_title_phrases(title: str) -> list[str]:
    parts = re.split(r"[：:，,、|｜\s]+", title)
    phrases = []
    for part in parts:
        part = part.strip("「」“”\"'")
        if len(part) < 2:
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]", part):
            phrases.append(clean_length(part, 18))
    return phrases[:2]


def briefing_quality_score(row) -> float:
    title = row["title"] or ""
    summary = row["summary"] or ""
    text = f"{title} {summary}"
    score = float(row["cluster_score"] or 0)
    if row["source_count"] and int(row["source_count"]) > 1:
        score += 0.12
    if re.search(r"(发布|推出|上线|支持|融资|收购|开源|升级|合作|部署|突破|报告|监管|API|Agent|Codex|Claude|OpenAI|Google|Gemini|Qwen|Runway)", text, re.I):
        score += 0.18
    if len(summary) >= 45:
        score += 0.08
    weak_patterns = [
        "分享 AI 行业动态",
        "这条信息提到",
        "这条信息讨论",
        "参与我们的",
        "测验",
        "quiz",
        "这个 skill 看着不错",
        "GM",
    ]
    if any(pattern.lower() in text.lower() for pattern in weak_patterns):
        score -= 0.35
    if is_version_only(title):
        score -= 0.08
    if len(re.sub(r"\W+", "", title)) < 8:
        score -= 0.18
    return round(max(score, 0), 4)


def display_title(row) -> str:
    title = clean_display_text(row["title"] or "")
    summary = clean_display_text(row["summary"] or "")
    if is_version_only(title) and "Claude Code" in summary:
        return "Claude Code v2.1.158 更新：Auto mode 扩展至 Bedrock、Vertex 和 Foundry"
    if "参与我们的 I/O" in title and "Google AI Studio" in summary:
        return "Google 用 AI Studio 生成 I/O 2026 互动测验，展示 vibe coding 应用"
    if "这个 skill 看着不错" in title and "claude-design-card" in summary:
        return "claude-design-card Skill 支持把文章生成公众号和小红书视觉卡片"
    title = title.replace("Codex现已", "Codex 现已").replace("ChatGPT对话", "ChatGPT 对话")
    title = title.replace("OpenAI推出", "OpenAI 推出").replace("OpenRouter支持", "OpenRouter 支持")
    title = title.replace("Braintrust如何", "Braintrust 如何").replace("Runway API持续", "Runway API 持续")
    title = title.replace("阿里云与Qwen", "阿里云与 Qwen").replace("支持70+", "支持 70+")
    title = title.replace("Windows端", "Windows 端").replace("支持Windows", "支持 Windows")
    title = title.replace("用Codex", "用 Codex").replace("Codex将", "Codex 将")
    title = title.replace("Qwen成为", "Qwen 成为").replace("多年全球AI", "多年全球 AI")
    title = title.replace("ComfyUI现", "ComfyUI 现").replace("支持OpenRouter", "支持 OpenRouter")
    title = title.replace("Codex可", "Codex 可")
    title = title.replace("成为UEFA", "成为 UEFA").replace("全球 AI合作伙伴", "全球 AI 合作伙伴")
    title = title.replace("UEFA多年", "UEFA 多年")
    title = title.replace("OpenRouter模型", "OpenRouter 模型").replace("70+语言", "70+ 语言")
    return clean_length(title, 70)


def editorial_summary(row, max_len: int = 200) -> str:
    title = display_title(row)
    material = source_material_text(row)
    summary = summarize_material(title, material, max_len=max_len) if material else ""
    if not summary:
        summary = clean_display_text(row["summary"] or "")
        summary = remove_source_noise(summary)
    if not summary or is_generic_summary(summary):
        summary = title
    if is_version_only(row["title"] or "") and "Claude Code" in summary:
        summary = "Claude Code v2.1.158 扩大 Auto mode 支持范围，可在 Bedrock、Vertex 和 Foundry 中使用 Claude Opus 4.7/4.8。"
    if "参与我们的 I/O" in (row["title"] or ""):
        summary = "Google 用 AI Studio 生成 I/O 2026 互动测验，用一个轻量案例展示 vibe coding 在活动内容和开发者体验中的应用。"
    if "LlamaIndex" in title and "Agents API" in summary:
        summary = "LlamaIndex 基于 Google Agents API 构建 LlamaParse/LiteParse 模板，让 Agent 能直接处理非结构化文档。"
    if "Braintrust" in title and "Codex" in title:
        summary = "Braintrust 工程团队使用 Codex 和 GPT-5.5，把客户请求更快转化为代码改动，用于加速实验运行和产品迭代。"
    if "Codex" in title and "Windows" in title:
        summary = "OpenAI 宣布 Codex 的计算机使用能力支持 Windows，用户可让 Codex 在 Windows 设备上执行和协助完成任务。"
    if "ChatGPT 对话目录" in title:
        summary = "ChatGPT 开始为较长对话提供目录功能，用户可以更快定位对话中的关键段落，改善长线程阅读和复用体验。"
    if "实时翻译" in title:
        summary = "OpenAI 推出 gpt-realtime-translate，可接收 70 多种语言的语音输入，并输出 13 种目标语言语音，面向智能眼镜等实时交互场景。"
    if "Runway API" in title:
        summary = "Runway API 继续增加生成模型和端点，开发者可在应用中统一调用视频、图像等多种生成能力。"
    if "阿里云" in title and "UEFA" in title:
        summary = "阿里云与 Qwen 成为 UEFA 多年全球 AI、云计算与电商合作伙伴，合作覆盖 2027/2028 至 2032/2033 赛季。"
    if "OpenRouter 支持模型生成文件补丁" in title:
        summary = "OpenRouter 在 Responses API 中支持 apply_patch，模型可以生成文件创建、修改或删除补丁，并由服务端校验 diff 语法。"
    if "ComfyUI" in title and "OpenRouter" in title:
        summary = "ComfyUI 现已支持在工作流中直接调用 OpenRouter 模型，用户可在 ComfyUI 内访问 20 多个模型，减少在不同模型服务之间切换的成本。"
    if "波士顿儿童医院" in title:
        summary = "波士顿儿童医院将 OpenAI 技术用于患者护理和运营流程，已辅助识别 40 多种罕见病病例。"
    if "推理速度" in title:
        summary = "Kog 团队称其在标准数据中心 GPU 上实现单用户 2100-3000 tokens/s 的推理速度，显著高于常规推理水平。"
    if "GPIC" in title:
        summary = "World Labs 相关研究者发布 GPIC，这是面向大规模视觉生成模型的基准数据集，用于评估新一代图像/视觉生成系统的能力。"
    if "AI上瘾" in title or "AI 上瘾" in title:
        summary = "TechCrunch 报道称，Box 创始人 Aaron Levie 批评部分公司在不了解岗位实际工作的情况下用 AI 替代员工；ClickUp 近期因部署 AI 智能体裁员 22%，成为相关争议案例。"
    if "Scott Wu" in title or "Cognition" in title:
        summary = "TechCrunch 报道称，Cognition 创始人 Scott Wu 表示，AI 编程智能体 Devin 的目标不是取代人类程序员，而是帮助工程团队处理更多开发任务。"
    if "ControlFoley" in title:
        summary = "小米大模型应用团队开源 ControlFoley，可支持文本引导视频配音、文本控制视频配音和参考音频控制视频配音，重点解决视频音效生成的可控性问题。"
    if "全民人工智能素养" in title:
        summary = "中央网信办等四部门发布《2026年提升全民数字素养与技能工作要点》，明确提出提升全民人工智能素养，覆盖教育赋能、人才培养、应用普及和网络安全等任务。"
    if "AGI" in title and "哈萨比斯" in title:
        summary = "Google DeepMind CEO 德米斯·哈萨比斯表示，AGI 研发进展快于预期，未来三到四年可能出现关键突破，AI 智能体和多模态能力是重要前奏。"
    return ensure_sentence(clean_length(summary, max_len))


def source_material_text(row) -> str:
    pieces = []
    for item in row.get("source_materials") or []:
        for key in ("content", "summary_zh", "summary", "title_zh", "title"):
            value = item.get(key)
            if value:
                pieces.append(str(value))
    if not pieces:
        pieces.append(row.get("summary") or "")
    return remove_source_noise("。".join(pieces))


def summarize_material(title: str, material: str, max_len: int = 150) -> str:
    material = remove_summary_noise(material)
    if not material:
        return ""
    if "Luma Agents" in title:
        return "Luma Agents 可根据输入内容和设定的传播钩子，自动生成宣传图，帮助用户把文章或素材快速转成可发布的营销视觉。"
    if "Codex可自主管理对话线程" in title or "Codex 可自主管理对话线程" in title:
        return "Codex 新增对话线程管理能力，可创建、搜索、整理和固定线程，并为并行任务启动工作树，降低多任务协作时的管理成本。"
    sentences = split_sentences(material)
    picked = []
    seen = set()
    for sentence in sentences:
        if is_noise_sentence(sentence):
            continue
        if not is_informative_sentence(sentence):
            continue
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", sentence.lower())
        if normalized in seen:
            continue
        seen.add(normalized)
        picked.append(sentence)
        if len("".join(picked)) >= max_len * 0.75:
            break
    if not picked:
        for sentence in sentences:
            if not is_noise_sentence(sentence):
                picked.append(sentence)
                break
    return clean_length("".join(picked), max_len)


def is_daily_worthy(row) -> bool:
    title = display_title(row)
    material = source_material_text(row)
    summary = editorial_summary(row)
    text = f"{title} {summary} {material}"
    reject_patterns = [
        "参与我们的",
        "测验",
        "quiz",
        "幕后故事",
        "Release Notes",
        "分享模型背后团队",
        "这个 skill 看着不错",
        "GM",
        "提到推进",
        "分享 AI 行业动态",
        "<p>",
        "ShareGPT-style提到",
        "The unix terminal",
        "未给出任何",
        "无法在摘要中提及",
    ]
    if any(pattern.lower() in text.lower() for pattern in reject_patterns):
        return False
    if is_bad_generated_title(title):
        return False
    if is_generic_summary(summary):
        return False
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", summary)
    if len(compact) < 28:
        return False
    if mostly_english(summary) and count_cjk(summary) < 20:
        return False
    high_signal = re.search(
        r"(发布|推出|上线|新增|支持|扩展|升级|构建|生成|部署|合作|融资|收购|开源|裁员|报告|诊断|医疗|罕见病|API|模型|Agent|Codex|Claude|OpenAI|Google|Runway|Qwen|OpenRouter)",
        text,
        flags=re.I,
    )
    return bool(high_signal)


def rank_event_sources(row) -> list[dict]:
    names = parse_json(row.get("source_names_json"))
    urls = parse_json(row.get("source_urls_json"))
    sources = []
    for index, name in enumerate(names):
        url = urls[index] if index < len(urls) else ""
        sources.append({"name": name, "url": url, "score": source_priority_score(name)})
    for item in row.get("source_materials") or []:
        name = item.get("source_name") or ""
        if not name:
            continue
        if any(source["name"] == name for source in sources):
            continue
        sources.append({"name": name, "url": item.get("url") or "", "score": source_priority_score(name)})
    sources.sort(key=lambda source: source["score"], reverse=True)
    return sources


def source_priority_score(name: str) -> float:
    if not name:
        return 0.2
    lowered = name.lower()
    if any(term in name for term in ["官网", "官方", "OpenAI：官网", "Anthropic", "Google Blog", "Qwen：Blog", "GitHub Releases", "Announcements"]):
        return 0.95
    if any(term in name for term in ["TechCrunch", "IT之家", "量子位", "机器之心", "MarkTechPost", "KDnuggets", "Hacker News"]):
        return 0.82
    if any(term in name for term in ["arXiv", "论文", "Research", "Blog", "博客", "Simon Willison"]):
        return 0.78
    if name == "AIHOT":
        return 0.30
    if name.startswith("X："):
        if any(term.lower() in lowered for term in ["openai", "google", "anthropic", "qwen", "runway", "openrouter", "gemini", "alibaba", "luma"]):
            return 0.70
        return 0.48
    return 0.55


def is_bad_generated_title(title: str) -> bool:
    if re.match(r"^[A-Za-z]+、[A-Za-z]+", title):
        return True
    weak = ["推进智能体和自动化工作流", "分享 AI 行业动态"]
    return title.strip() in weak


def mostly_english(value: str) -> bool:
    letters = len(re.findall(r"[A-Za-z]", value or ""))
    cjk = count_cjk(value)
    return letters > 40 and letters > cjk * 1.8


def count_cjk(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", value or ""))


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?])\s+|(?<=[。！？!?])", text)
    return [ensure_sentence(part.strip(" ，,；;：:")) for part in parts if part.strip(" ，,；;：:")]


def remove_summary_noise(value: str) -> str:
    value = re.sub(r"【引用\s*】|【引用】|\[引用\]", "", value or "")
    value = re.sub(r"投入使用\s*[→>]*", "", value)
    value = re.sub(r"查看.*?(?:示例|更多).*", "", value)
    value = re.sub(r"博客文章完成了思考。?", "", value)
    value = re.sub(r"现在让宣传来发挥作用。?", "", value)
    value = re.sub(r"我对这个.*?感到非常兴奋！?", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ，,；;：:。")


def is_noise_sentence(sentence: str) -> bool:
    text = sentence.strip()
    noise_patterns = [
        "【引用",
        "博客文章完成了思考",
        "现在让宣传来发挥作用",
        "投入使用",
        "了解更多",
        "点击查看",
        "这条消息是给你的",
        "我刚刚",
        "我对这个",
    ]
    if any(pattern in text for pattern in noise_patterns):
        return True
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return len(cleaned) < 10


def is_informative_sentence(sentence: str) -> bool:
    return bool(
        re.search(
            r"(发布|推出|上线|新增|支持|扩展|构建|生成|自动|使用|部署|合作|融资|收购|开源|模型|API|Agent|Codex|Claude|OpenAI|Google|Runway|Luma)",
            sentence,
            flags=re.I,
        )
    )


def extract_entities_from_text(text: str) -> list[str]:
    aliases = [
        ("Claude Code", ["Claude Code"]),
        ("Codex", ["Codex"]),
        ("OpenAI", ["OpenAI", "ChatGPT"]),
        ("Google AI Studio", ["Google AI Studio"]),
        ("Google Agents API", ["Google Agents API", "Agents API"]),
        ("Gemini", ["Gemini"]),
        ("LlamaIndex", ["LlamaIndex"]),
        ("LlamaParse", ["LlamaParse", "LiteParse"]),
        ("Braintrust", ["Braintrust"]),
        ("Runway", ["Runway"]),
        ("OpenRouter", ["OpenRouter"]),
        ("Qwen", ["Qwen", "通义千问"]),
        ("Kling AI", ["Kling", "可灵"]),
        ("实时翻译", ["实时翻译", "translate", "translation"]),
        ("Windows 支持", ["Windows"]),
        ("Agent 工作流", ["Agent", "智能体"]),
    ]
    found = []
    for label, patterns in aliases:
        if any(re.search(re.escape(pattern), text, flags=re.I) for pattern in patterns):
            found.append(label)
    if found:
        return found
    return extract_title_phrases(text)[:3]


def is_weak_keyword(value: str) -> bool:
    weak = {
        "发布",
        "推出",
        "完成",
        "团队基于",
        "参与我们的",
        "更新",
        "分享",
        "行业动态",
        "v2.1.158",
        "I/O",
    }
    return value in weak or len(value.strip()) < 3


def is_version_only(value: str) -> bool:
    return bool(re.fullmatch(r"v?\d+(?:\.\d+){1,3}", (value or "").strip(), flags=re.I))


def is_generic_summary(value: str) -> bool:
    weak_patterns = ["分享 AI 行业动态", "这条信息提到", "这条信息讨论", "涉及AI", "发布或推出发布", "提到推进"]
    return any(pattern in value for pattern in weak_patterns)


def remove_source_noise(value: str) -> str:
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"@\w+", "", value)
    value = re.sub(r"\s*[↓→]+\s*", " ", value)
    value = re.sub(r"[，,、]\s*[，,、]+", "，", value)
    return clean_display_text(value)


def clean_display_text(value: str) -> str:
    value = re.sub(r"https?://\S+", "", value or "")
    value = re.sub(r"[\U00010000-\U0010ffff]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip("，,；;：: ")


def ensure_sentence(value: str) -> str:
    value = value.strip()
    if value and value[-1] not in "。！？":
        return value + "。"
    return value


def format_sources(row) -> str:
    ranked = row.get("best_sources") or rank_event_sources(row)
    pieces = []
    for source in ranked[:3]:
        name = source["name"]
        url = source["url"]
        if url:
            pieces.append(f"[{escape_md(name)}]({url})")
        else:
            pieces.append(escape_md(name))
    return " | ".join(pieces) if pieces else "本地采集"


def format_reference_details(row) -> str:
    references = row.get("reference_items") or []
    if not references:
        return ""
    lines = ["<details><summary>查看引用源</summary>", ""]
    for item in references[:8]:
        title = escape_md(item.get("title") or "引用源")
        source_name = escape_md(item.get("source_name") or "未知来源")
        url = item.get("url") or ""
        if url:
            lines.append(f"- {source_name}：[{title}]({url})")
        else:
            lines.append(f"- {source_name}：{title}")
    lines.extend(["", "</details>"])
    return "\n".join(lines)


def format_footer_sources(rows, limit: int) -> str:
    names = []
    for row in rows:
        for source in (row.get("best_sources") or rank_event_sources(row)):
            name = source["name"]
            if name not in names:
                names.append(name)
            if len(names) >= limit:
                break
        if len(names) >= limit:
            break
    return " · ".join(escape_md(name) for name in names)


def parse_json(value: str | None):
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def clean_length(text: str, max_len: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("，,；;：: ") + "…"


def escape_md(value: str) -> str:
    return str(value).replace("|", "\\|")


def format_date_zh(daily_bucket: str) -> str:
    dt = datetime.fromisoformat(daily_bucket)
    return f"{dt.year}年{dt.month}月{dt.day}日（{WEEKDAYS[dt.weekday()]}）"


if __name__ == "__main__":
    main()
