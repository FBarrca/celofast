"""Pull-time validation of calculated attributes, with a fake Celonis export."""

import pytest

from celofast.exceptions import CeloFastError
from celofast.sdk import Capture
from celofast.sdk.mapping import normalize
from celofast.sdk.validation import SAMPLE_ROWS, validate

from objects_fixture import JOINS, MAPPING, TABLES, attribute, capture


def with_calculated(*attributes):
    layer = capture().to_dict()
    plant = next(item for item in layer["records"] if item["id"] == "O_PLANT")
    plant["attributes"] += list(attributes)
    return Capture.create(capture().source, layer, joins=JOINS, tables=TABLES)


class Export:
    """Fails any query containing FAIL; otherwise returns the given values per column."""

    def __init__(self, values):
        self.values = values
        self.queries = []

    def __call__(self, expressions, limit):
        assert limit == SAMPLE_ROWS
        self.queries.append(list(expressions))
        if any("FAIL" in expression for expression in expressions):
            raise RuntimeError("Syntax error near FAIL")
        return [tuple(self.values.get(e.strip()[1:-1].strip(), "x") for e in expressions)]


def test_failing_attributes_are_isolated_by_bisection():
    captured = with_calculated(
        attribute("GOOD", 'UPPER("o_Plant"."Country")'),
        attribute("BAD1", 'FAIL("o_Plant"."Country")'),
        attribute("OTHER", 'LOWER("o_Plant"."Country")'),
        attribute("BAD2", 'FAIL(1)'),
    )
    export = Export({})
    rejected = validate(captured, export, mapping=MAPPING)
    assert rejected == {"O_PLANT": {
        "BAD1": "fails in Celonis: Syntax error near FAIL",
        "BAD2": "fails in Celonis: Syntax error near FAIL",
    }}
    # Plain columns are typed by the Data Model and never probed; every
    # query carries the key so rows stay per object.
    first = export.queries[0]
    assert first[0] == '("o_Plant"."ID"\n)'
    assert not any('"o_Plant"."Opened"' in e for query in export.queries for e in query)
    # The rejected attributes are skipped at generation.
    model = normalize(captured.with_validation(rejected), MAPPING)
    plant = next(o for o in model.objects if o.record_id == "O_PLANT")
    assert {"GOOD", "OTHER"} <= {f.attribute_id for f in plant.fields}
    assert not {"BAD1", "BAD2"} & {f.attribute_id for f in plant.fields}


def test_values_that_do_not_decode_are_rejected():
    captured = with_calculated(attribute("FLAG", 'CASE WHEN "o_Plant"."Country" = \'DE\' THEN 1.0 END'))
    rejected = validate(captured, Export({'CASE WHEN "o_Plant"."Country" = \'DE\' THEN 1.0 END': 1.0}),
                        mapping=MAPPING)
    reason = rejected["O_PLANT"]["FLAG"]
    assert reason.startswith("returned values that are not str")


def test_records_without_calculated_attributes_need_no_query():
    export = Export({})
    assert validate(capture(), export, mapping=MAPPING) == {}
    # Only the Material record's ${factor} attribute is calculated, and
    # attributes with input variables are not probed.
    assert export.queries == []


def test_celofast_errors_are_not_mistaken_for_bad_attributes():
    def export(expressions, limit):
        raise CeloFastError("not connected")

    with pytest.raises(CeloFastError, match="not connected"):
        validate(with_calculated(attribute("GOOD", 'UPPER("o_Plant"."Country")')), export, mapping=MAPPING)
