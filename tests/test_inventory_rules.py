"""The inventory business rules (tests/inventory_rules.py) as tests.

Offline: the object package is generated from a tenant-free Inventory KM
fixture. Each business rule runs
over hand-built objects that cover every branch, through a client that
evaluates predicates in plain Python (tests/inventory_oracle.py). The PQL the
real client sends is checked against a recording transport.

The same questions run end to end against Celonis, after a real
``celofast km pull``, in test_inventory_acceptance.py.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from celofast import ObjectNotFoundError, QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelClient, KnowledgeModelConnection
from celofast.sdk import Capture
from celofast.sdk.package import write_package

from inventory_oracle import MemoryClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "inventory_km.json"
AS_OF = date(2026, 9, 23)


def at(day: date | None) -> datetime | None:
    """Celonis DATE values load as datetimes; test data uses midnights."""
    return None if day is None else datetime.combine(day, time())


def _purge() -> None:
    for name in list(sys.modules):
        if name.split(".")[0] == "generated" or name == "inventory_rules":
            del sys.modules[name]


def _import(path: Path):
    """Import generated.inventory and the rules with ``path`` first on sys.path."""
    _purge()
    sys.path.insert(0, str(path))
    try:
        return (
            importlib.import_module("generated.inventory"),
            importlib.import_module("inventory_rules"),
        )
    finally:
        sys.path.remove(str(path))


@pytest.fixture(scope="module")
def offline(tmp_path_factory):
    root = tmp_path_factory.mktemp("offline")
    capture = Capture.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    write_package(capture, root / "generated" / "inventory")
    sdk, rules = _import(root)
    yield SimpleNamespace(sdk=sdk, rules=rules)
    _purge()


def make(cls, **values):
    """Build a loaded object; unspecified fields are null."""
    fields = {field.name: None for field in cls.fields}
    unknown = set(values) - set(fields)
    assert not unknown, unknown
    fields.update(values)
    return cls(key=fields["id"], **fields)


def keys(items):
    return [item.key for item in items]


# ---------------------------------------------------------------------------
# 1. Below safety stock, without near-term firm supply
# ---------------------------------------------------------------------------


def stock_scenario(sdk):
    Plant, Stock, Supply = sdk.Plant, sdk.MaterialMasterPlant, sdk.PlannedSupply
    objects = [make(Plant, id="P-DE", country="DE"), make(Plant, id="P-FR", country="FR")]

    def item(id_, plant="P-DE", stock=5.0, safety=10.0, discontinued=0):
        objects.append(make(Stock, id=id_, plant_id=plant, is_discontinued=discontinued,
                            current_valuated_stock_quantity=stock, safety_stock_quantity=safety))

    def plan(id_, target, *, firm=1, quantity=20.0, finish=date(2026, 9, 30)):
        objects.append(make(Supply, id=id_, material_master_plant_id=target, is_firm_order=firm,
                            order_quantity=quantity, order_finish_date=at(finish)))

    item("A")                                            # no supply at all -> at risk
    item("B"); plan("S-B", "B")                          # firm supply in horizon -> covered
    item("C"); plan("S-C", "C", firm=0)                  # only planned, not firm -> at risk
    item("D"); plan("S-D", "D", finish=date(2026, 10, 7))  # due at the horizon (exclusive)
    item("E"); plan("S-E", "E", finish=AS_OF)            # due today (inclusive) -> covered
    item("F"); plan("S-F", "F", quantity=0.0)            # zero quantity -> at risk
    item("G", discontinued=1)                            # discontinued
    item("H", stock=15.0)                                # above safety stock
    item("I", stock=None)                                # unknown stock is not "below"
    item("J", plant="P-FR")                              # other country
    item("K", plant=None)                                # no plant reference
    item("L"); plan("S-L", "L", quantity=None)           # unknown quantity is not positive
    item("M"); plan("S-M1", "M", firm=0); plan("S-M2", "M")  # one covering supply suffices
    return objects


def test_below_safety_stock_without_firm_supply(offline):
    client = MemoryClient(offline.sdk.km, stock_scenario(offline.sdk))
    page = offline.rules.below_safety_stock_without_firm_supply(client, AS_OF)
    assert keys(page) == ["A", "C", "D", "F", "L"]
    assert all(type(item) is offline.sdk.MaterialMasterPlant for item in page)
    assert keys(offline.rules.below_safety_stock_without_firm_supply(
        client, AS_OF, country="FR")) == ["J"]
    small = offline.rules.below_safety_stock_without_firm_supply(client, AS_OF, page_size=2)
    assert keys(small) == ["A", "C"] and small.has_more
    assert keys(small.next_page()) == ["D", "F"]


# ---------------------------------------------------------------------------
# 2. Overdue, under-received schedules of active external purchases
# ---------------------------------------------------------------------------


def purchase_scenario(sdk):
    Vendor, Document = sdk.Vendor, sdk.PurchaseDocument
    Line, Schedule = sdk.PurchaseDocumentLine, sdk.PurchaseScheduleLine
    objects = [
        make(Vendor, id="V-EXT", is_internal_vendor=0),
        make(Vendor, id="V-INT", is_internal_vendor=1),
        make(Vendor, id="V-UNKNOWN", is_internal_vendor=None),
        make(Document, id="D-ACTIVE", is_canceled=0, vendor_id="V-EXT"),
        make(Document, id="D-CANCELED", is_canceled=1, vendor_id="V-EXT"),
        make(Document, id="D-INTERNAL", is_canceled=0, vendor_id="V-INT"),
        make(Document, id="D-UNKNOWN", is_canceled=0, vendor_id="V-UNKNOWN"),
        make(Document, id="D-NO-VENDOR", is_canceled=0, vendor_id=None),
        make(Line, id="L-ACTIVE", is_canceled=0, header_id="D-ACTIVE"),
        make(Line, id="L-CANCELED", is_canceled=1, header_id="D-ACTIVE"),
        make(Line, id="L-UNKNOWN-STATUS", is_canceled=None, header_id="D-ACTIVE"),
        make(Line, id="L-DOC-CANCELED", is_canceled=0, header_id="D-CANCELED"),
        make(Line, id="L-INTERNAL", is_canceled=0, header_id="D-INTERNAL"),
        make(Line, id="L-VENDOR-UNKNOWN", is_canceled=0, header_id="D-UNKNOWN"),
        make(Line, id="L-NO-VENDOR", is_canceled=0, header_id="D-NO-VENDOR"),
    ]

    def schedule(id_, line, expected_date, received=0.0, expected=10.0):
        objects.append(make(Schedule, id=id_, purchase_document_line_id=line,
                            expected_delivery_date=at(expected_date),
                            received_quantity=received, expected_quantity=expected))

    schedule("S-LATE", "L-ACTIVE", date(2026, 9, 1), received=5.0)     # overdue, partial
    schedule("S-LATEST", "L-ACTIVE", date(2026, 7, 15), received=2.0)  # oldest -> first
    schedule("S-RECEIVED", "L-ACTIVE", date(2026, 9, 10), received=10.0)
    schedule("S-FUTURE", "L-ACTIVE", date(2026, 9, 30))
    schedule("S-TODAY", "L-ACTIVE", AS_OF)                              # due today is not overdue
    schedule("S-NO-RECEIPT-DATA", "L-ACTIVE", date(2026, 7, 1), received=None)
    schedule("S-LINE-CANCELED", "L-CANCELED", date(2026, 8, 15))
    schedule("S-LINE-UNKNOWN", "L-UNKNOWN-STATUS", date(2026, 8, 15))
    schedule("S-DOC-CANCELED", "L-DOC-CANCELED", date(2026, 8, 1))
    schedule("S-INTERNAL", "L-INTERNAL", date(2026, 8, 1))
    schedule("S-VENDOR-UNKNOWN", "L-VENDOR-UNKNOWN", date(2026, 8, 1))
    schedule("S-NO-VENDOR", "L-NO-VENDOR", date(2026, 8, 1))
    schedule("S-NO-LINE", None, date(2026, 8, 1))
    return objects


def test_overdue_external_schedules(offline):
    client = MemoryClient(offline.sdk.km, purchase_scenario(offline.sdk))
    page = offline.rules.overdue_external_schedules(client, AS_OF)
    assert keys(page) == ["S-LATEST", "S-LATE"]  # earliest expected delivery first
    assert [d.expected_delivery_date for d in page] == [at(date(2026, 7, 15)), at(date(2026, 9, 1))]


def test_reusable_purchase_predicates(offline):
    sdk, rules = offline.sdk, offline.rules
    client = MemoryClient(sdk.km, purchase_scenario(sdk))
    documents = client.objects(sdk.PurchaseDocument).where(rules.external_purchase)
    assert keys(documents.fetch_page()) == ["D-ACTIVE"]
    lines = client.objects(sdk.PurchaseDocumentLine).where(rules.active_external_line)
    assert keys(lines.fetch_page()) == ["L-ACTIVE"]
    # The predicates belong to their own types and cannot filter another type.
    with pytest.raises(QueryValidationError, match="cannot filter"):
        client.objects(sdk.PurchaseScheduleLine).where(rules.active_external_line)


# ---------------------------------------------------------------------------
# 3. Other plants that could supply the same material
# ---------------------------------------------------------------------------


def transfer_scenario(sdk):
    Stock = sdk.MaterialMasterPlant

    def item(id_, material, plant, stock, safety, discontinued=0):
        return make(Stock, id=id_, material_id=material, plant_id=plant, is_discontinued=discontinued,
                    current_valuated_stock_quantity=stock, safety_stock_quantity=safety)

    return [
        item("M1@1000", "M1", "1000", 0.0, 10.0),        # the target
        item("M1@1100", "M1", "1100", 50.0, 20.0),       # +30
        item("M1@1150", "M1", "1150", 25.5, 5.0),        # +20.5
        item("M1@1200", "M1", "1200", 10.0, 20.0),       # below its safety stock
        item("M1@1300", "M1", "1300", 90.0, 10.0, 1),    # discontinued
        item("M1@1400", "M1", "1400", 30.0, None),       # unknown safety stock
        item("M1@1000b", "M1", "1000", 90.0, 10.0),      # same plant as the target
        item("M2@1100", "M2", "1100", 90.0, 10.0),       # other material
        item("M3@NONE", "M3", None, 0.0, 10.0),          # target without a plant
    ]


def test_alternative_sources(offline):
    client = MemoryClient(offline.sdk.km, transfer_scenario(offline.sdk))
    candidates = offline.rules.alternative_sources(client, "M1@1000")
    assert [(c.material_plant.key, c.quantity_above_safety) for c in candidates] == [
        ("M1@1100", 30.0), ("M1@1150", 20.5),
    ]
    assert offline.rules.alternative_sources(client, "M2@1100") == []
    with pytest.raises(ValueError, match="material and plant references"):
        offline.rules.alternative_sources(client, "M3@NONE")
    with pytest.raises(ObjectNotFoundError):
        offline.rules.alternative_sources(client, "missing")


# ---------------------------------------------------------------------------
# The PQL the real client sends
# ---------------------------------------------------------------------------


class Transport:
    """Records each export and returns no rows."""

    def __init__(self):
        self.queries = []

    def __call__(self, query, *, limit=None, offset=None, distinct=False):
        self.queries.append(query)
        return pd.DataFrame(columns=[column.name for column in query.columns])


def real_client(sdk, transport):
    # The KM's current input values are those captured at pull.
    inputs = json.loads(FIXTURE.read_text(encoding="utf-8")).get("input_variables") or {}
    native = MagicMock()
    native.get_variables.return_value = [
        SimpleNamespace(key=key, data_type=variable.get("dataType"), value_or_default=variable.get("value"))
        for key, variable in inputs.items()
    ]
    connection = KnowledgeModelConnection(native, SimpleNamespace(id="fixture-dm"))
    connection._export = transport
    return KnowledgeModelClient(connection, sdk.km)


def expression(field):
    """A field's captured expression, parenthesized as the planner renders it."""
    return f"({field.expression}\n)"


