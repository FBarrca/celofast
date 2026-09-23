"""Run three inventory business questions against the live Inventory KM.

Generate the offline definitions before the first run or after KM changes:
    uv run celofast km pull inventory
    uv run python main.py
"""

from datetime import date, timedelta

from celofast import CeloFast, KnowledgeModelClient
from celofast.sdk import ObjectPage
from generated.inventory import (
    MaterialMasterPlant,
    Plant,
    PlannedSupply,
    PurchaseDocument,
    PurchaseDocumentLine,
    PurchaseScheduleLine,
    Vendor,
    km as inventory,
)

AS_OF = date(2026, 9, 23)  # Example planning date.

# import logging
# # Enable to show the PQL queries in the logs
# logging.basicConfig()
# logging.getLogger("celofast.km").setLevel(logging.DEBUG)


def at_risk_materials(client: KnowledgeModelClient, as_of: date):
    """German, non-discontinued material-plants below safety stock with no firm supply soon."""
    horizon = as_of + timedelta(days=14)

    stock = MaterialMasterPlant.fields
    relations = MaterialMasterPlant.relations
    supply = PlannedSupply.fields

    return (
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


def overdue_external_schedules(client, as_of: date, *, use_canceled_flag: bool = False):
    """Overdue, under-received schedules of purchases from external vendors.

    In the Inventory KM every purchase document and line has IsCanceled = 1,
    including fully received ones, so filtering on the flag always returns
    nothing. It is therefore off by default; pass use_canceled_flag=True once
    the flag is populated correctly to exclude canceled lines and documents.
    """
    schedule = PurchaseScheduleLine.fields

    # A reusable predicate on purchase documents.
    external_purchase = PurchaseDocument.relations.vendor.has(
        Vendor.fields.is_internal_vendor.eq(0)
    )
    if use_canceled_flag:
        external_purchase = PurchaseDocument.fields.is_canceled.eq(0) & external_purchase

    # Compose it into a predicate on purchase lines.
    active_external_line = PurchaseDocumentLine.relations.header.has(external_purchase)
    if use_canceled_flag:
        active_external_line = PurchaseDocumentLine.fields.is_canceled.eq(0) & active_external_line

    return (
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


def alternative_sources(client, material_plant_id: str):
    """Other plants holding the same material above safety stock."""
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

        result.append((candidate, quantity - safety_stock))
    return target, result


def main() -> None:
    source = inventory.source
    cf = CeloFast(source.space_id, source.package_id, mode=source.mode)
    client = cf.km(inventory)

    print(f"1. Below safety stock in DE, no firm supply by {AS_OF + timedelta(days=14)}")
    at_risk = at_risk_materials(client, AS_OF)
    print(f"   {len(at_risk.items)} on this page (more pages: {bool(at_risk.has_more)})")
    for item in at_risk.items[:5]:
        print(
            f"   {item.key}: stock {item.current_valuated_stock_quantity} "
            f"< safety {item.safety_stock_quantity}"
        )

    print(f"\n2. Overdue, under-received external schedules as of {AS_OF}")
    overdue = overdue_external_schedules(client, AS_OF)
    print(f"   {len(overdue.items)} on this page (more pages: {bool(overdue.has_more)})")
    for delivery in overdue.items[:5]:
        print(f"   {delivery.key}: expected {delivery.expected_delivery_date}")

    print("\n3. Alternative plants for the same material")
    # Use the first at-risk item as the target; fall back to any stocked one.
    seed = (
        at_risk.items[0]
        if at_risk.items
        else client.objects(MaterialMasterPlant).fetch_page(page_size=1).items[0]
    )
    target, alternatives = alternative_sources(client, seed.key)
    print(f"   target {target.key} (material {target.material_id}, plant {target.plant_id})")
    if not alternatives:
        print("   no other plant holds this material above safety stock")
    for candidate, above in alternatives[:5]:
        print(f"   {candidate.key}: {above} above safety stock")


if __name__ == "__main__":
    main()
