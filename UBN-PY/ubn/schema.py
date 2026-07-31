from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from typing import Any, get_args, get_origin, Union

def _basic_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple, set)):
        return "array"
    return "string"

def _merge_types(types: list[str]) -> str:
    uniq = list(dict.fromkeys(types))
    if len(uniq) == 1:
        return uniq[0]
    if "number" in uniq and "integer" in uniq:
        uniq = [t for t in uniq if t != "integer"]
    return "|".join(sorted(uniq))

def infer_schema(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value):
        return infer_schema(dataclasses.asdict(value))
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return infer_schema(value.model_dump())
        except Exception:
            pass
    if isinstance(value, dict):
        props: dict[str, Any] = {}
        required: list[str] = []
        for k, v in value.items():
            if v is not None:
                required.append(str(k))
            props[str(k)] = infer_schema(v)
        return {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": True,
        }
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if not items:
            return {"type": "array", "items": {"type": "null"}}
        item_schemas = [infer_schema(i) for i in items]
        item_types = [s.get("type", "string") for s in item_schemas]
        merged = _merge_types(item_types)
        if merged == "object" and all(s.get("type") == "object" for s in item_schemas):
            all_props: dict[str, list[str]] = {}
            for s in item_schemas:
                for pk, pv in s.get("properties", {}).items():
                    all_props.setdefault(pk, []).append(pv.get("type", "string"))
            merged_props = {
                k: {"type": _merge_types(v)}
                for k, v in all_props.items()
            }
            return {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": merged_props,
                    "additionalProperties": True,
                },
            }
        return {"type": "array", "items": {"type": merged}}
    t = _basic_type_name(value)
    return {"type": t}

def infer_schema_from_signature(fn) -> dict[str, Any]:
    sig = inspect.signature(fn)
    hints = getattr(fn, "__annotations__", {})
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        hint = hints.get(name, Any)
        schema = annotation_to_schema(hint)
        if param.default is inspect._empty:
            required.append(name)
        else:
            schema = schema_with_default(schema, param.default)
        props[name] = schema
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }

def schema_with_default(schema: dict[str, Any], default: Any) -> dict[str, Any]:
    out = dict(schema)
    out["default"] = default
    return out

def annotation_to_schema(ann: Any) -> dict[str, Any]:
    origin = get_origin(ann)
    args = get_args(ann)
    if ann is Any or ann is inspect._empty:
        return {"type": "string"}
    if ann is str:
        return {"type": "string"}
    if ann is int:
        return {"type": "integer"}
    if ann is float:
        return {"type": "number"}
    if ann is bool:
        return {"type": "boolean"}
    if ann is dict:
        return {"type": "object"}
    if ann is list or ann is tuple or ann is set:
        return {"type": "array", "items": {"type": "string"}}
    if origin in (list, tuple, set):
        item_ann = args[0] if args else Any
        return {"type": "array", "items": annotation_to_schema(item_ann)}
    if origin is dict:
        return {
            "type": "object",
            "additionalProperties": annotation_to_schema(args[1]) if len(args) > 1 else {"type": "string"},
        }
    if origin is Union:
        parts = []
        for a in args:
            if a is type(None):
                parts.append("null")
            else:
                parts.append(annotation_to_schema(a).get("type", "string"))
        return {"type": _merge_types(parts)}
    if dataclasses.is_dataclass(ann):
        return infer_schema(ann)
    return {"type": "string"}

def schema_hash(schema: dict[str, Any]) -> str:
    raw = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]