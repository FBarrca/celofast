"""Object Link: the Data Model's graph between objects of one type (e.g. a bill of materials)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from celofast.exceptions import QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelClient, KnowledgeModelConnection
from celofast.sdk import ObjectCollection, ObjectLinkRelation
from celofast.sdk.generate import generate
from celofast.sdk.model import normalize
from celofast.sdk.validation import object_links

from objects_fixture import capture, load, write
from test_object_runtime import PLANT_COLUMNS, Transport, plant_row

PLANT = '"o_Plant"'
KEY = '"o_Plant"."ID"'
SOURCE, TARGET = f"LINK_SOURCE({KEY})", f"LINK_TARGET({KEY})"


def links(own, condition=""):
    """The per-plant link count, as the Celonis KM attributes on Object Link write it."""
    return (
        f"COALESCE(PU_FIRST({PLANT}, CASE WHEN {own} = {KEY} THEN BIND(COMMON_TABLE({own}, {KEY}), "
        f"PU_COUNT(DOMAIN_TABLE({own}), {own}{condition})) END), 0)"
    )


def linked():
    return capture().model_copy(update={"object_links": ["o_Plant"]})


@pytest.fixture
def sdk(tmp_path):
    return load(write(tmp_path / "linked", linked()), "linked_sdk")


@pytest.fixture
def transport():
    return Transport()


@pytest.fixture
def client(sdk, transport):
    native = MagicMock()
    native.get_variables.return_value = [SimpleNamespace(key="factor", data_type="NUMBER", value_or_default="2")]
    connection = KnowledgeModelConnection(native, SimpleNamespace(id="dm"))
    connection._export = transport
    return KnowledgeModelClient(connection, sdk.km)


def test_pull_finds_the_tables_celonis_serves_link_functions_on():
    runs = []

    def execute(expressions, limit):
        runs.append(expressions)
        if expressions != [SOURCE]:
            raise RuntimeError('Table is not a connected table of the Object Link configuration.')
        return [("P1",)]

    assert object_links(capture(), execute).object_links == ["o_Plant"]
    # Every generated type with a single-column key is tried once; events are not.
    assert sorted(expression for (expression,) in runs) == [
        'LINK_SOURCE("o_Material"."ID")', SOURCE,
    ]


def test_linked_types_get_link_targets_and_link_sources():
    plant = next(o for o in normalize(linked()).objects if o.record_id == "O_PLANT")
    assert [(l.name, l.target, l.graph) for l in plant.links if l.graph] == [
        ("link_sources", "O_PLANT", "sources"), ("link_targets", "O_PLANT", "targets"),
    ]
    source = generate(linked())["objects.py"].decode()
    assert "    link_targets = _o.ObjectLinkRelation(Plant, ends='targets')\n" in source
    # Without an Object Link, nothing changes.
    assert "ObjectLinkRelation" not in generate(capture())["objects.py"].decode()


def test_traversal_reads_the_linked_objects_in_one_query(sdk, client, transport):
    assert isinstance(sdk.Plant.relations.link_targets, ObjectLinkRelation)
    transport.reply(plant_row("P1"), columns=PLANT_COLUMNS)
    plant = client.objects(sdk.Plant).get("P1")

    targets = plant.links.link_targets
    assert isinstance(targets, ObjectCollection) and targets.object_type is sdk.Plant
    transport.reply(plant_row("P2"), columns=PLANT_COLUMNS)
    assert [p.key for p in targets.fetch_page()] == ["P2"]
    # Plants at the target end of a link whose source is P1.
    condition = transport.requests[1].query.filters[0].query
    assert condition == f"FILTER CASE WHEN {links(TARGET, f', {SOURCE} = {chr(39)}P1{chr(39)}')} > 0 THEN 1 ELSE 0 END = 1;"

    transport.reply(columns=PLANT_COLUMNS)
    plant.links.link_sources.fetch_page()
    condition = transport.requests[2].query.filters[0].query
    assert links(SOURCE, f", {TARGET} = 'P1'") in condition


def test_any_and_count_follow_the_links_of_each_object(sdk, client, transport):
    targets = sdk.Plant.relations.link_targets
    # The sort aggregate is selected too, after the fields.
    transport.replies.append(pd.DataFrame(columns=["f0", "f1", "f2", "f3", "f4", "s0"]))
    client.objects(sdk.Plant).where(
        targets.any() & sdk.Plant.relations.link_sources.count().gt(2)
    ).order_by(targets.count().desc()).fetch_page()
    query = transport.requests[0].query
    condition = query.filters[0].query
    assert f"CASE WHEN {links(SOURCE)} > 0 THEN 1 ELSE 0 END = 1" in condition
    assert f"CASE WHEN {links(TARGET)} > 2 THEN 1 ELSE 0 END = 1" in condition
    assert query.order_by_columns[0].query == links(SOURCE)


def test_conditions_on_linked_objects_are_rejected(sdk):
    targets = sdk.Plant.relations.link_targets
    with pytest.raises(QueryValidationError, match="takes no condition"):
        targets.any(sdk.Plant.fields.country.eq("DE"))
    with pytest.raises(QueryValidationError, match="count\\(\\) without a condition only"):
        targets.count(sdk.Plant.fields.country.eq("DE"))
    with pytest.raises(QueryValidationError, match="count\\(\\) without a condition only"):
        targets.max(sdk.Plant.fields.opened)