def test_relations_render_into_one_query(offline):
    transport = Transport()
    offline.rules.below_safety_stock_without_firm_supply(real_client(offline.sdk, transport), AS_OF)
    (query,) = transport.queries  # No separate lookups: one export per read.
    (condition,) = [f.query for f in query.filters]
    stock, plant = offline.sdk.MaterialMasterPlant.fields, offline.sdk.Plant.fields
    supply = offline.sdk.PlannedSupply.fields
    mmp = '"o_celonis_MaterialMasterPlant"'

    # to-one has(): the plant's columns are BIND'ed onto each material-plant row.
    country = f"BIND({mmp}, {expression(plant.country)})"
    exists = f"BIND({mmp}, {expression(plant.id)}) IS NOT NULL"
    assert f"CASE WHEN {exists} AND CASE WHEN {country} = 'DE' THEN 1 ELSE 0 END = 1" in condition
    # ~any(): PU_COUNT of matching planned supplies on the material-plant table is 0.
    pu = f"PU_COUNT({mmp}, {expression(supply.id)}, (CASE WHEN {expression(supply.is_firm_order)} = 1"
    assert f"CASE WHEN {pu}" in condition
    # Date arguments compare as midnight: 2026-09-23 and 2026-10-07 in epoch milliseconds.
    assert "{t 1790121600000}" in condition and "{t 1791331200000}" in condition
    assert ") > 0 THEN 1 ELSE 0 END = 0" in condition
    stock_qty, safety = expression(stock.current_valuated_stock_quantity), expression(stock.safety_stock_quantity)
    assert f"CASE WHEN {stock_qty} < {safety} THEN 1 ELSE 0 END = 1" in condition


