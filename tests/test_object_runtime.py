from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from celofast.exceptions import (
    ObjectIdentityError,
    ObjectNotFoundError,
    ObjectValueError,
    QueryValidationError,
    UnresolvedVariableError,
)
from celofast.resources.knowledge_model import KnowledgeModelClient, KnowledgeModelConnection
from celofast.sdk import ObjectCollection, ObjectPage, ToOne

from objects_fixture import load, write


def wrapped(expression):
    return f"({expression}\n)"


def eq_filter(expression, literal):
    return f"FILTER CASE WHEN {wrapped(expression)} = {literal} THEN 1 ELSE 0 END = 1;"


PLANT_COLUMNS = ["id", "country", "plantnumber", "opened", "description"]
MATERIAL_COLUMNS = ["id", "plant_id", "stock", "active", "updated", "count", "untyped"]


class Transport:
    """Records each native export and replies with queued frames."""

    def __init__(self):
        self.requests = []
        self.replies = []

    def reply(self, *rows, columns):
        frame = pd.DataFrame(list(rows), columns=[f"f{i}" for i in range(len(columns))])
        self.replies.append(frame)

    def __call__(self, query, *, limit=None, offset=None, distinct=False):
        self.requests.append(SimpleNamespace(query=query, limit=limit, offset=offset, distinct=distinct))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def sdk(tmp_path):
    return load(write(tmp_path / "inventory"))


@pytest.fixture
def transport():
    return Transport()


@pytest.fixture
def client(sdk, transport):
    connection = KnowledgeModelConnection(MagicMock(), SimpleNamespace(id="dm"))
    connection._export = transport
    return KnowledgeModelClient(connection, sdk.km, variables={"factor": "2"})


def plant_row(id_="P1", country="DE"):
    return [id_, country, None, pd.Timestamp("2020-01-01"), "Main"]


def test_get_retrieves_a_typed_object_with_plain_values(sdk, client, transport):
    transport.reply(plant_row(), columns=PLANT_COLUMNS)
    plant = client.objects(sdk.Plant).get("P1")

    assert type(plant) is sdk.Plant
    assert plant.key == "P1" and plant.id == "P1"
    assert plant.country == "DE"
    assert plant.plantnumber is None
    assert plant.opened == date(2020, 1, 1) and type(plant.opened) is date
    assert plant.ref.key == "P1" and plant.ref.object_type == "O_PLANT"

    request = transport.requests[0]
    assert (request.limit, request.offset, request.distinct) == (2, 0, True)
    # Expressions are parenthesized so a trailing line comment cannot swallow SQL.
    assert [c.query for c in request.query.columns] == [wrapped(e) for e in (
        '"o_Plant"."ID"', '"o_Plant"."Country"', '"o_Plant"."Number"',
        '"o_Plant"."Opened"', '"o_Plant"."Text"',
    )]
    assert [f.query for f in request.query.filters] == [eq_filter('"o_Plant"."ID"', "'P1'")]
    assert [o.query for o in request.query.order_by_columns] == [wrapped('"o_Plant"."ID"')]
    # Reading loaded values never performs another request.
    _ = (plant.country, plant.key, plant.ref, plant.links)
    assert len(transport.requests) == 1


def test_filtered_collections_page_in_key_order(sdk, client, transport):
    base = client.objects(sdk.Plant)
    german = base.where(sdk.Plant.fields.country.eq("DE"))
    assert isinstance(german, ObjectCollection) and german is not base
    assert base._predicates == ()

    transport.reply(plant_row("P1"), plant_row("P2"), plant_row("P3"), columns=PLANT_COLUMNS)
    page = german.fetch_page(page_size=2)
    assert isinstance(page, ObjectPage)
    assert [p.key for p in page.items] == ["P1", "P2"] == [p.key for p in page]
    assert page.has_more and len(page) == 2
    assert transport.requests[0].limit == 3
    assert [f.query for f in transport.requests[0].query.filters] == [
        eq_filter('"o_Plant"."Country"', "'DE'")
    ]

    transport.reply(plant_row("P3"), columns=PLANT_COLUMNS)
    last = page.next_page()
    assert [p.key for p in last] == ["P3"] and not last.has_more
    assert transport.requests[1].offset == 2
    assert last.next_page() is None

    transport.reply(columns=PLANT_COLUMNS)
    assert base.where(sdk.Plant.fields.country.eq(None)).fetch_page().items == ()
    country = wrapped('"o_Plant"."Country"')
    assert transport.requests[2].query.filters[0].query == (
        f"FILTER CASE WHEN {country} IS NULL THEN 1 ELSE 0 END = 1;"
    )


