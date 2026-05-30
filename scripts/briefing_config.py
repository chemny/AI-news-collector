from pathlib import Path


def load_simple_yaml(path: str | None) -> dict:
    if not path:
        return {}
    yaml_path = Path(path)
    if not yaml_path.exists():
        return {}
    return parse_simple_yaml(yaml_path.read_text(encoding="utf-8"))


def parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]
    raw_lines = text.splitlines()

    for index, raw_line in enumerate(raw_lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            value = line[2:].strip()
            if isinstance(parent, list):
                if ":" in value:
                    key, raw_value = value.split(":", 1)
                    node = {key.strip(): parse_scalar(raw_value)}
                    parent.append(node)
                    stack.append((indent, node))
                else:
                    parent.append(parse_scalar(value))
            continue

        if ":" not in line or not isinstance(parent, dict):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            node: object = {}
            for lookahead in raw_lines[index + 1 :]:
                if not lookahead.strip() or lookahead.lstrip().startswith("#"):
                    continue
                next_indent = len(lookahead) - len(lookahead.lstrip(" "))
                if next_indent > indent and lookahead.strip().startswith("- "):
                    node = []
                break
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = parse_scalar(value)
    return root


def parse_scalar(value: str):
    value = value.strip()
    if value in {"", "null", "Null", "NULL"}:
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


def default_dimensions() -> list[dict]:
    return [
        {"id": "model", "label": "大模型", "icon": "🔴", "max_items": 4, "priority": 1.3, "keywords": ["Claude", "GPT", "Gemini", "模型"]},
        {"id": "funding", "label": "投融资", "icon": "🟡", "max_items": 3, "priority": 1.25, "keywords": ["融资", "估值", "IPO", "收购"]},
        {"id": "product", "label": "应用产品", "icon": "🟠", "max_items": 4, "priority": 1.1, "keywords": ["产品", "工具", "launch", "release"]},
        {"id": "tech", "label": "技术突破", "icon": "🔵", "max_items": 4, "priority": 1.15, "keywords": ["论文", "研究", "技术", "benchmark"]},
        {"id": "policy", "label": "政策监管", "icon": "🟢", "max_items": 3, "priority": 1.05, "keywords": ["政策", "监管", "合规", "safety"]},
        {"id": "hardware", "label": "硬件/具身智能", "icon": "⚪", "max_items": 2, "priority": 1.0, "keywords": ["硬件", "机器人", "芯片", "device"]},
        {"id": "ai_coding", "label": "AI编程/Agent", "icon": "🟣", "max_items": 4, "priority": 1.2, "keywords": ["Agent", "Claude Code", "Codex", "MCP", "编程"]},
        {"id": "industry", "label": "行业动态", "icon": "🟤", "max_items": 4, "priority": 1.0, "keywords": ["行业", "市场", "startup", "enterprise"]},
    ]
