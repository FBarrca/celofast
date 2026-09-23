"""The inventory business rules (tests/inventory_rules.py) as tests.

Offline: the object package is generated from a tenant-free Inventory KM
fixture with the repository's inventory-objects.toml. Each business rule runs
over hand-built objects that cover every branch, through a client that
evaluates predicates in plain Python (tests/inventory_oracle.py). The PQL the
real client sends is checked against a recording transport.

The same questions run end to end against Celonis, after a real
``celofast km pull``, in test_inventory_acceptance.py.
"""

from __future__ import annotations

import importlib
import sys
from datetime import date, timedelta
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

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "inventory_km.json"
MAPPING = ROOT / "inventory-objects.toml"
AS_OF = date(2026, 9, 23)


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
    with MAPPING.open("rb") as stream:
        mapping = tomllib.load(stream)
    write_package(capture, root / "generated" / "inventory", mapping=mapping)
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
                            order_quantity=quantity, order_finish_date=finish))

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
                            expected_delivery_date=expected_date,
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
    assert [d.expected_delivery_date for d in page] == [date(2026, 7, 15), date(2026, 9, 1)]


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
    """Records each export and answers relation lookups with queued values."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.queries = []

    def __call__(self, query, *, limit=None, offset=None, distinct=False):
        self.queries.append(query)
        columns = [column.name for column in query.columns]
        if columns == ["v"]:
            return pd.DataFrame({"v": self.answers.pop(0)})
        return pd.DataFrame(columns=columns)


def real_client(sdk, transport):
    connection = KnowledgeModelConnection(
        MagicMock(), SimpleNamespace(id="fixture-dm"), source=sdk.km.source
    )
    connection._export = transport
    return KnowledgeModelClient(connection, sdk.km)


def test_relations_resolve_related_keys_before_the_object_read(offline):
    transport = Transport(["P-DE"], ["B", "E"])
    offline.rules.below_safety_stock_without_firm_supply(real_client(offline.sdk, transport), AS_OF)
    plants, supplies, final = transport.queries
    assert plants.columns[0].query == '("o_celonis_Plant"."ID"\n)'
    assert "\"o_celonis_Plant\".\"Country\"\n) = 'DE'" in plants.filters[0].query
    assert supplies.columns[0].query == '("o_celonis_PlannedSupply"."MaterialMasterPlant_ID"\n)'
    assert "{d '2026-09-23'}" in supplies.filters[0].query
    assert "{d '2026-10-07'}" in supplies.filters[0].query
    (condition,) = [f.query for f in final.filters]
    fields = offline.sdk.MaterialMasterPlant.fields

    def expression(field):  # Captured expressions are parenthesized as-is.
        return f"({field.metadata['pql']}\n)"

    plant, key = expression(fields.plant_id), expression(fields.id)
    assert f"CASE WHEN {plant} IN ('P-DE') THEN 1 ELSE 0 END = 1" in condition
    # ~any(...) is the exact complement: objects whose key is not among them.
    assert f"CASE WHEN {key} IN ('B', 'E') THEN 1 ELSE 0 END = 0" in condition
    stock = expression(fields.current_valuated_stock_quantity)
    safety = expression(fields.safety_stock_quantity)
    assert f"CASE WHEN {stock} < {safety} THEN 1 ELSE 0 END = 1" in condition


def test_nested_relations_resolve_innermost_first(offline):
    transport = Transport(["V1"], ["D1"], ["L1"])
    offline.rules.overdue_external_schedules(real_client(offline.sdk, transport), AS_OF)
    lookups = [query.columns[0].query for query in transport.queries[:3]]
    assert lookups == [
        '("o_celonis_Vendor"."ID"\n)',
        '("o_celonis_PurchaseDocument"."ID"\n)',
        '("o_celonis_PurchaseDocumentLine"."ID"\n)',
    ]
    final = transport.queries[3]
    assert [o.query for o in final.order_by_columns] == [
        '("o_celonis_PurchaseScheduleLine"."ExpectedDeliveryDate"\n)',
        '("o_celonis_PurchaseScheduleLine"."ID"\n)',
    ]
    assert "IN ('L1')" in final.filters[0].query


def test_a_relation_without_matches_filters_everything_out(offline):
    transport = Transport([], [])
    offline.rules.below_safety_stock_without_firm_supply(real_client(offline.sdk, transport), AS_OF)
    condition = transport.queries[-1].filters[0].query
    assert "IN (" not in condition
    assert "= 2 THEN 1 ELSE 0 END = 1" in condition  # has(): always false
    assert "= 2 THEN 1 ELSE 0 END = 0" in condition  # ~any(): always true