def test_relationships_are_explicit_typed_requests(sdk, client, transport):
    transport.reply(plant_row(), columns=PLANT_COLUMNS)
    plant = client.objects(sdk.Plant).get("P1")

    materials = plant.links.materials
    assert isinstance(materials, ObjectCollection) and materials.object_type is sdk.Material
    assert len(transport.requests) == 1  # Building the accessor is not a fetch.

    transport.reply(
        ["M1", "P1", 4.0, 1, pd.Timestamp("2024-05-01 10:30"), 3.0, "x"],
        ["M2", "P1", np.nan, 0, pd.NaT, np.nan, None],
        columns=MATERIAL_COLUMNS,
    )
    page = materials.fetch_page(page_size=50)
    first, second = page.items
    assert [f.query for f in transport.requests[1].query.filters] == [
        eq_filter('"o_Material"."Plant_ID"', "'P1'")
    ]
    assert transport.requests[1].query.columns[2].query == wrapped('"o_Material"."Stock" * 2')
    assert (first.stock, first.active, first.count) == (4.0, True, 3)
    assert type(first.count) is int and first.updated == datetime(2024, 5, 1, 10, 30)
    assert (second.stock, second.active, second.updated, second.count) == (None, False, None, None)

    to_plant = first.links.plant
    assert isinstance(to_plant, ToOne)
    transport.reply(plant_row(), columns=PLANT_COLUMNS)
    assert to_plant.fetch() == plant
    transport.reply(columns=PLANT_COLUMNS)
    assert to_plant.fetch() is None

    orphan = sdk.Material(key="M9", id="M9", plant_id=None, stock=None, active=None,
                          updated=None, count=None, untyped=None)._attach(client)
    before = len(transport.requests)
    assert orphan.links.plant.fetch() is None
    assert orphan.links.plant._collection.fetch_page().items == ()
    assert len(transport.requests) == before  # A null reference needs no request.


def test_composite_keys(sdk, client, transport):
    transport.reply(["P1", pd.Timestamp("2024-01-31"), 7], columns=["plant_id", "day", "qty"])
    # Celonis DATE columns load as datetimes; a date argument means its midnight.
    line = client.objects(sdk.StockLine).get(("P1", date(2024, 1, 31)))
    assert line.key == ("P1", datetime(2024, 1, 31)) and line.qty == 7
    filters = [f.query for f in transport.requests[0].query.filters]
    assert filters == [
        eq_filter('"o_Stock"."Plant_ID"', "'P1'"),
        eq_filter('"o_Stock"."Day"', "{t 1706659200000}"),
    ]
    with pytest.raises(QueryValidationError, match="2 parts"):
        client.objects(sdk.StockLine).get("P1")
    with pytest.raises(QueryValidationError, match="None"):
        client.objects(sdk.StockLine).get(("P1", None))


def test_missing_objects_and_failed_requests_are_errors(sdk, client, transport):
    transport.reply(columns=PLANT_COLUMNS)
    with pytest.raises(ObjectNotFoundError, match="P404"):
        client.objects(sdk.Plant).get("P404")
    transport.replies.append(RuntimeError("native failure"))
    with pytest.raises(RuntimeError, match="native failure"):
        client.objects(sdk.Plant).fetch_page()


@pytest.mark.parametrize(
    ("rows", "error", "message"),
    [
        ([plant_row("P1", "DE"), plant_row("P1", "FR")], ObjectIdentityError, "conflicting values for country"),
        ([plant_row(None)], ObjectIdentityError, "key value is null"),
        ([["P1", 42, None, None, None]], ObjectValueError, "expects str"),
        ([["P1", "DE", None, pd.Timestamp("2020-01-01 08:00"), None]], ObjectValueError, "date but received time"),
    ],
)
def test_hydration_rejects_invalid_identity_and_values(sdk, client, transport, rows, error, message):
    transport.reply(*rows, columns=PLANT_COLUMNS)
    with pytest.raises(error, match=message):
        client.objects(sdk.Plant).fetch_page()


