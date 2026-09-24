"""Test-run calculated KM attributes at pull; reject those Celonis cannot serve.

Plain Data Model columns are typed by the Data Model and never probed. For
every other generated field, one export per object type reads the key and all
calculated fields for a sample of rows. When Celonis rejects the query, the
field set is bisected until each failing field is isolated. When it succeeds,
every sampled value must decode to the field's resolved type. The result maps
record IDs to rejected attribute IDs and reasons, stored in the capture so
generation stays a pure function of it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import SimpleNamespace
from typing import Any

from celofast.exceptions import CeloFastError
from celofast.sdk.capture import Capture, Progress
from celofast.sdk.hydration import ValueType, decode
from celofast.sdk.mapping import FieldSpec, MappingConfig, ObjectSpec, column, normalize

Execute = Callable[[Sequence[str], int], Sequence[Sequence[object]]]
"""Runs one export of the given expressions and returns plain row values."""

SAMPLE_ROWS = 200


def resolve_types(
    capture: Capture, describe: Callable[[str], ValueType | None], *,
    mapping: Mapping[str, Any] | MappingConfig | None = None,
    progress: Progress | None = None,
) -> Capture:
    """Resolve calculated types from Celonis schemas before value validation."""
    types = dict(capture.types)
    rejected = {rid: dict(fields) for rid, fields in capture.validation.items()}

    def resolve(rid: str, attribute_id: str, expression: str) -> ValueType | None:
        if progress is not None:
            progress(f"Resolving type: {rid}.{attribute_id}", 0, 1)
        try:
            value_type = types.get(expression) or describe(expression)
        except CeloFastError:
            raise
        except Exception as exc:  # noqa: BLE001 - same native export errors as validation
            rejected.setdefault(rid, {})[attribute_id] = _reason(exc)
            return None
        if value_type is not None:
            types[expression] = value_type
        return value_type

    normalize(capture, mapping, _resolve_type=resolve)
    return capture.with_types(types).with_validation(rejected)


def _calculated(spec: ObjectSpec) -> list[FieldSpec]:
    """Generated fields that are not plain columns of the record's own table."""
    result = []
    for field in spec.fields:
        found = column(field.expression)
        plain = found is not None and spec.table is not None and found[0].lower() == spec.table.lower()
        if not plain and "${" not in field.expression:
            result.append(field)
    return result


def _reason(exc: BaseException) -> str:
    cause = exc.__cause__ or exc
    text = " ".join(str(cause).split())
    return f"fails in Celonis: {text[:160]}" if text else f"fails in Celonis: {type(cause).__name__}"


def _probe(
    spec: ObjectSpec, fields: list[FieldSpec], execute: Execute
) -> dict[str, str]:
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
        declared = SimpleNamespace(
            owner=spec.record_id, name=field.name, value_type=field.value_type, nullable=True
        )
        for row in rows:
            try:
                decode(declared, row[index])  # type: ignore[arg-type]
            except CeloFastError as exc:
                rejected[field.attribute_id] = f"returned values that are not {field.value_type} ({exc})"
                break
    return rejected


def validate(
    capture: Capture,
    execute: Execute,
    *,
    mapping: Mapping[str, Any] | MappingConfig | None = None,
    progress: Progress | None = None,
) -> dict[str, dict[str, str]]:
    """Rejected calculated attributes per record, found by test-running them."""
    model = normalize(capture.with_validation({}), mapping)
    work = [(spec, fields) for spec in model.objects if (fields := _calculated(spec))]
    result: dict[str, dict[str, str]] = {}
    for done, (spec, fields) in enumerate(work, start=1):
        if progress is not None:
            progress(f"Validating calculated attributes: {spec.class_name}", done - 1, len(work))
        rejected = _probe(spec, fields, execute)
        if rejected:
            result[spec.record_id] = rejected
    if progress is not None and work:
        progress("Validating calculated attributes", len(work), len(work))
    return result
