"""Read table components from Celonis Views with the SaolaPy DataFrame API."""

from typing import Any, Iterable, Mapping, Optional, Sequence

from pycelonis.pql.data_frame import DataFrame
from saolapy.pql.base import PQL, PQLColumn, PQLFilter

from ..services.clients import get_celonis
from .context import read_view_variables, resolve_studio_context
from .exceptions import PqlResolutionError, ViewFormatError
from .parser import ViewTableParser
from .resolvers import default_resolver_chain


class CelonisViewReader:
    """Compile and execute PQL from tables configured in a published Studio View."""

    def __init__(
        self,
        *,
        view: Any,
        knowledge_model: Any,
        data_model: Any,
        variables: Optional[Mapping[str, Any]] = None,
    ):
        self.view = view
        self.knowledge_model = knowledge_model
        self.data_model = data_model
        self.variables = (
            dict(variables) if variables is not None else read_view_variables(view)
        )
        self.parser = ViewTableParser(view)
        self.resolver = default_resolver_chain(knowledge_model, self.variables)

    @classmethod
    def from_studio(
        cls,
        celonis: Any | None = None,
        *,
        space_id: str,
        package_id: str,
        view_key: str,
        knowledge_model_key: Optional[str] = None,
        data_model_id: Optional[str] = None,
        data_pool_id: Optional[str] = None,
        variables: Optional[Mapping[str, Any]] = None,
    ):
        """Resolve the required objects from Studio and construct a reader."""

        client = get_celonis() if celonis is None else celonis
        context = resolve_studio_context(
            client,
            space_id=space_id,
            package_id=package_id,
            view_key=view_key,
            knowledge_model_key=knowledge_model_key,
            data_model_id=data_model_id,
            data_pool_id=data_pool_id,
        )
        return cls(
            view=context.view,
            knowledge_model=context.knowledge_model,
            data_model=context.data_model,
            variables=variables,
        )

    def build_query(
        self,
        table_name: str,
        *,
        inherit_filters_from: Sequence[str] = (),
        extra_filters: Iterable[str] = (),
    ):
        """Build a PQL query from a View table without executing it."""

        table = self.parser.table(table_name)
        query = PQL(distinct=False, limit=None, offset=None)
        visible_columns = [column for column in table.columns if not column.hidden]
        if not visible_columns:
            raise ViewFormatError(
                "Table {!r} has no visible columns.".format(table_name)
            )

        output_names = set()
        for column in visible_columns:
            output_name = column.name
            if output_name in output_names:
                raise ViewFormatError(
                    "Table {!r} produces duplicate output column {!r}.".format(
                        table_name, output_name
                    )
                )
            output_names.add(output_name)
            query += PQLColumn(
                name=output_name,
                query=self._resolve_column_pql(column),
            )

        filter_pql = list(self.resolved_filters(table.name))
        for inherited_table in inherit_filters_from:
            filter_pql.extend(self.resolved_filters(inherited_table))
        filter_pql.extend(self.resolver.resolve(value) for value in extra_filters)

        for pql in filter_pql:
            query += PQLFilter(query=pql)
        return query

    def resolved_filters(self, table_name: str):
        """Return resolved filter PQL for a table, without creating a query."""

        table = self.parser.table(table_name)
        for view_filter in table.filters:
            pql = view_filter.pql
            if view_filter.is_referenced:
                try:
                    pql = self.knowledge_model.get_filter(pql.strip()).pql
                except Exception as exc:
                    raise PqlResolutionError(
                        "Referenced filter {!r} could not be resolved.".format(
                            view_filter.pql.strip()
                        )
                    ) from exc
            yield self.resolver.resolve(pql)

    def read(
        self,
        table_name: str,
        *,
        inherit_filters_from: Sequence[str] = (),
        extra_filters: Iterable[str] = (),
    ):
        """Build and execute the PQL query for one configured View table."""

        query = self.build_query(
            table_name,
            inherit_filters_from=inherit_filters_from,
            extra_filters=extra_filters,
        )
        return self.execute(query)

    def execute(self, query):
        """Let SaolaPy validate and execute a generated PQL query."""

        return DataFrame.from_pql(query, data_model=self.data_model).to_pandas()

    def _resolve_column_pql(self, column) -> str:
        pql = column.pql
        referenced = column.referenced_entity
        if str(referenced.get("type", "")).upper() == "KPI":
            kpi_id = referenced.get("id")
            if not kpi_id:
                raise PqlResolutionError(
                    "KPI-backed column {!r} has no KPI id.".format(column.name)
                )
            try:
                pql = self.knowledge_model.get_kpi(kpi_id).pql
            except Exception as exc:
                raise PqlResolutionError(
                    "KPI {!r} for column {!r} could not be resolved.".format(
                        kpi_id, column.name
                    )
                ) from exc
        return self.resolver.resolve(pql)
