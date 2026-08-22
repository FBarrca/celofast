"""Query a real Knowledge Model with pycelonis using the credentials in ``.env``."""

from __future__ import annotations

from celofast import KnowledgeModelService


KNOWLEDGE_MODEL = (
    "9f7cc225-132d-49e7-8b0d-b626b1000b41."
    "c1721b64-5f2c-4311-99ee-8177f0839c92."
    "test:perspective_celonis_InventoryManagement KM"
)
ATTRIBUTE_COLUMNS = {
    "customer_city": '"o_celonis_Customer"."City"',
    "customer_postal_code": '"o_celonis_Customer"."PostalCode"',
    "delivery_line_number": '"o_celonis_DeliveryLine"."LineNumber"',
}


def get_attributes():
    """Find the configured KM and return ten rows of its attributes."""
    service = KnowledgeModelService(KNOWLEDGE_MODEL)
    return service.knowledge_model, service.query(ATTRIBUTE_COLUMNS, limit=10)


def main() -> None:
    knowledge_model, dataframe = get_attributes()
    print(f"Knowledge Model: {knowledge_model.name} ({knowledge_model.root_with_key})")
    print(dataframe.to_string(index=False))
    print(f"\nReturned {len(dataframe)} row(s) and {len(dataframe.columns)} attribute(s).")


if __name__ == "__main__":
    main()
