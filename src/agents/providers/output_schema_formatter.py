from __future__ import annotations

from typing import Any

from ..types import OutputSchema

_JSON_SCHEMA_KEYS = {
    "$id",
    "$schema",
    "$defs",
    "$ref",
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "oneOf",
    "anyOf",
    "allOf",
    "not",
    "if",
    "then",
    "else",
    "additionalProperties",
}


def normalize_output_schema(output_schema: OutputSchema) -> dict[str, Any]:
    if _is_json_schema(output_schema):
        return output_schema
    return _build_object_schema_from_shorthand(output_schema)


def _is_json_schema(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(key in _JSON_SCHEMA_KEYS for key in value)


def _build_object_schema_from_shorthand(mapping: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field_name, field_spec in mapping.items():
        if not isinstance(field_name, str):
            continue
        properties[field_name] = _normalize_property_schema(field_spec)
        required.append(field_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _normalize_property_schema(field_spec: Any) -> dict[str, Any]:
    if isinstance(field_spec, dict):
        if _is_json_schema(field_spec):
            return field_spec
        # Nested shorthand objects are converted recursively.
        return _build_object_schema_from_shorthand(field_spec)

    if isinstance(field_spec, list):
        item_schema: dict[str, Any]
        if field_spec:
            item_schema = _normalize_property_schema(field_spec[0])
        else:
            item_schema = {"type": "string"}
        return {"type": "array", "items": item_schema}

    if isinstance(field_spec, bool):
        return {"type": "boolean"}
    if isinstance(field_spec, int) and not isinstance(field_spec, bool):
        return {"type": "integer"}
    if isinstance(field_spec, float):
        return {"type": "number"}
    if isinstance(field_spec, str):
        if field_spec.strip():
            return {"type": "string", "description": field_spec}
        return {"type": "string"}

    return {"type": "string"}