def test_identical_rows_for_one_key_collapse(sdk, client, transport):
    transport.reply(plant_row(), plant_row(), columns=PLANT_COLUMNS)
    assert len(client.objects(sdk.Plant).fetch_page().items) == 1


def test_unexpected_result_shape_is_rejected(sdk, client, transport):
    transport.replies.append(pd.DataFrame({"other": ["P1"]}))
    with pytest.raises(ObjectValueError, match="expected"):
        client.objects(sdk.Plant).fetch_page()


def test_predicates_are_typed_and_scoped_to_their_object_type(sdk, client):
    with pytest.raises(ObjectValueError, match="expects str"):
        sdk.Plant.fields.country.eq(1)
    with pytest.raises(ObjectValueError, match="never null"):
        sdk.Plant.fields.id.eq(None)
    with pytest.raises(ObjectValueError, match="expects bool"):
        sdk.Material.fields.active.eq(1)
    with pytest.raises(QueryValidationError, match="cannot filter O_MATERIAL"):
        client.objects(sdk.Material).where(sdk.Plant.fields.country.eq("DE"))
    with pytest.raises(QueryValidationError, match="field predicates"):
        client.objects(sdk.Plant).where('FILTER "o_Plant"."Country" = \'DE\';')
    with pytest.raises(TypeError, match="&, \\|, and ~"):
        bool(sdk.Plant.fields.country.eq("DE"))
    for bad in (0, -1, True, 10_001):
        with pytest.raises(QueryValidationError, match="page_size"):
            client.objects(sdk.Plant).fetch_page(page_size=bad)


def test_literal_values_are_never_variables(sdk, client, transport):
    transport.reply(columns=PLANT_COLUMNS)
    client.objects(sdk.Plant).where(sdk.Plant.fields.country.eq("${factor}'")).fetch_page()
    assert "= '${factor}\\'' THEN" in transport.requests[0].query.filters[0].query


def test_unbound_variables_fail_before_any_request(sdk, client, transport):
    unbound = KnowledgeModelClient(client._connection, sdk.km)
    with pytest.raises(UnresolvedVariableError, match="factor"):
        unbound.objects(sdk.Material).fetch_page()
    assert transport.requests == []


def test_only_types_from_the_connected_package_are_accepted(sdk, client, tmp_path):
    other = load(write(tmp_path / "other"), name="other_inventory_sdk")
    with pytest.raises(QueryValidationError, match="same generated package"):
        client.objects(other.Plant)
    with pytest.raises(QueryValidationError, match="cannot filter"):
        client.objects(sdk.Plant).where(other.Plant.fields.country.eq("DE"))
    detached = sdk.Plant(key="P1", id="P1", country=None, plantnumber=None, opened=None, description=None)
    with pytest.raises(QueryValidationError, match="not loaded by a client"):
        detached.links.materials


def test_results_contain_no_analytical_types(sdk, client, transport):
    transport.reply(plant_row(), columns=PLANT_COLUMNS)
    plant = client.objects(sdk.Plant).fetch_page().items[0]
    values = [getattr(plant, name) for name in PLANT_COLUMNS]
    assert all(type(v) in (str, date, type(None)) for v in values)
    for removed in ("select", "execute", "build", "records"):
        assert not hasattr(client, removed)


def test_predicate_composition_is_validated(sdk):
    Plant, Material = sdk.Plant, sdk.Material
    with pytest.raises(QueryValidationError, match="same object type"):
        Plant.fields.country.eq("DE") & Material.fields.active.eq(True)
    with pytest.raises(QueryValidationError, match="same type"):
        Plant.fields.country.eq(Material.fields.id)
    with pytest.raises(ObjectValueError, match="Cannot compare"):
        Plant.fields.country.lt(Plant.fields.opened)
    with pytest.raises(ObjectValueError, match="nulls only support"):
        Plant.fields.opened.lt(None)
    with pytest.raises(ObjectValueError, match="no ordering"):
        Material.fields.active.gt(False)
    with pytest.raises(QueryValidationError, match="relates to O_MATERIAL"):
        Plant.relations.materials.any(Plant.fields.country.eq("DE"))


def test_order_by_rejects_other_types(sdk, client):
    with pytest.raises(QueryValidationError, match="order_by"):
        client.objects(sdk.Plant).order_by(sdk.Material.fields.count.asc())
    # int and float fields compare with each other.
    assert sdk.Material.fields.stock.gt(sdk.Material.fields.count) is not None


