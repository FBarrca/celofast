"""Small end-to-end showcase of the CeloFast public API."""

from celofast import CeloFast, QueryDefinition


SPACE_ID = "9f7cc225-132d-49e7-8b0d-b626b1000b41"
PACKAGE_ID = "c1721b64-5f2c-4311-99ee-8177f0839c92"
KNOWLEDGE_MODEL_KEY = "dm_test_perspective_celonis_inventorymanagement-km"
VIEW_KEY = "management-dashboard-caro-joan-test-"
TABLE_NAME = "Supplier Performance"


def main() -> None:
    """Run a small live showcase against the hard-coded Studio resources.

    The example demonstrates both supported entry points: a dictionary query
    executed directly against a Knowledge Model and a typed View table whose
    native query is exported before execution.  It expects the normal Celonis
    OAuth settings (``CELONIS_URL``, ``OAUTH_CLIENT_ID``,
    ``OAUTH_CLIENT_SECRET``, and ``OAUTH_SCOPES``) to be available to
    :func:`celofast.get_celonis`; Space, Package, KM, View, and table selectors
    are intentionally kept as readable constants in this file.

    Raises:
        Exception: Native authentication, resource-resolution, query, and
            execution errors are allowed to propagate so the showcase exposes
            the original PyCelonis/SaolaPy diagnostics.
    """
    celofast = CeloFast(SPACE_ID, PACKAGE_ID)

    query: QueryDefinition = {
        "columns": {
            "Supplier": '"o_celonis_Vendor"."SupplierNumberNameConcat"',
            "Purchase Order Value": (
                'KPI("IM_PurchaseDocumentLine_PurchaseDocumentLineValue")'
            ),
        },
        "order_by": [
            {
                "pql": 'KPI("IM_PurchaseDocumentLine_PurchaseDocumentLineValue")',
                "ascending": False,
            }
        ],
    }

    km_result = celofast.km(KNOWLEDGE_MODEL_KEY).execute(query, limit=5)
    print("Direct Knowledge Model query")
    print(km_result.to_string(index=False))

    table = celofast.view(VIEW_KEY).table(TABLE_NAME)
    print("\nQuery exported from the View table")
    print(table.to_query())

    table_result = table.execute(limit=5)
    print("\nView table result")
    print(table_result.to_string(index=False))


if __name__ == "__main__":
    main()
