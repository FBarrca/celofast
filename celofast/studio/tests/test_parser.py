import json
import unittest

from celofast.studio import TableNotFoundError, ViewFormatError
from celofast.studio.parser import ViewTableParser, load_serialized_content


class FakeView:
    def __init__(self, content):
        self._content = content

    def json_dict(self):
        return {"serialized_content": json.dumps(self._content)}


class ViewTableParserTests(unittest.TestCase):
    def setUp(self):
        self.view = FakeView(
            {
                "components": [
                    {"type": "text", "settings": {"name": "Ignore"}},
                    {
                        "type": "table",
                        "settings": {
                            "name": "Input",
                            "dataSources": [
                                {
                                    "attributes": [
                                        {
                                            "displayName": "Case ID",
                                            "pql": '"CASES"."ID"',
                                        },
                                        {
                                            "pql": "KPI(throughput)",
                                            "hide": True,
                                            "referencedEntity": {
                                                "id": "throughput",
                                                "type": "KPI",
                                            },
                                        },
                                    ],
                                    "filters": [
                                        {"pql": "active_cases", "isReferenced": True}
                                    ],
                                }
                            ],
                        },
                    },
                ]
            }
        )

    def test_parses_columns_filters_and_hidden_state(self):
        table = ViewTableParser(self.view).table("Input")

        self.assertEqual(table.name, "Input")
        self.assertEqual([column.name for column in table.columns], ["Case ID", "throughput"])
        self.assertTrue(table.columns[1].hidden)
        self.assertEqual(table.columns[1].referenced_entity["type"], "KPI")
        self.assertTrue(table.filters[0].is_referenced)

    def test_missing_table_has_specific_error(self):
        with self.assertRaises(TableNotFoundError):
            ViewTableParser(self.view).table("Event Log")

    def test_invalid_serialized_json_is_rejected(self):
        class InvalidView:
            serialized_content = "not-json"

        with self.assertRaises(ViewFormatError):
            load_serialized_content(InvalidView())


if __name__ == "__main__":
    unittest.main()
