"""Bounded JSON, static signatures and safe reads shared by the business gate."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

MAX_INPUT = 32_768
MAX_OUTPUT = 65_536
MAX_SOURCE = 524_288


class BusinessError(ValueError):
    """An intentionally content-free, stable error code safe for tool results."""


def reject(code):
    raise BusinessError(code)


def read_safe(root: Path, path: Path, limit: int = MAX_SOURCE) -> bytes:
    """Reject every symlink/reparse component and bound the actual read."""
    try:
        relative = path.relative_to(root)
        if not relative.parts or any(p in ("..", ".") for p in relative.parts):
            reject("unsafe_path")
        current = root
        for part in (None, *relative.parts):
            if part is not None:
                current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                reject("unsafe_path")
        if not stat.S_ISREG(info.st_mode) or not path.resolve().is_relative_to(root.resolve()):
            reject("unsafe_path")
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        final = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino) or (after.st_size, after.st_mtime_ns, after.st_ino) != (final.st_size, final.st_mtime_ns, final.st_ino):
            reject("file_changed_during_read")
        if len(data) > limit:
            reject("size_limit")
        return data
    except BusinessError:
        raise
    except (OSError, ValueError):
        reject("required_file_unavailable")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject("duplicate_json_key")
        result[key] = value
    return result


def dumps(value, limit=MAX_OUTPUT):
    try:
        def finite_json(item, depth=0):
            if depth > 24:
                reject("schema_depth")
            if type(item) is dict:
                if any(type(key) is not str for key in item):
                    reject("invalid_json")
                for child in item.values():
                    finite_json(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    finite_json(child, depth + 1)
            elif type(item) is float:
                if not math.isfinite(item):
                    reject("nonfinite_number")
            elif type(item) is int:
                if not -(2**63) <= item < 2**63:
                    reject("json_integer_limit")
            elif item is not None and type(item) not in (str, bool):
                reject("invalid_json")
        finite_json(value)
        data = json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"))
        if len(data.encode()) > limit:
            reject("size_limit")
        return data
    except BusinessError:
        raise
    except (ValueError, TypeError, RecursionError):
        reject("invalid_json")


def loads(data, limit=MAX_INPUT):
    if not isinstance(data, (str, bytes)) or len(data.encode() if isinstance(data, str) else data) > limit:
        reject("size_limit")
    try:
        value = json.loads(data, object_pairs_hook=_pairs,
                           parse_constant=lambda _: reject("nonfinite_number"))
        dumps(value, limit)
        return value
    except BusinessError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        reject("invalid_json")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else dumps(value).encode()).hexdigest()


def validate(value, schema, depth=0):
    """Validate the closed subset we emit, independently of provider enforcement."""
    if depth > 24:
        reject("schema_depth")
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate(value, alternative, depth + 1)
                return
            except BusinessError:
                pass
        reject("schema_mismatch")
    kind = schema.get("type")
    matches = {"null": value is None, "string": type(value) is str,
               "boolean": type(value) is bool, "integer": type(value) is int,
               "number": type(value) in (int, float), "object": type(value) is dict,
               "array": type(value) is list}
    if not matches.get(kind, False):
        reject("schema_mismatch")
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        reject("schema_mismatch")
    if kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 4096) or "pattern" in schema and not re.search(schema["pattern"], value):
            reject("schema_mismatch")
    if kind in ("integer", "number"):
        if not schema["minimum"] <= value <= schema["maximum"] or type(value) is float and not math.isfinite(value):
            reject("schema_mismatch")
    if kind == "object":
        props = schema["properties"]
        if not set(schema["required"]) <= set(value) <= set(props) or schema.get("additionalProperties") is not False:
            reject("schema_mismatch")
        for key, item in value.items():
            validate(item, props[key], depth + 1)
    if kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema["maxItems"]:
            reject("schema_mismatch")
        for item in value:
            validate(item, schema["items"], depth + 1)


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def static_signature(source: bytes, function: str):
    """Parse only a deliberately small annotation grammar; never eval or import."""
    try:
        tree = ast.parse(source.decode("utf-8"))
        names = {}
        primitives = {"str", "bool", "int", "float", "list"}
        typing_names = {"Literal", "Optional", "TypedDict", "Annotated", "NotRequired"}
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    binding = alias.asname or alias.name.split(".")[0]
                    if binding in primitives or binding in typing_names and (not isinstance(node, ast.ImportFrom) or node.module != "typing" or alias.name != binding):
                        reject("ambiguous_annotation_binding")
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                node = node.value
            if name:
                if name in primitives | typing_names:
                    reject("ambiguous_annotation_binding")
                if name in names:
                    reject("duplicate_symbol")
                names[name] = node

        def schema(node, seen=()):
            if isinstance(node, ast.Constant) and node.value is None:
                return {"type": "null"}
            if isinstance(node, ast.Name):
                if node.id == "str":
                    return {"type": "string", "maxLength": 4096}
                if node.id == "bool":
                    return {"type": "boolean"}
                if node.id in ("int", "float"):
                    reject("unbounded_number")
                if node.id in seen or node.id not in names:
                    reject("unsupported_annotation")
                definition = names[node.id]
                if isinstance(definition, ast.ClassDef):
                    if len(definition.bases) != 1 or not isinstance(definition.bases[0], ast.Name) or definition.bases[0].id != "TypedDict" or definition.keywords:
                        reject("unsupported_annotation")
                    props = {}
                    optional = []
                    for field in definition.body:
                        if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name) or field.value is not None:
                            reject("unsupported_annotation")
                        if field.target.id in props or field.target.id.startswith("_"):
                            reject("duplicate_symbol")
                        annotation = field.annotation
                        if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name) and annotation.value.id == "NotRequired":
                            optional.append(field.target.id)
                            annotation = annotation.slice
                        props[field.target.id] = schema(annotation, (*seen, node.id))
                    result = object_schema(props)
                    result["required"] = [key for key in props if key not in optional]
                    return result
                return schema(definition, (*seen, node.id))
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                return {"anyOf": [schema(node.left, seen), schema(node.right, seen)]}
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                kind = node.value.id
                parts = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
                if kind == "Literal":
                    values = [ast.literal_eval(part) for part in parts]
                    if not values or any(type(v) is not str for v in values) or len(set(values)) != len(values):
                        reject("unsupported_annotation")
                    return {"type": "string", "enum": values, "maxLength": 4096}
                if kind == "Optional" and len(parts) == 1:
                    return {"anyOf": [schema(parts[0], seen), {"type": "null"}]}
                if kind == "list" and len(parts) == 1:
                    return {"type": "array", "items": schema(parts[0], seen), "maxItems": 256}
                if kind == "Annotated" and len(parts) == 2:
                    base = parts[0]
                    bounds = ast.literal_eval(parts[1])
                    if isinstance(base, ast.Name) and base.id == "str" and type(bounds) is dict and set(bounds) <= {"minLength", "maxLength", "pattern"}:
                        if any(type(bounds[key]) is not int or not 0 <= bounds[key] <= 4096 for key in bounds if key != "pattern") or bounds.get("minLength", 0) > bounds.get("maxLength", 4096) or bounds.get("pattern", "\\S") not in ("\\S", "^(?!512)[A-Z0-9]{2,20}$"):
                            reject("unsupported_annotation")
                        return {"type": "string", "maxLength": 4096, **bounds}
                    if not isinstance(base, ast.Name) or base.id not in ("int", "float") or type(bounds) is not dict or set(bounds) != {"minimum", "maximum"}:
                        reject("unsupported_annotation")
                    if any(type(v) not in (int, float) or not -10**15 <= v <= 10**15 for v in bounds.values()) or bounds["minimum"] > bounds["maximum"]:
                        reject("unsupported_annotation")
                    return {"type": "integer" if base.id == "int" else "number", **bounds}
            reject("unsupported_annotation")

        node = names.get(function)
        if function.startswith("_") or not isinstance(node, ast.FunctionDef) or node.decorator_list or node.type_comment:
            reject("unapproved_callable")
        args = node.args
        if args.vararg or args.kwarg or args.posonlyargs or args.kwonlyargs or args.defaults or args.kw_defaults:
            reject("unsupported_signature")
        properties = {arg.arg: schema(arg.annotation) for arg in args.args if not arg.arg.startswith("_")}
        if len(properties) != len(args.args) or not node.returns:
            reject("unsupported_signature")
        return object_schema(properties), schema(node.returns)
    except BusinessError:
        raise
    except (SyntaxError, ValueError, TypeError, UnicodeError, RecursionError):
        reject("invalid_callable_source")