def test_exported_pql_is_logged_at_debug(sdk, client, transport, caplog):
    import logging

    transport.reply(columns=PLANT_COLUMNS)
    client.objects(sdk.Plant).fetch_page()
    assert not caplog.records  # Silent unless DEBUG is enabled for celofast.km.

    caplog.set_level(logging.DEBUG, logger="celofast.km")
    transport.reply(plant_row(), columns=PLANT_COLUMNS)
    client.objects(sdk.Plant).where(sdk.Plant.fields.country.eq("DE")).order_by(
        sdk.Plant.fields.opened.desc()
    ).fetch_page(page_size=10)
    (record,) = caplog.records
    assert record.name == "celofast.km" and record.levelname == "DEBUG"
    text = record.getMessage()
    assert text.startswith("Read O_PLANT objects (Plant) (limit=11, offset=0, distinct)")
    assert '"o_Plant"."Country"\n) AS "f1",  -- country' in text
    assert '"o_Plant"."Text"\n) AS "f4"  -- description\n)' in text  # No trailing comma.
    assert eq_filter('"o_Plant"."Country"', "'DE'") in text
    opened, key = wrapped('"o_Plant"."Opened"'), wrapped('"o_Plant"."ID"')
    assert text.endswith(f"ORDER BY {opened} DESC, {key} ASC")


def test_membership_range_and_pattern_predicates(sdk, client, transport):
    Plant, Material = sdk.Plant, sdk.Material
    transport.reply(columns=PLANT_COLUMNS)
    client.objects(Plant).where(
        Plant.fields.country.is_in(["DE", "FR"])
        & Plant.fields.opened.between(date(2020, 1, 1), date(2020, 12, 31))
        & ~Plant.fields.description.like("Old%")
    ).fetch_page()
    condition = transport.requests[0].query.filters[0].query
    country, opened = wrapped('"o_Plant"."Country"'), wrapped('"o_Plant"."Opened"')
    text = wrapped('"o_Plant"."Text"')
    assert f"CASE WHEN {country} IN ('DE', 'FR') THEN 1 ELSE 0 END = 1" in condition
    assert (
        f"CASE WHEN {opened} BETWEEN {{d '2020-01-01'}} AND {{d '2020-12-31'}} THEN 1 ELSE 0 END = 1"
        in condition
    )
    assert f"CASE WHEN {text} LIKE 'Old%' THEN 1 ELSE 0 END = 0" in condition

    with pytest.raises(QueryValidationError, match="at least one"):
        Plant.fields.country.is_in([])
    with pytest.raises(ObjectValueError, match="cannot be None"):
        Plant.fields.country.is_in(["DE", None])
    with pytest.raises(ObjectValueError, match="expects str"):
        Plant.fields.country.is_in([1])
    with pytest.raises(ObjectValueError, match="two values"):
        Plant.fields.opened.between(date(2020, 1, 1), None)
    with pytest.raises(ObjectValueError, match="no ordering"):
        Material.fields.active.between(False, True)
    with pytest.raises(ObjectValueError, match="not a string"):
        Material.fields.count.like("1%")


def test_relations_without_a_join_are_not_predicates(sdk):
    from celofast.sdk.objects import ToManyRelation

    # Plant.stock has no Data Model foreign key; it supports traversal only.
    relation = ToManyRelation("stock", sdk.Plant, sdk.StockLine)
    with pytest.raises(QueryValidationError, match="no Data Model foreign key or lookup path"):
        relation.any()


