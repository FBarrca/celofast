"""Read live Inventory KM records and a configured View table.

Generate the offline definitions before the first run or after KM changes:
    uv run celofast km pull inventory
    uv run python main.py
"""

from celofast import CeloFast
from generated.inventory import km as inventory


VIEW_SPACE_ID = "9df26518-1b95-45d7-ac8e-07d4497de48b"
VIEW_PACKAGE_ID = "9832f9de-45be-4edf-b07a-34fd5bb8462a"
VIEW_KEY = "d4f44e9f_6146_44a1_8587_ba1606616c0a-view"
TABLE_ID = "table-94060354-64b4-4a25-a990-fc5c02d9c837"


def main() -> None:
    """Use offline fields with a live handle; propagate native query errors."""
    source = inventory.capture.source
    celofast = CeloFast(source.space_id, source.package_id, mode=source.mode)
    km = celofast.km(inventory)
    plant = inventory.records.o_celonis_plant
    query = (
        km.select(plant)
        .where(plant.country.eq("DE"))
        .order_by(plant.plantnumber.asc())
    )
    km_result = query.execute(limit=5, distinct=True)
    print(f"Inventory plants in Germany ({len(km_result)} rows)")
    print(km_result.to_string(index=False))

    view_connection = CeloFast(VIEW_SPACE_ID, VIEW_PACKAGE_ID)
    table = view_connection.view(VIEW_KEY).table(TABLE_ID)
    print("\nQuery exported from the View table")
    print(table.to_query())

    table_result = table.execute(limit=5)
    print(f"\nView table result ({len(table_result)} rows)")
    print(table_result.to_string(index=False))


if __name__ == "__main__":
    main()
