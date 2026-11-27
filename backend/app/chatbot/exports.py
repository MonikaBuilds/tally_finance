"""Scoped, expiring snapshots for Excel downloads from chat."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import time
from urllib.parse import urlencode
from uuid import uuid4

from app.cache.manager import cache_manager
from app.export.exporter import build_report_excel
from app.export import report_specs

EXPORT_TTL = 3600
MAX_LOCAL_BYTES = 32 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_local = OrderedDict()


def _key(user_id, org_id, company, token):
    scope = json.dumps([str(user_id), str(org_id), (company or "").casefold(), str(token)])
    return "chat:export:v1:" + hashlib.sha256(scope.encode()).hexdigest()


def _prune():
    now = time.time()
    for key in list(_local):
        if _local[key][0] <= now:
            _local.pop(key)
    while sum(len(entry[1]) for entry in _local.values()) > MAX_LOCAL_BYTES:
        _local.popitem(last=False)


async def save_export(user_id, org_id, company, tool_name, arguments, result, answer):
    if not user_id or not company:
        return None
    token = str(uuid4())
    record = {
        "tool_name": tool_name, "arguments": arguments, "company_name": company,
        "result": result, "answer": answer, "created_at": time.time(),
    }
    blob = json.dumps(record, default=str, ensure_ascii=False).encode("utf-8")
    if len(blob) > MAX_SNAPSHOT_BYTES:
        return None
    record = json.loads(blob)
    key = _key(user_id, org_id, company, token)
    try:
        stored = await cache_manager.set_entry(key=key, data=record, fresh_ttl=EXPORT_TTL, retention_ttl=EXPORT_TTL)
    except Exception:
        stored = False
    if not stored:
        _local[key] = (time.time() + EXPORT_TTL, blob)
        _prune()
    title = tool_name.removeprefix("get_").replace("_", " ").title()
    return {
        "url": f"/chat/exports/{token}.xlsx?" + urlencode({"company_name": company}),
        "filename": f"chat_{tool_name.removeprefix('get_')}.xlsx",
        "label": f"Download {title} as Excel",
    }


async def load_export(user_id, org_id, company, token):
    key = _key(user_id, org_id, company, token)
    _prune()
    try:
        record, _state, _at = await cache_manager.get_entry(key)
    except Exception:
        record = None
    if not isinstance(record, dict) and key in _local:
        record = json.loads(_local[key][1])
    if not isinstance(record, dict) or time.time() - record.get("created_at", 0) >= EXPORT_TTL:
        return None
    return deepcopy(record)


def snapshot_spec(record):
    """Export every structured record, including records truncated in chat text."""
    result = record["result"]
    data = result.get("data") or {}
    company = record["company_name"]
    arguments = record.get("arguments") or {}
    period = report_specs.period_label(
        data.get("from_date") or arguments.get("from_date"),
        data.get("to_date") or arguments.get("to_date"),
    )
    if record["tool_name"] == "get_profit_loss":
        spec = report_specs.profit_loss_spec(data.get("report") or data, company, period)
    else:
        sections = []

        def label(key):
            return key.replace("_", " ").title()

        def walk(value, location):
            if isinstance(value, dict):
                scalars = [{"field": label(str(k)), "value": v} for k, v in value.items()
                           if not isinstance(v, (dict, list)) and v is not None]
                if scalars:
                    sections.append({"title": location, "columns": [
                        {"key": "field", "label": "Field"}, {"key": "value", "label": "Value"},
                    ], "rows": scalars})
                for key, child in value.items():
                    if isinstance(child, (dict, list)):
                        walk(child, f"{location} / {label(str(key))}")
            elif isinstance(value, list):
                if not value:
                    return
                rows = [row if isinstance(row, dict) else {"value": row} for row in value]
                keys = list(dict.fromkeys(k for row in rows for k, v in row.items() if not isinstance(v, (dict, list))))
                columns = []
                for key in keys:
                    values = [row.get(key) for row in rows if row.get(key) is not None]
                    numeric = bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
                    kind = "date" if key == "date" or key.endswith("_date") else "text"
                    if numeric:
                        kind = "qty" if "quantity" in key or key.endswith("_qty") else "int" if "count" in key or key.endswith("_days") else "amount"
                    columns.append({"key": key, "label": label(key), "type": kind})
                if columns:
                    sections.append({"title": location, "columns": columns,
                                     "rows": [{k: row.get(k) for k in keys} for row in rows]})
                for index, row in enumerate(rows, 1):
                    for key, child in row.items():
                        if isinstance(child, (dict, list)):
                            walk(child, f"{location} / Record {index} / {label(key)}")

        walk(data, "Report")
        spec = report_specs.spec(record["tool_name"].removeprefix("get_").replace("_", " ").title(), company, sections, period=period)
    spec["meta"] = list(spec.get("meta") or []) + [
        ("Data source", str(result.get("source", "tally"))),
        ("Stale cached data", "Yes" if result.get("is_stale") else "No"),
        ("Calculation method", str(result.get("calculation_method", "Tally report rows"))),
    ]
    spec["notes"] = list(spec.get("notes") or []) + [
        "Snapshot of the report returned in this chat; later queries do not change this download.",
    ]
    if result.get("calculation_method") == "application_aggregation":
        spec["notes"].append("Derived figures are calculated from Tally report rows.")
    return spec


def export_excel(record):
    return build_report_excel(snapshot_spec(record))
