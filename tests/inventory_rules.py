"""Inventory business rules written against the generated object SDK.

Each function is one realistic use case built on the Inventory Management KM,
exercised by test_inventory_rules.py. The object types and relations come from
inventory-objects.toml; the tests import whichever ``generated.inventory`` they
put first on the path (a fixture package offline, the pulled package live).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from celofast import KnowledgeModelClient
from celofast.sdk import ObjectPage
from generated.inventory import (
    MaterialMasterPlant,
    PlannedSupply,
    Plant,
    PurchaseDocument,
    PurchaseDocumentLine,
    PurchaseScheduleLine,
    Vendor,
)

stock = MaterialMasterPlant.fields
relations = MaterialMasterPlant.relations
supply = PlannedSupply.fields
schedule = PurchaseScheduleLine.fields


def below_safety_stock_without_firm_supply(
    client: KnowledgeModelClient,
    as_of: date,
    *,
    country: str = "DE",
    horizon_days: int = 14,
    page_size: int = 100,
) -> ObjectPage[MaterialMasterPlant]:
    """Non-discontinued material-plants in ``country`` below safety stock, with
    no positive firm planned supply finishing in the next ``horizon_days``.

    A screening rule, not proof of a shortage: it checks this planned-supply
    condition, not every possible source of replenishment.
    """
    horizon = as_of + timedelta(days=horizon_days)
    return (
        client.objects(MaterialMasterPlant)
        .where(
            stock.is_discontinued.eq(0)
            & stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)
            & relations.plant.has(Plant.fields.country.eq(country))
            & ~relations.planned_supplies.any(
                supply.is_firm_order.eq(1)
                & supply.order_quantity.gt(0)
                & supply.order_finish_date.gte(as_of)
                & supply.order_finish_date.lt(horizon)
            )
        )
        .fetch_page(page_size=page_size)
    )


# A reusable predicate on purchase documents: not canceled, external vendor.
external_purchase = PurchaseDocument.fields.is_canceled.eq(0) & PurchaseDocument.relations.vendor.has(
    Vendor.fields.is_internal_vendor.eq(0)
)

# Composed into a predicate on purchase lines.
active_external_line = PurchaseDocumentLine.fields.is_canceled.eq(
    0
) & PurchaseDocumentLine.relations.header.has(external_purchase)


def overdue_external_schedules(
    client: KnowledgeModelClient, as_of: date, *, page_size: int = 100
) -> ObjectPage[PurchaseScheduleLine]:
    """Overdue, not fully received schedule lines of active external purchases,
    earliest expected delivery first."""
    return (
        client.objects(PurchaseScheduleLine)
        .where(
            schedule.expected_delivery_date.lt(as_of)
            & schedule.received_quantity.lt(schedule.expected_quantity)
            & PurchaseScheduleLine.relations.purchase_document_line.has(active_external_line)
        )
        .order_by(schedule.expected_delivery_date.asc())
        .fetch_page(page_size=page_size)
    )


@dataclass(frozen=True)
class Candidate:
    """Another plant's stock of the same material, above its safety stock."""

    material_plant: MaterialMasterPlant
    quantity_above_safety: float


def alternative_sources(
    client: KnowledgeModelClient, material_plant_id: str, *, page_size: int = 100
) -> list[Candidate]:
    """Other plants holding the target's material above their safety stock."""
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
        .fetch_page(page_size=page_size)
    )

    result = []
    for candidate in candidates.items:
        quantity = candidate.current_valuated_stock_quantity
        safety_stock = candidate.safety_stock_quantity
        if quantity is None or safety_stock is None:
            continue
        result.append(Candidate(candidate, quantity - safety_stock))
    return result
