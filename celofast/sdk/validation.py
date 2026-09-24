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

Test runs bind KM input placeholders with their values at pull; the
generated fields keep the placeholders, bound with live values at query time.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from celofast.exceptions import CeloFastError, UnresolvedVariableError
from celofast.sdk.capture import Capture, Progress
from celofast.sdk.expressions import bind_inputs
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


def _with_pull_values(capture: Capture) -> Callable[[str], str | None]:
    """Bind input placeholders with their values at pull, for test runs only.

    Generated fields keep their placeholders; reads bind the KM's values at
    query time. Returns None when an input has no value.
    """
    inputs = capture.input_variables or {}
    types = {name: variable.get("dataType") for name, variable in inputs.items()}

    def value(name: str) -> str | None:
        current = inputs.get(name, {}).get("value")
        return None if current is None else str(current)

    def bind(expression: str) -> str | None:
        try:
            return bind_inputs(expression, value, types)
        except UnresolvedVariableError:
            return None

    return bind


def resolve_types(
    capture: Capture, describe: Describe, *,
    mapping: MappingInput = None, progress: Progress | None = None,
) -> Capture:
    """Record Celonis result types; attributes whose export fails are rejected.

    Attributes with an input that has no value keep their declared type.
    """
    types = dict(capture.types)
    rejected = _rejections(capture)
    bind = _with_pull_values(capture)

    def resolve(rid: str, attribute_id: str, expression: str) -> ValueType | None:
        if expression in types:
            return types[expression]
        bound = bind(expression)
        if bound is None:
            return None
        if progress is not None:
            progress(f"Resolving type: {rid}.{attribute_id}", 0, 1)
        try:
            value_type = describe(bound)
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
        if not plain:
            result.append(field)
    return result


def _probe(keys: list[str], fields: list[tuple[FieldSpec, str]], execute: Execute) -> dict[str, str]:
    """Rejections among ``fields``, each paired with its expression bound for the test run."""
    try:
        rows = execute([f"({expression}\n)" for expression in (*keys, *(e for _, e in fields))], SAMPLE_ROWS)
    except CeloFastError:
        raise
    except Exception as exc:  # noqa: BLE001 - native export errors identify bad fields
        if len(fields) == 1:
            return {fields[0][0].attribute_id: _reason(exc)}
        middle = len(fields) // 2
        return {**_probe(keys, fields[:middle], execute), **_probe(keys, fields[middle:], execute)}
    rejected: dict[str, str] = {}
    for index, (field, _) in enumerate(fields, start=len(keys)):
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
    """Test-run calculated attributes; return the capture with rejections added.

    Attributes with an input that has no value are not test-run.
    """
    bind = _with_pull_values(capture)
    work = []
    for spec in normalize(capture, mapping).objects:
        bound = [(field, e) for field in _calculated(spec) if (e := bind(field.expression)) is not None]
        if bound:
            work.append((spec, [f.expression for f in spec.fields if f.key], bound))
    rejected = _rejections(capture)
    for done, (spec, keys, fields) in enumerate(work):
        if progress is not None:
            progress(f"Validating calculated attributes: {spec.class_name}", done, len(work))
        found = _probe(keys, fields, execute)
        if found:
            rejected.setdefault(spec.record_id, {}).update(found)
    if progress is not None and work:
        progress("Validating calculated attributes", len(work), len(work))
    return capture.model_copy(update={"validation": rejected})
