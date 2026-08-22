import json
import unittest
from types import SimpleNamespace
from typing import cast

from pycelonis.celonis import Celonis

from celofast.studio import ContextResolutionError, resolve_studio_context
from celofast.studio.context import read_view_variables


class Collection:
    def __init__(self, values):
        self.values = values

    def find(self, key, search_attribute=None):
        if search_attribute not in (None, "key"):
            raise KeyError(search_attribute)
        return self.values[key]


class Node:
    def __init__(self, content):
        self.serialized_content = json.dumps(content)
        self.id: str | None = None


class ContextTests(unittest.TestCase):
    def make_celonis(self):
        view = Node({"metadata": {"knowledgeModelKey": "orders-km"}})
        knowledge_model = Node({"dataModelId": "${{orders_dm}}"})
        knowledge_model.id = "km-id"
        data_model = SimpleNamespace(id="dm-id")
        data_pool = SimpleNamespace(
            id="pool-id",
            get_data_models=lambda: [data_model],
            get_data_model=lambda model_id: data_model
            if model_id == "dm-id"
            else None,
        )
        package = SimpleNamespace(
            get_content_nodes=lambda: Collection({"input-data": view}),
            get_knowledge_models=lambda: Collection({"orders-km": knowledge_model}),
            get_variables=lambda: Collection(
                {"orders_dm": SimpleNamespace(value="dm-id")}
            ),
        )
        space = SimpleNamespace(get_package=lambda package_id: package)
        celonis = SimpleNamespace(
            studio=SimpleNamespace(get_space=lambda space_id: space),
            data_integration=SimpleNamespace(get_data_pools=lambda: [data_pool]),
        )
        return celonis, view, knowledge_model, data_model, data_pool

    def test_resolves_context_from_published_metadata(self):
        celonis, view, knowledge_model, data_model, data_pool = self.make_celonis()

        context = resolve_studio_context(
            cast(Celonis, celonis),
            space_id="space-id",
            package_id="package-id",
            view_key="input-data",
        )

        self.assertIs(context.view, view)
        self.assertIs(context.knowledge_model, knowledge_model)
        self.assertIs(context.data_model, data_model)
        self.assertIs(context.data_pool, data_pool)

    def test_missing_knowledge_model_metadata_is_rejected(self):
        celonis, view, _, _, _ = self.make_celonis()
        view.serialized_content = json.dumps({"metadata": {}})

        with self.assertRaisesRegex(ContextResolutionError, "does not identify"):
            resolve_studio_context(
                cast(Celonis, celonis),
                space_id="space-id",
                package_id="package-id",
                view_key="input-data",
            )

    def test_reads_object_and_dictionary_variable_definitions(self):
        view = SimpleNamespace(
            input_variable_definitions=[
                SimpleNamespace(key="days", default_value="30"),
                {"key": "region", "defaultValue": "EMEA"},
            ]
        )

        self.assertEqual(
            read_view_variables(view),
            {"days": "30", "region": "EMEA"},
        )


if __name__ == "__main__":
    unittest.main()
