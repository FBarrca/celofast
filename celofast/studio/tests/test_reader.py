import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from celofast.studio import (
    CelonisViewReader,
    PqlResolutionError,
    ViewFormatError,
)


class FakeView:
    input_variable_definitions = [SimpleNamespace(key="days", default_value="30")]

    def __init__(self):
        self.content = {
            "components": [
                {
                    "type": "table",
                    "settings": {
                        "name": "Input",
                        "dataSources": [
                            {
                                "attributes": [
                                    {"displayName": "id", "pql": '"Cases"."ID"'},
                                    {
                                        "displayName": "target",
                                        "pql": "KPI(target_kpi)",
                                        "referencedEntity": {
                                            "type": "KPI",
                                            "id": "target_kpi",
                                        },
                                    },
                                    {
                                        "displayName": "Hidden",
                                        "pql": "SHOULD_NOT_APPEAR()",
                                        "hide": True,
                                    },
                                ],
                                "filters": [
                                    {"pql": "case_filter", "isReferenced": True}
                                ],
                            }
                        ],
                    },
                },
                {
                    "type": "table",
                    "settings": {
                        "name": "Event Log",
                        "dataSources": [
                            {
                                "attributes": [
                                    {"displayName": "activity", "pql": '"Events"."NAME"'},
                                    {"displayName": "time", "pql": '"Events"."TIME"'},
                                ],
                                "filters": [{"pql": "${days} > 0", "isReferenced": False}],
                            }
                        ],
                    },
                },
            ]
        }

    def json_dict(self):
        return {"serialized_content": json.dumps(self.content)}


class FakeKnowledgeModel:
    def get_content(self):
        return SimpleNamespace(records=[])

    def get_kpi(self, key):
        if key != "target_kpi":
            raise KeyError(key)
        return SimpleNamespace(pql='"Cases"."TARGET"')

    def get_filter(self, key):
        if key != "case_filter":
            raise KeyError(key)
        return SimpleNamespace(pql='"Cases"."ACTIVE" = 1')


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.km = FakeKnowledgeModel()
        self.data_model = object()
        self.reader = CelonisViewReader(
            view=FakeView(),
            knowledge_model=self.km,
            data_model=self.data_model,
        )

    def test_build_query_uses_visible_columns_and_resolves_references(self):
        query = self.reader.build_query("Input")

        self.assertEqual(
            [(column.name, column.query) for column in query.columns],
            [("id", '"Cases"."ID"'), ("target", '"Cases"."TARGET"')],
        )
        self.assertEqual(
            [query_filter.query for query_filter in query.filters],
            ['"Cases"."ACTIVE" = 1'],
        )

    def test_event_query_can_inherit_input_filters(self):
        query = self.reader.build_query(
            "Event Log",
            inherit_filters_from=("Input",),
            extra_filters=('"Events"."VALID" = 1',),
        )

        self.assertEqual(
            [(column.name, column.query) for column in query.columns],
            [("activity", '"Events"."NAME"'), ("time", '"Events"."TIME"')],
        )
        self.assertEqual(
            [query_filter.query for query_filter in query.filters],
            ["30 > 0", '"Cases"."ACTIVE" = 1', '"Events"."VALID" = 1'],
        )

    def test_read_executes_with_the_supplied_models(self):
        lazy_frame = MagicMock()
        lazy_frame.to_pandas.return_value = {"rows": 2}

        with patch(
            "celofast.studio.reader.DataFrame.from_pql",
            return_value=lazy_frame,
        ) as from_pql:
            result = self.reader.read("Input")

        self.assertEqual(result["rows"], 2)
        query = from_pql.call_args.args[0]
        self.assertEqual([column.name for column in query.columns], ["id", "target"])
        from_pql.assert_called_once_with(query, data_model=self.data_model)
        lazy_frame.to_pandas.assert_called_once_with()

    def test_missing_referenced_filter_is_not_silently_skipped(self):
        self.reader.parser._content["components"][0]["settings"]["dataSources"][0][
            "filters"
        ][0]["pql"] = "unknown_filter"

        with self.assertRaisesRegex(PqlResolutionError, "unknown_filter"):
            self.reader.build_query("Input")

    def test_duplicate_studio_names_are_rejected(self):
        attributes = self.reader.parser._content["components"][0]["settings"][
            "dataSources"
        ][0]["attributes"]
        attributes.append({"displayName": "id", "pql": '"Cases"."OTHER_ID"'})

        with self.assertRaisesRegex(ViewFormatError, "duplicate output column 'id'"):
            self.reader.build_query("Input")

    def test_saolapy_errors_are_preserved(self):
        with patch(
            "celofast.studio.reader.DataFrame.from_pql",
            side_effect=RuntimeError("service unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "service unavailable"):
                self.reader.read("Input")

    def test_from_studio_uses_celofast_client_factory_when_client_is_omitted(self):
        context = SimpleNamespace(
            view=FakeView(),
            knowledge_model=self.km,
            data_model=self.data_model,
        )
        client = object()

        with (
            patch("celofast.studio.reader.get_celonis", return_value=client) as get_client,
            patch(
                "celofast.studio.reader.resolve_studio_context",
                return_value=context,
            ) as resolve_context,
        ):
            reader = CelonisViewReader.from_studio(
                space_id="space-id",
                package_id="package-id",
                view_key="Input",
            )

        self.assertIsInstance(reader, CelonisViewReader)
        get_client.assert_called_once_with()
        resolve_context.assert_called_once_with(
            client,
            space_id="space-id",
            package_id="package-id",
            view_key="Input",
            knowledge_model_key=None,
            data_model_id=None,
            data_pool_id=None,
        )


if __name__ == "__main__":
    unittest.main()
