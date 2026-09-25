"""End-to-end acceptance tests against the Inventory Management KM.

The suite runs the real ``celofast km pull inventory`` (configuration from this
repository's pyproject.toml and inventory-objects.toml) into a temporary
directory, imports the generated package, and runs the documented business
questions exactly as an application writes them. Each test asserts:

A. the API: the generated names exist and results are pages of typed objects
   holding plain Python values;
B. the values: every returned object satisfies the business rule (checked on
   its loaded values and by traversing its links), and nothing that satisfies
   the rule is missing (checked in plain Python over every loaded object).

They run online as part of ``uv run pytest`` whenever Celonis credentials are
configured, and only read data. Without credentials they are skipped;
``uv run pytest -m "not live"`` excludes them explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from celofast import ObjectNotFoundError
from celofast.sdk import Field, ObjectPage, ToManyRelation, ToOneRelation

from inventory_oracle import select

# Run with credentials from .env or the environment; exclude with -m "not live".
pytestmark = pytest.mark.live

SPEC_DATE = date(2026, 9, 23)  # The planning date used in the documented examples.
PLAIN = (str, int, float, bool, date, datetime, type(None))


def moment(day: date) -> datetime:
    """Celonis DATE values load as datetimes; a date argument means its midnight."""
    return day if isinstance(day, datetime) else datetime.combine(day, time())


# The object types the documented questions use. Pull generates more (every
# record with a primary key); they are not loaded here.
USED = (
    "MaterialMasterPlant", "PlannedSupply", "Plant", "PurchaseDocument",
    "PurchaseDocumentLine", "PurchaseScheduleLine", "Vendor",
)


@pytest.fixture(scope="module")
def km(inventory_package):
    """Connect to the pulled KM and load every used object."""
    package = inventory_package

    from celofast import CeloFast

    source = package.km.source
    client = CeloFast(source.space_id, source.package_id, mode=source.mode).km(package.km)
    loaded = {}
    for object_type in package.km:
        if object_type.__name__ not in USED:
            continue
        items, page = [], client.objects(object_type).fetch_page(page_size=5000)
        while page:
            items += page.items
            page = page.next_page()
        loaded[object_type.__name__] = items
    # Count native exports from here on: every read must be exactly one.
    exports = []
    export = client._connection._export
    client._connection._export = lambda *args, **kwargs: exports.append(1) or export(*args, **kwargs)
    return SimpleNamespace(package=package, client=client, all=loaded, exports=exports)


def by_key(items):
    return {item.key: item for item in items}


def children(items, field):
    grouped = defaultdict(list)
    for item in items:
        grouped[getattr(item, field)].append(item)
    return grouped


def assert_typed_page(page, object_type):
    assert isinstance(page, ObjectPage)
    for item in page.items:
        assert type(item) is object_type
        for field in object_type.fields:
            assert isinstance(getattr(item, field.name), PLAIN), field.name


def expect_page(page, expected_keys, page_size):
    assert [item.key for item in page.items] == expected_keys[:page_size]
    assert page.has_more == (len(expected_keys) > page_size)


def all_items(collection):
    items, page = [], collection.fetch_page(page_size=1000)
    while page:
        items += page.items
        page = page.next_page()
    return items


def test_pulled_package_declares_the_documented_api(km):
    from generated.inventory import (  # noqa: F401 - the documented import surface
        MaterialMasterPlant,
        PlannedSupply,
        Plant,
        PurchaseDocument,
        PurchaseDocumentLine,
        PurchaseScheduleLine,
        Vendor,
        km as inventory,
    )

    assert inventory is km.package.km
    documented = {
        MaterialMasterPlant: {
            "is_discontinued": "int", "current_valuated_stock_quantity": "float",
            "safety_stock_quantity": "float", "material_id": "str", "plant_id": "str",
        },
        Plant: {"country": "str"},
        PlannedSupply: {"is_firm_order": "int", "order_quantity": "float", "order_finish_date": "datetime"},
        PurchaseScheduleLine: {
            "expected_delivery_date": "datetime", "received_quantity": "float", "expected_quantity": "float",
        },
        PurchaseDocumentLine: {"is_canceled": "int"},
        PurchaseDocument: {"is_canceled": "int"},
        Vendor: {"is_internal_vendor": "int"},
    }
    for object_type, fields in documented.items():
        for name, value_type in fields.items():
            field = getattr(object_type.fields, name)
            assert isinstance(field, Field) and field.value_type == value_type, (object_type, name)
    assert isinstance(MaterialMasterPlant.relations.plant, ToOneRelation)
    assert isinstance(MaterialMasterPlant.relations.planned_supplies, ToManyRelation)
    assert isinstance(PurchaseDocument.relations.vendor, ToOneRelation)
    assert isinstance(PurchaseDocumentLine.relations.header, ToOneRelation)
    assert isinstance(PurchaseScheduleLine.relations.purchase_document_line, ToOneRelation)
    assert all(km.all[name] for name in USED), "every used object type has data"


# ---------------------------------------------------------------------------
# 1. Below safety stock, without near-term firm supply
# ---------------------------------------------------------------------------


def run_at_risk(client, as_of):
    """The documented query, as written."""
    from generated.inventory import MaterialMasterPlant, PlannedSupply, Plant

    horizon = as_of + timedelta(days=14)

    stock = MaterialMasterPlant.fields
    relations = MaterialMasterPlant.relations
    supply = PlannedSupply.fields

    at_risk = (
        client.objects(MaterialMasterPlant)
        .where(
            stock.is_discontinued.eq(0)
            & stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)
            & relations.plant.has(Plant.fields.country.eq("DE"))
            & ~relations.planned_supplies.any(
                supply.is_firm_order.eq(1)
                & supply.order_quantity.gt(0)
                & supply.order_finish_date.gte(as_of)
                & supply.order_finish_date.lt(horizon)
            )
        )
        .fetch_page(page_size=100)
    )
    return at_risk


def covering(supply, as_of):
    as_of = moment(as_of)
    horizon = as_of + timedelta(days=14)
    return (
        supply.is_firm_order == 1
        and supply.order_quantity is not None and supply.order_quantity > 0
        and supply.order_finish_date is not None and as_of <= supply.order_finish_date < horizon
    )


def expected_at_risk(km, as_of):
    plants = by_key(km.all["Plant"])
    supplies = children(km.all["PlannedSupply"], "material_master_plant_id")
    return sorted(
        item.key for item in km.all["MaterialMasterPlant"]
        if item.is_discontinued == 0
        and item.current_valuated_stock_quantity is not None
        and item.safety_stock_quantity is not None
        and item.current_valuated_stock_quantity < item.safety_stock_quantity
        and item.plant_id in plants and plants[item.plant_id].country == "DE"
        and not any(covering(s, as_of) for s in supplies[item.key])
    )


def covered_case(km):
    """A below-safety-stock item and a date on which firm supply covers it."""
    supplies = children(km.all["PlannedSupply"], "material_master_plant_id")
    for item in km.all["MaterialMasterPlant"]:
        if item.key in expected_at_risk(km, date(1900, 1, 1)):
            for supply in supplies[item.key]:
                if covering(supply, supply.order_finish_date or date(1900, 1, 1)):
                    return item, supply.order_finish_date
    pytest.fail("The KM has no firm supply covering an item below safety stock.")


def test_below_safety_stock_without_firm_supply(km):
    from generated.inventory import MaterialMasterPlant

    covered_item, covered_on = covered_case(km)
    for as_of in (SPEC_DATE, covered_on):
        at_risk = run_at_risk(km.client, as_of)

        # A. A page of typed MaterialMasterPlant objects, not rows.
        assert_typed_page(at_risk, MaterialMasterPlant)

        # B. Each result satisfies the rule, verified by traversing its links.
        for item in at_risk.items:
            assert item.is_discontinued == 0
            assert item.current_valuated_stock_quantity < item.safety_stock_quantity
            assert item.links.plant.fetch().country == "DE"
            assert not any(covering(s, as_of) for s in all_items(item.links.planned_supplies))

        # B. And nothing that satisfies it is missing.
        expect_page(at_risk, expected_at_risk(km, as_of), 100)

    # B. A concrete case: on the day its firm supply arrives, the item is covered.
    assert covered_item.key in [i.key for i in run_at_risk(km.client, SPEC_DATE).items]
    assert covered_item.key not in [i.key for i in run_at_risk(km.client, covered_on).items]


# ---------------------------------------------------------------------------
# 2. Overdue, under-received schedules of active external purchases
# ---------------------------------------------------------------------------


def run_overdue(client, as_of):
    """The documented query, as written."""
    from generated.inventory import (
        PurchaseDocument,
        PurchaseDocumentLine,
        PurchaseScheduleLine,
        Vendor,
    )

    schedule = PurchaseScheduleLine.fields

    # A reusable predicate on purchase documents.
    external_purchase = (
        PurchaseDocument.fields.is_canceled.eq(0)
        & PurchaseDocument.relations.vendor.has(
            Vendor.fields.is_internal_vendor.eq(0)
        )
    )

    # Compose it into a predicate on purchase lines.
    active_external_line = (
        PurchaseDocumentLine.fields.is_canceled.eq(0)
        & PurchaseDocumentLine.relations.header.has(external_purchase)
    )

    overdue = (
        client.objects(PurchaseScheduleLine)
        .where(
            schedule.expected_delivery_date.lt(as_of)
            & schedule.received_quantity.lt(schedule.expected_quantity)
            & PurchaseScheduleLine.relations.purchase_document_line.has(
                active_external_line
            )
        )
        .order_by(schedule.expected_delivery_date.asc())
        .fetch_page(page_size=100)
    )
    return overdue, external_purchase, active_external_line


def external_documents(km):
    vendors = by_key(km.all["Vendor"])
    return {
        d.key for d in km.all["PurchaseDocument"]
        if d.is_canceled == 0 and d.vendor_id in vendors
        and vendors[d.vendor_id].is_internal_vendor == 0
    }


def active_external_lines(km):
    documents = external_documents(km)
    return {
        line.key for line in km.all["PurchaseDocumentLine"]
        if line.is_canceled == 0 and line.header_id in documents
    }


def expected_overdue(km, as_of):
    lines = active_external_lines(km)
    matches = [
        s for s in km.all["PurchaseScheduleLine"]
        if s.expected_delivery_date is not None and s.expected_delivery_date < moment(as_of)
        and s.received_quantity is not None and s.expected_quantity is not None
        and s.received_quantity < s.expected_quantity
        and s.purchase_document_line_id in lines
    ]
    return [s.key for s in sorted(matches, key=lambda s: (s.expected_delivery_date, s.key))]


def test_overdue_external_schedules(km):
    from generated.inventory import PurchaseDocument, PurchaseDocumentLine, PurchaseScheduleLine

    for as_of in (SPEC_DATE, date(2025, 1, 1)):
        overdue, external_purchase, active_external_line = run_overdue(km.client, as_of)

        # A. Typed schedule lines, earliest expected delivery first.
        assert_typed_page(overdue, PurchaseScheduleLine)
        dates = [(d.expected_delivery_date, d.key) for d in overdue.items]
        assert dates == sorted(dates)

        # B. Each result satisfies the rule along its relationship path.
        for delivery in overdue.items:
            assert delivery.expected_delivery_date < moment(as_of)
            assert delivery.received_quantity < delivery.expected_quantity
            line = delivery.links.purchase_document_line.fetch()
            assert line.is_canceled == 0
            header = line.links.header.fetch()
            assert header.is_canceled == 0
            assert header.links.vendor.fetch().is_internal_vendor == 0

        # B. And nothing is missing.
        expect_page(overdue, expected_overdue(km, as_of), 100)

        # B. The reusable predicates select exactly the external purchases and lines.
        documents = all_items(km.client.objects(PurchaseDocument).where(external_purchase))
        assert {d.key for d in documents} == external_documents(km)
        lines = all_items(km.client.objects(PurchaseDocumentLine).where(active_external_line))
        assert {line.key for line in lines} == active_external_lines(km)


# ---------------------------------------------------------------------------
# 3. Other plants that could supply the same material
# ---------------------------------------------------------------------------


def run_alternatives(client, material_plant_id):
    """The documented query, as written; returns (key, quantity above safety)."""
    from generated.inventory import MaterialMasterPlant

    stock = MaterialMasterPlant.fields

    target = client.objects(MaterialMasterPlant).get(material_plant_id)

    if target.material_id is None or target.plant_id is None:
        raise ValueError("The target requires material and plant references.")

    candidates = (
        client.objects(MaterialMasterPlant)
        .where(
            stock.material_id.eq(target.material_id)
            & stock.plant_id.ne(target.plant_id)
            & stock.is_discontinued.eq(0)
            & stock.current_valuated_stock_quantity.gt(stock.safety_stock_quantity)
        )
        .fetch_page(page_size=100)
    )

    result = []
    for candidate in candidates.items:
        quantity = candidate.current_valuated_stock_quantity
        safety_stock = candidate.safety_stock_quantity

        if quantity is None or safety_stock is None:
            continue

        quantity_above_safety = quantity - safety_stock
        result.append((candidate.key, quantity_above_safety))
    return target, candidates, result


def expected_alternatives(km, target):
    return sorted(
        (item.key, item.current_valuated_stock_quantity - item.safety_stock_quantity)
        for item in km.all["MaterialMasterPlant"]
        if item.material_id == target.material_id and item.plant_id != target.plant_id
        and item.is_discontinued == 0
        and item.current_valuated_stock_quantity is not None
        and item.safety_stock_quantity is not None
        and item.current_valuated_stock_quantity > item.safety_stock_quantity
    )


def test_alternative_sources(km):
    from generated.inventory import MaterialMasterPlant

    items = [i for i in km.all["MaterialMasterPlant"] if i.material_id and i.plant_id]
    ranked = sorted(items, key=lambda i: (-len(expected_alternatives(km, i)), i.key))
    targets = ranked[:3] + ranked[-1:]  # The richest cases and one without candidates.
    assert expected_alternatives(km, ranked[0]), "some material is stocked at several plants"

    for material_plant in targets:
        target, candidates, result = run_alternatives(km.client, material_plant.key)

        # A. The loaded target is the same object; candidates are typed objects.
        assert target == material_plant
        assert_typed_page(candidates, MaterialMasterPlant)

        # B. Each candidate qualifies, and the result is complete and exact.
        for candidate in candidates.items:
            assert candidate.material_id == target.material_id
            assert candidate.plant_id != target.plant_id
            assert candidate.is_discontinued == 0
            assert candidate.current_valuated_stock_quantity > candidate.safety_stock_quantity
        assert result == expected_alternatives(km, target)

    with pytest.raises(ObjectNotFoundError):
        run_alternatives(km.client, "NO-SUCH-MATERIAL-PLANT")


# ---------------------------------------------------------------------------
# Further predicate forms, compared with a plain-Python oracle
# ---------------------------------------------------------------------------


def conformance_cases(sdk):
    """Predicate forms beyond the documented questions, chosen to return data."""
    S, P, PS = sdk.MaterialMasterPlant.fields, sdk.Plant.fields, sdk.PlannedSupply.fields
    R = sdk.MaterialMasterPlant.relations
    Sch, L, D, V = (sdk.PurchaseScheduleLine.fields, sdk.PurchaseDocumentLine.fields,
                    sdk.PurchaseDocument.fields, sdk.Vendor.fields)
    below = S.current_valuated_stock_quantity.lt(S.safety_stock_quantity)
    canceled_external_line = L.is_canceled.eq(1) & sdk.PurchaseDocumentLine.relations.header.has(
        D.is_canceled.eq(1) & sdk.PurchaseDocument.relations.vendor.has(V.is_internal_vendor.eq(0)))
    Stock, Schedule, Vendor = sdk.MaterialMasterPlant, sdk.PurchaseScheduleLine, sdk.Vendor
    window = PS.order_finish_date.gte(date(2025, 1, 1)) & PS.order_finish_date.lt(date(2025, 3, 1))
    return {
        "field < field": (Stock, below, ()),
        "~(field < field)": (Stock, ~below, ()),
        "field >= value": (Stock, S.safety_stock_quantity.gte(50.0), ()),
        "ne str": (Stock, S.procurement_type.ne("F"), ()),
        "eq None": (Stock, S.safety_stock_quantity.eq(None), ()),
        "ne None": (Stock, S.safety_stock_quantity.ne(None), ()),
        "or": (Stock, S.is_discontinued.eq(1) | S.safety_stock_quantity.gte(80.0), ()),
        "has": (Stock, R.plant.has(P.plant_name.ne(None)), ()),
        "has()": (Stock, R.plant.has(), ()),
        "any()": (Stock, R.planned_supplies.any(), ()),
        "~any()": (Stock, ~R.planned_supplies.any(), ()),
        "any(date window)": (Stock, R.planned_supplies.any(window), ()),
        "~any(date window) & below": (Stock, below & ~R.planned_supplies.any(window), ()),
        "nested has x3": (Schedule, Schedule.relations.purchase_document_line.has(canceled_external_line), ()),
        "field < field (schedule)": (Schedule, Sch.received_quantity.lt(Sch.expected_quantity), ()),
        "order desc": (Schedule, Sch.expected_quantity.gt(0.0), (Sch.expected_delivery_date.desc(),)),
        "any() on vendor": (Vendor, Vendor.relations.purchase_documents.any(), ()),
        "~any() on vendor": (Vendor, ~Vendor.relations.purchase_documents.any(), ()),
        "is_in": (Stock, S.plant_id.is_in(["SAP_ECC::100::1000", "SAP_ECC::100::1300"]), ()),
        "between": (Stock, S.safety_stock_quantity.between(10.0, 50.0), ()),
        "like": (Stock, S.id.like("%::1000"), ()),
        "~like": (Stock, ~S.id.like("%00000001%"), ()),
        "~has": (Stock, ~R.plant.has(P.country.eq("DE")), ()),
        "lookup has": (Schedule, Schedule.relations.plant.has(P.plant_name.like("B%")), ()),
        "any(has) (BIND in PU)": (Stock, R.purchase_schedule_lines.any(
            sdk.PurchaseScheduleLine.relations.purchase_document_line.has(L.is_canceled.eq(1))), ()),
        "has(any) (PU through BIND)": (Schedule, Schedule.relations.material_master_plant.has(
            R.planned_supplies.any(PS.is_firm_order.eq(1))), ()),
        # Relation aggregates (Pull-Up functions), compared with the oracle's own
        # aggregation; PU_MEDIAN takes the upper middle value.
        "count(p) > 1": (Stock, R.planned_supplies.count(PS.is_firm_order.eq(1)).gt(1), ()),
        "avg > 50": (Stock, R.planned_supplies.avg(PS.order_quantity).gt(50.0), ()),
        "avg is null": (Stock, R.planned_supplies.avg(PS.order_quantity).eq(None), ()),
        "sum(p) > 100": (Stock, R.planned_supplies.sum(
            PS.order_quantity, PS.is_firm_order.eq(1)).gt(100.0), ()),
        "min < 20": (Stock, R.planned_supplies.min(PS.order_quantity).lt(20.0), ()),
        "max between": (Stock, R.planned_supplies.max(PS.order_quantity).between(60.0, 95.0), ()),
        "median > 50": (Stock, R.planned_supplies.median(PS.order_quantity).gt(50.0), ()),
        "latest finish": (Stock, R.planned_supplies.max(PS.order_finish_date).gte(date(2025, 6, 1)), ()),
        "count_distinct": (Stock, R.planned_supplies.count_distinct(PS.object_type_attribute).gte(1), ()),
        "sum < own field": (Stock, R.planned_supplies.sum(PS.order_quantity).lt(
            S.safety_stock_quantity), ()),
        "aggregate vs aggregate": (Stock, R.planned_supplies.sum(PS.order_quantity).gt(
            R.planned_supplies.max(PS.order_quantity)), ()),
        "has(count)": (Schedule, Schedule.relations.material_master_plant.has(
            R.planned_supplies.count().gte(2)), ()),
        "count(any) (PU in PU)": (sdk.Plant, sdk.Plant.relations.materials.count(
            R.planned_supplies.any(PS.is_firm_order.eq(1))).gte(30), ()),
        "order by count desc": (Stock, R.planned_supplies.count().gt(0),
                                (R.planned_supplies.count().desc(),)),
        "vendor documents": (Vendor, Vendor.relations.purchase_documents.count().gte(5), ()),
    }


def test_predicate_forms_match_the_oracle(km):
    population = {
        object_type.fields.object_type: km.all[object_type.__name__]
        for object_type in km.package.km if object_type.__name__ in USED
    }
    cases = conformance_cases(km.package)
    nonempty = 0
    for name, (object_type, predicate, order) in cases.items():
        before = len(km.exports)
        page = (
            km.client.objects(object_type).where(predicate).order_by(*order)
            .fetch_page(page_size=10_000)
        )
        assert len(km.exports) == before + 1, f"{name}: relations must not add requests"
        expected = [o.key for o in select(object_type, (predicate,), order, population)]
        assert [o.key for o in page.items] == expected, name
        nonempty += bool(page.items)
    assert nonempty >= len(cases) - 3


def test_each_documented_question_is_one_request_per_read(km):
    target = next(i for i in km.all["MaterialMasterPlant"] if i.material_id and i.plant_id)
    before = len(km.exports)
    run_at_risk(km.client, SPEC_DATE)
    assert len(km.exports) == before + 1
    run_overdue(km.client, SPEC_DATE)
    assert len(km.exports) == before + 2
    run_alternatives(km.client, target.key)  # get() plus one filtered page.
    assert len(km.exports) == before + 4
