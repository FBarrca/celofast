import unittest
from types import SimpleNamespace
from typing import cast

from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel

from celofast.studio import PqlResolutionError
from celofast.studio.resolvers import (
    KpiResolver,
    RecordAttributeResolver,
    ResolverChain,
    VariableResolver,
)


class FakeKnowledgeModel:
    def __init__(self):
        self.kpis = {
            "outer": 'KPI("inner") + 1',
            "inner": '"Orders"."VALUE"',
        }
        attribute = SimpleNamespace(
            id="VALUE",
            pql='COALESCE("RAW"."VALUE", 0)',
            auto_generated=False,
        )
        self.content = SimpleNamespace(
            records=[SimpleNamespace(id="Orders", attributes=[attribute])]
        )

    def get_kpi(self, key):
        return SimpleNamespace(pql=self.kpis[key])

    def get_content(self):
        return self.content


class ResolverTests(unittest.TestCase):
    def test_chain_resolves_nested_kpi_record_attribute_and_variable(self):
        km = cast(KnowledgeModel, FakeKnowledgeModel())
        chain = ResolverChain(
            [KpiResolver(km), RecordAttributeResolver(km), VariableResolver({"days": 7})]
        )

        result = chain.resolve('KPI("outer") + ${days}')

        self.assertEqual(result, '((COALESCE("RAW"."VALUE", 0)) + 1) + 7')

    def test_variables_inside_comments_are_not_replaced(self):
        resolver = VariableResolver({"days": 7})
        pql = "${days} -- ${missing}\n/* ${also_missing} */ + 1"

        self.assertEqual(
            resolver.resolve(pql),
            "7 -- ${missing}\n/* ${also_missing} */ + 1",
        )

    def test_missing_variable_fails_clearly(self):
        with self.assertRaisesRegex(PqlResolutionError, "Unresolved PQL variable"):
            VariableResolver({}).resolve("${missing}")

    def test_missing_kpi_fails_instead_of_broadening_query(self):
        with self.assertRaisesRegex(PqlResolutionError, "could not be resolved"):
            KpiResolver(cast(KnowledgeModel, FakeKnowledgeModel())).resolve("KPI(unknown)")


if __name__ == "__main__":
    unittest.main()