def test_relation_aggregates_render_pull_up_functions(sdk, client, transport):
    Plant, Material = sdk.Plant, sdk.Material
    materials = Plant.relations.materials
    # The sort-only aggregate comes back as an extra column after the fields.
    transport.replies.append(pd.DataFrame(
        [["P1", "DE", None, pd.Timestamp("2020-01-01"), "Main", 7]],
        columns=["f0", "f1", "f2", "f3", "f4", "s0"],
    ))
    page = client.objects(Plant).where(
        materials.count(Material.fields.active.eq(True)).gt(2)
        & materials.avg(Material.fields.stock).lt(10.0)
        & materials.max(Material.fields.updated).eq(None)
    ).order_by(materials.sum(Material.fields.count).desc()).fetch_page()
    query = transport.requests[0].query
    condition = query.filters[0].query
    plant, material_id = '"o_Plant"', wrapped('"o_Material"."ID"')
    active_column = wrapped('"o_Material"."Active"')
    active = f"CASE WHEN {active_column} = 1 THEN 1 ELSE 0 END = 1"
    assert f"CASE WHEN PU_COUNT({plant}, {material_id}, {active}) > 2 THEN 1 ELSE 0 END = 1" in condition
    stock = wrapped('"o_Material"."Stock" * 2')
    assert f"CASE WHEN PU_AVG({plant}, {stock}) < 10.0 THEN 1 ELSE 0 END = 1" in condition
    updated = wrapped('"o_Material"."Updated"')
    assert f"CASE WHEN PU_MAX({plant}, {updated}) IS NULL THEN 1 ELSE 0 END = 1" in condition
    count = wrapped('"o_Material"."Count"')
    assert [o.query for o in query.order_by_columns] == [
        f"PU_SUM({plant}, {count})", wrapped('"o_Plant"."ID"'),
    ]
    assert [o.ascending for o in query.order_by_columns] == [False, True]
    # Celonis ignores ORDER BY expressions that are not selected under DISTINCT.
    assert (query.columns[-1].name, query.columns[-1].query) == ("s0", f"PU_SUM({plant}, {count})")
    assert page.items[0].key == "P1" and page.items[0].description == "Main"
    assert len(transport.requests) == 1


def test_aggregates_compare_with_other_aggregates(sdk, client, transport):
    Material = sdk.Material
    materials = sdk.Plant.relations.materials
    transport.reply(columns=PLANT_COLUMNS)
    # More counted units than materials: both sides are Pull-Ups on the plant.
    client.objects(sdk.Plant).where(
        materials.sum(Material.fields.count).gt(materials.count())
    ).fetch_page()
    condition = transport.requests[0].query.filters[0].query
    plant = '"o_Plant"'
    units, keys = wrapped('"o_Material"."Count"'), wrapped('"o_Material"."ID"')
    total, count = f"PU_SUM({plant}, {units})", f"PU_COUNT({plant}, {keys})"
    assert condition == f"FILTER CASE WHEN {total} > {count} THEN 1 ELSE 0 END = 1;"


def test_aggregate_validation(sdk):
    Plant, Material, Stock = sdk.Plant, sdk.Material, sdk.StockLine
    materials = Plant.relations.materials
    with pytest.raises(ObjectValueError, match="numeric"):
        materials.sum(Material.fields.untyped)
    with pytest.raises(ObjectValueError, match="boolean"):
        materials.max(Material.fields.active)
    with pytest.raises(QueryValidationError, match="aggregates fields of O_MATERIAL"):
        materials.sum(Plant.fields.country)
    with pytest.raises(QueryValidationError, match="relates to O_MATERIAL"):
        materials.count(Plant.fields.country.eq("DE"))
    with pytest.raises(ObjectValueError, match="never null"):
        materials.count().eq(None)
    with pytest.raises(ObjectValueError, match="expects int"):
        materials.count().gt(2.5)
    with pytest.raises(QueryValidationError, match="same type"):
        materials.count().gt(Stock.fields.qty)
    from celofast.sdk.objects import ToManyRelation

    # Plant.stock has no foreign key: no Pull-Up path to aggregate over.
    with pytest.raises(QueryValidationError, match="Pull-Up aggregates need one"):
        ToManyRelation("stock", Plant, Stock).count()


def test_datetime_fields_accept_date_filters_as_midnight(sdk):
    updated = sdk.Material.fields.updated
    assert type(updated).__name__ == "DateTimeField"
    assert updated.gte(date(2024, 5, 1)).operand == datetime(2024, 5, 1)
    assert updated.between(date(2024, 5, 1), date(2024, 6, 1)).operand == (
        datetime(2024, 5, 1), datetime(2024, 6, 1)
    )
    assert updated.is_in([date(2024, 5, 1)]).operand == (datetime(2024, 5, 1),)
    # A strict date field (types override) still rejects datetimes.
    with pytest.raises(ObjectValueError, match="expects date"):
        sdk.Plant.fields.opened.eq(datetime(2020, 1, 1, 8))
