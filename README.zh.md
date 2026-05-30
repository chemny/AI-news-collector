# Media Source Collector

面向自媒体创作的信息采集 Skill，支持 AI 资讯采集、原始数据落库、去重、日报生成和选题池生成。

本仓库按跨平台 Skill 结构整理：仓库根目录就是 Skill 根目录，`SKILL.md` 位于根目录。设计目标是兼容 Codex、Claude Code 和 OpenClaw。

## 能做什么

Media Source Collector 会把公开 RSS/API、外部精选信号和 X builder 时间线采集到本地 SQLite。

核心能力：

- 严格采集过去 24 小时内容
- 保存原始 payload
- 生成标准化内容卡片
- 当天去重和近两天去重
- 按质量选择主展示内容
- 把重复/相似内容作为引用源保留
- 生成 AI 日报
- 生成自媒体创作选题池

## 数据结构

SQLite 数据库按流水线拆分：

| 层级 | 表 | 作用 |
|---|---|---|
| 原始采集 | `raw_source_records` | 原样保存外部数据，是 source of truth。 |
| 内容卡片 | `source_items` | 清洗、标准化、生成可用标题和摘要。 |
| 去重关系 | `item_duplicates` | 记录谁重复谁，以及判重证据。 |
| 展示卡 | `event_clusters` | 保留一条主内容，其他来源作为引用链接。 |
| 选题池 | `topic_candidates` | 把信息转成可创作选题。 |
| 运行审计 | `collection_runs` | 记录每次运行窗口、数量、错误和规则版本。 |
| 来源快照 | `sources` | 保存 source 配置快照。 |
| Builder 统计 | `builder_activity_stats` | 统计 X builder 发文量、重复率和建议抓取上限。 |

字段说明见 [`references/sqlite-schema.md`](references/sqlite-schema.md)。

## 安装

把仓库 clone 或复制到你的 agent skills 目录：

```text
~/.agents/skills/media-source-collector
~/.codex/skills/media-source-collector
```

安装可选 Python 依赖：

```bash
pip install -r requirements.txt
```

建议使用 Python 3.11+。

## 快速开始

在仓库根目录运行：

```bash
python3 scripts/workflow.py --config examples/sources.yaml --mode full
```

这个命令会依次执行：

1. 信息采集
2. 标准化
3. 去重
4. 展示卡生成
5. 日报生成
6. 选题池生成

默认输出到 `./data`。

常用命令：

```bash
python3 scripts/collect.py --config examples/sources.yaml --mode daily
python3 scripts/curate.py --config examples/sources.yaml
python3 scripts/briefing.py --config examples/sources.yaml
python3 scripts/report_builder_activity.py --db ./data/media_sources.sqlite --days 7
```

## 配置

从 [`examples/sources.yaml`](examples/sources.yaml) 开始。

示例配置使用相对路径：

```yaml
project:
  data_dir: ./data
  database_path: ./data/media_sources.sqlite
```

来源角色建议：

| 来源 | 角色 |
|---|---|
| `aihot_selected` | 外部精选信号，用于发现和补充。 |
| `news_aggregator` | 本地可控 RSS/Web 来源采集。 |
| `x_builders` | 通过公开 RSS/Nitter 风格端点监控 X builder。 |

AIHOT 是外部精选信号，不是本地 source of truth。长期建议把稳定来源迁移到 `source_registry.yaml`。

## 平台兼容性

静态兼容性检查：

- Codex：支持标准根目录 `SKILL.md`。
- Claude Code：预期可作为根目录 Skill 使用。
- OpenClaw：预期可作为自包含 Skill 目录使用。

当前发布准备阶段只做了 Codex 风格本地执行验证；Claude Code 和 OpenClaw 需要在对应运行环境里再做实测。

## 来源说明

本 Skill 的集成思路和公开来源说明参考了：

- 部分 AIHOT 相关接口、思路和内容引用自 [KKKKhazix/khazix-skills](https://github.com/KKKKhazix/khazix-skills)
- follow-builders
- news aggregator 风格的信息源采集

见 `vendor/*/source-notes.md`。用户不需要额外安装这些上游 skills。

## 限制

- X 采集依赖公开 RSS/Nitter 风格端点，稳定性受实例影响。
- 有些外部服务不提供逐条发布时间，严格 24 小时过滤会跳过这些内容。
- 默认标题/摘要生成是本地保守抽取式，不调用外部模型。
- 默认示例配置不需要 API key。

## License

MIT.
