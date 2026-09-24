"""Test-run calculated KM attributes at pull; reject those Celonis cannot serve.

Plain Data Model columns are typed by the Data Model and never probed. Pull
runs two steps, each returning an updated capture so generation stays a pure
function of it:

1. ``resolve_types`` asks Celonis for the result type of every calculated
   attribute that no override or column type covers.
2. ``validate`` exports the key and all calculated fields of each object type
   for a sample of rows. When Celonis rejects the query, the field set is
   bisected until each failing field is isolated. When it succeeds, every
   sampled value must convert to the field's type.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from celofast.exceptions import CeloFastError
from celofast.sdk.capture import Capture, Progress
from celofast.sdk.hydration import ValueType, convert
from celofast.sdk.mapping import FieldSpec, MappingInput, ObjectSpec, column, normalize

Describe = Callable[[str], "ValueType | None"]
"""Returns the Celonis result type of one expression."""
Execute = Callable[[Sequence[str], int], Sequence[Sequence[object]]]
"""Runs one export of the given expressions and returns plain row values."""

SAMPLE_ROWS = 200


def _reason(exc: BaseException) -> str:
    cause = exc.__cause__ or exc
    text = " ".join(str(cause).split())
    return f"fails in Celonis: {text[:160]}" if text else f"fails in Celonis: {type(cause).__name__}"


def _rejections(capture: Capture) -> dict[str, dict[str, str]]:
    return {rid: dict(fields) for rid, fields in capture.validation.items()}


def resolve_types(
    capture: Capture, describe: Describe, *,
    mapping: MappingInput = None, progress: Progress | None = None,
) -> Capture:
    """Record Celonis result types; attributes whose export fails are rejected."""
    types = dict(capture.types)
    rejected = _rejections(capture)

    def resolve(rid: str, attribute_id: str, expression: str) -> ValueType | None:
        if expression in types:
            return types[expression]
        if progress is not None:
            progress(f"Resolving type: {rid}.{attribute_id}", 0, 1)
        try:
            value_type = describe(expression)
        except CeloFastError:
            raise
        except Exception as exc:  # noqa: BLE001 - native export errors identify bad fields
            rejected.setdefault(rid, {})[attribute_id] = _reason(exc)
            return None
        if value_type is not None:
            types[expression] = value_type
        return value_type

    normalize(capture, mapping, describe=resolve)
    return capture.model_copy(update={"types": types, "validation": rejected})


def _calculated(spec: ObjectSpec) -> list[FieldSpec]:
    """Generated fields that are not plain columns of the record's own table."""
    result = []
    for field in spec.fields:
        found = column(field.expression)
        plain = found is not None and spec.table is not None and found[0].lower() == spec.table.lower()
        if not plain and "${" not in field.expression:
            result.append(field)
    return result


def _probe(spec: ObjectSpec, fields: list[FieldSpec], execute: Execute) -> dict[str, str]:
    key = [field for field in spec.fields if field.key]
    try:
        rows = execute([f"({f.expression}\n)" for f in (*key, *fields)], SAMPLE_ROWS)
    except CeloFastError:
        raise
    except Exception as exc:  # noqa: BLE001 - native export errors identify bad fields
        if len(fields) == 1:
            return {fields[0].attribute_id: _reason(exc)}
        middle = len(fields) // 2
        return {**_probe(spec, fields[:middle], execute), **_probe(spec, fields[middle:], execute)}
    rejected: dict[str, str] = {}
    for index, field in enumerate(fields, start=len(key)):
        for row in rows:
            if row[index] is None:
                continue
            try:
                convert(field.value_type, row[index])
            except ValueError as exc:
                rejected[field.attribute_id] = f"returned values that are not {field.value_type} ({exc})"
                break
    return rejected


def validate(
    capture: Capture, execute: Execute, *,
    mapping: MappingInput = None, progress: Progress | None = None,
) -> Capture:
    """Test-run calculated attributes; return the capture with rejections added."""
    model = normalize(capture, mapping)
    work = [(spec, fields) for spec in model.objects if (fields := _calculated(spec))]
    rejected = _rejections(capture)
    for done, (spec, fields) in enumerate(work):
        if progress is not None:
            progress(f"Validating calculated attributes: {spec.class_name}", done, len(work))
        found = _probe(spec, fields, execute)
        if found:
            rejected.setdefault(spec.record_id, {}).update(found)
    if progress is not None and work:
        progress("Validating calculated attributes", len(work), len(work))
    return capture.model_copy(update={"validation": rejected})
