#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from adapters.x_builder_monitor import parse_simple_profiles_yaml

try:
    import yaml
except ImportError:
    yaml = None


def load_profiles(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        data = yaml.safe_load(text) if yaml else parse_simple_profiles_yaml(text)
    else:
        data = json.loads(text)
    if isinstance(data, list):
        return {"version": 1, "companies": [], "builders": data}
    return {
        "version": data.get("version", 1),
        "companies": data.get("companies", []),
        "builders": data.get("builders", []),
    }


def validate(data: dict) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    companies = data.get("companies", [])
    builders = data.get("builders", [])

    company_ids = {}
    for index, company in enumerate(companies, start=1):
        cid = company.get("id")
        if not cid:
            errors.append(f"company[{index}] missing id")
            continue
        if cid in company_ids:
            errors.append(f"duplicate company id: {cid}")
        company_ids[cid] = company
        if not company.get("name"):
            errors.append(f"company[{cid}] missing name")

    builder_ids = {}
    handles = {}
    for index, builder in enumerate(builders, start=1):
        bid = builder.get("id")
        handle = (builder.get("handle") or "").lstrip("@")
        label = bid or builder.get("name") or f"builder[{index}]"
        if not bid:
            errors.append(f"builder[{index}] missing id")
        elif bid in builder_ids:
            errors.append(f"duplicate builder id: {bid}")
        else:
            builder_ids[bid] = builder

        if not builder.get("name"):
            errors.append(f"{label} missing name")
        if not handle:
            errors.append(f"{label} missing handle")
        elif handle.lower() in handles:
            errors.append(f"duplicate builder handle: {handle}")
        else:
            handles[handle.lower()] = builder

        company_id = builder.get("company_id")
        if company_id and company_id not in company_ids:
            errors.append(f"{label} references unknown company_id: {company_id}")
        if not company_id and builder.get("type") == "person":
            warnings.append(f"{label} has no company_id")

    return errors, warnings


def summary(data: dict) -> dict:
    companies = data.get("companies", [])
    builders = data.get("builders", [])
    company_by_id = {company.get("id"): company for company in companies}
    linked = [builder for builder in builders if builder.get("company_id")]
    unlinked = [builder for builder in builders if not builder.get("company_id")]
    company_counts = {}
    for builder in linked:
        cid = builder.get("company_id")
        company_counts[cid] = company_counts.get(cid, 0) + 1
    return {
        "version": data.get("version", 1),
        "company_count": len(companies),
        "builder_count": len(builders),
        "linked_builder_count": len(linked),
        "unlinked_builder_count": len(unlinked),
        "companies": [
            {
                "id": cid,
                "name": company_by_id.get(cid, {}).get("name"),
                "builder_count": count,
            }
            for cid, count in sorted(company_counts.items())
        ],
        "unlinked_builders": [
            {"id": builder.get("id"), "name": builder.get("name"), "handle": builder.get("handle")}
            for builder in unlinked
        ],
    }


def list_builders(data: dict) -> list[dict]:
    company_by_id = {company.get("id"): company for company in data.get("companies", [])}
    rows = []
    for builder in data.get("builders", []):
        company = company_by_id.get(builder.get("company_id"), {})
        rows.append(
            {
                "id": builder.get("id"),
                "name": builder.get("name"),
                "handle": builder.get("handle"),
                "type": builder.get("type"),
                "role": builder.get("role"),
                "company_id": builder.get("company_id"),
                "company": company.get("name"),
                "priority": builder.get("priority") or company.get("priority"),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and inspect builder/company profiles.")
    parser.add_argument("command", choices=["validate", "summary", "list-builders"])
    parser.add_argument("--profiles", required=True)
    args = parser.parse_args()

    data = load_profiles(args.profiles)
    errors, warnings = validate(data)

    if args.command == "validate":
        output = {"ok": not errors, "errors": errors, "warnings": warnings, **summary(data)}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        raise SystemExit(1 if errors else 0)
    if args.command == "summary":
        print(json.dumps({"errors": errors, "warnings": warnings, **summary(data)}, ensure_ascii=False, indent=2))
        return
    if args.command == "list-builders":
        print(json.dumps(list_builders(data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