def test_nested_relations_bind_one_hop_at_a_time(offline):
    transport = Transport()
    offline.rules.overdue_external_schedules(real_client(offline.sdk, transport), AS_OF)
    (query,) = transport.queries
    condition = query.filters[0].query
    schedule, line = '"o_celonis_PurchaseScheduleLine"', '"o_celonis_PurchaseDocumentLine"'
    header = '"o_celonis_PurchaseDocument"'
    vendor = expression(offline.sdk.Vendor.fields.is_internal_vendor)
    # schedule -> line -> header -> vendor: each hop pulls onto the previous table.
    assert f"BIND({schedule}, BIND({line}, BIND({header}, {vendor})))" in condition
    assert [o.query for o in query.order_by_columns] == [
        expression(offline.sdk.PurchaseScheduleLine.fields.expected_delivery_date),
        expression(offline.sdk.PurchaseScheduleLine.fields.id),
    ]


def test_any_inside_pu_binds_the_related_parent(offline):
    sdk, transport = offline.sdk, Transport()
    Stock, Schedule, Line = sdk.MaterialMasterPlant, sdk.PurchaseScheduleLine, sdk.PurchaseDocumentLine
    real_client(sdk, transport).objects(Stock).where(
        Stock.relations.purchase_schedule_lines.any(
            Schedule.relations.purchase_document_line.has(Line.fields.is_canceled.eq(1))
        )
    ).fetch_page()
    condition = transport.queries[0].filters[0].query
    # Inside the PU filter, the schedule line's parent is BIND'ed onto the schedule line (1:N:1).
    canceled = f'BIND("o_celonis_PurchaseScheduleLine", {expression(Line.fields.is_canceled)})'
    assert condition.startswith('FILTER CASE WHEN PU_COUNT("o_celonis_MaterialMasterPlant", ')
    assert f"{canceled} = 1" in condition


def test_the_single_read_is_logged(offline, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="celofast.km")
    transport = Transport()
    offline.rules.below_safety_stock_without_firm_supply(real_client(offline.sdk, transport), AS_OF)
    (record,) = caplog.records
    assert record.getMessage().startswith(
        "Read O_CELONIS_MATERIALMASTERPLANT objects (MaterialMasterPlant) (limit=101, offset=0, distinct)"
    )
    assert "PU_COUNT(" in record.getMessage() and "BIND(" in record.getMessage()
