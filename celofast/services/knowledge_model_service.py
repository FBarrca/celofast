"""Reusable Celonis Knowledge Model query and export service.

The service keeps KM access independent from any job or optimization code. It
supports the regular query endpoint for smaller results and the asynchronous
Parquet export endpoint for larger results.
"""

import asyncio
import functools
import json
import logging
import os
import time
from typing import Union

import numpy as np
import pandas as pd
import yaml
from celofast.services.phoenix_client import PhoenixClientBase, PhoenixExternalClient
from celofast.services.semantic_layer_client import (
    DataModelTransport,
    ExportStatus,
    KnowledgeModelQueryRequest,
    MultiStatementQueryResult,
    ProxyExportTypeV2,
    ProxyQueryResponseTransportV2,
    ProxyTableResultV2,
    QueryExportRequestTransport,
    QueryExportStatusTransport,
    SemanticLayerClient,
    SemanticLayerClientBase,
    SemanticLayerExternalClient,
)
from pycelonis.service.semantic_layer.service import (
    ExportKnowledgeModelByRootWithKeyRequest,
    ExportStatusKnowledgeModelByRootWithKeyRequest,
    ProxyDataExportStatusResponseV2,
    ProxyExportStatusV2,
)
from pycelonis.service.semantic_layer.service import ProxyExportTypeV2 as PyCelonisExportType
from pycelonis.service.semantic_layer.service import QueryContext, SemanticLayerService
from pycelonis_core.client.client import Client
from pydantic import BaseModel, Field, model_validator
from python_core_ems.exception import BatchQueryExportException
from python_core_internal_client import PythonCoreBaseModel
from python_core_internal_client.settings import internal_client_settings
from saolapy.pql.base import PQL

logger = logging.getLogger(__name__)


def _external_headers(api_token: Union[str, None] = None, key_type: Union[str, None] = None) -> dict[str, str]:
    """Build Celonis external API headers from explicit values or environment variables."""
    token = api_token or os.environ.get("CELONIS_API_TOKEN")
    if not token:
        raise RuntimeError("CELONIS_API_TOKEN must be provided to use the external Celonis clients.")
    resolved_key_type = key_type or ("Bearer" if os.environ.get("CELONIS_KEY_TYPE") == "USER_KEY" else "AppKey")
    return {"Authorization": f"{resolved_key_type} {token}"}


@functools.cache
def get_internal_semantic_layer_client() -> SemanticLayerClient:
    if "semantic-layer" not in internal_client_settings.celonis.services:
        raise RuntimeError("Semantic Layer service is not configured in internal client settings.")
    return SemanticLayerClient(base_url=internal_client_settings.celonis.services["semantic-layer"].url)


@functools.cache
def get_semantic_layer_client(
    base_url: Union[str, None] = None,
    api_token: Union[str, None] = None,
    key_type: Union[str, None] = None,
) -> SemanticLayerClientBase:
    """Return a cached external Semantic Layer client.

    ``base_url`` should be the Celonis tenant URL without ``/semantic-layer``;
    callers may pass explicit credentials for library use, otherwise the
    ``CELONIS_URL``, ``CELONIS_API_TOKEN``, and ``CELONIS_KEY_TYPE`` environment
    variables are used.
    """
    resolved_base_url = (base_url or os.environ.get("CELONIS_URL", "")).strip("/")
    if not resolved_base_url:
        raise RuntimeError("CELONIS_URL must be provided to use the external Semantic Layer client.")
    return SemanticLayerExternalClient(
        base_url=resolved_base_url + "/semantic-layer",
        headers=_external_headers(api_token, key_type),
    )


@functools.cache
def get_phoenix_client(
    base_url: Union[str, None] = None,
    api_token: Union[str, None] = None,
    key_type: Union[str, None] = None,
) -> PhoenixClientBase:
    """Return a cached external Phoenix client for augmented-attribute writes."""
    resolved_base_url = (base_url or os.environ.get("CELONIS_URL", "")).strip("/")
    if not resolved_base_url:
        raise RuntimeError("CELONIS_URL must be provided to use the external Phoenix client.")
    return PhoenixExternalClient(
        base_url=resolved_base_url + "/phoenix",
        headers=_external_headers(api_token, key_type),
    )


class ContentwithFormat(PythonCoreBaseModel):
    id: str

    def to_dict(self, exclude: Union[set[str], None] = None, exclude_none: bool = False) -> dict:
        fields = self.model_fields.keys()
        content_dict = {}
        for field in fields:
            if exclude is not None and field in exclude:
                continue
            content = getattr(self, field)
            if content is None or content == "nan":
                if exclude_none:
                    continue
                content = ""
            content_dict[field] = content
        return content_dict

    def to_yaml(self, exclude: Union[set[str], None] = None) -> str:
        content_dict = self.to_dict(exclude)
        return yaml.dump(content_dict)

    def to_json(self, exclude: Union[set[str], None] = None) -> str:
        content_dict = self.to_dict(exclude)
        return json.dumps(content_dict)


class Variable(ContentwithFormat):
    id: str
    display_name: str
    value: str
    description: Union[str, None] = None
    internal_note: Union[str, None] = None

    @model_validator(mode="before")
    def convert_datetimes(cls, values: dict) -> dict:  # pylint: disable=no-self-argument
        for key, value in values.items():
            if key == "value" and not isinstance(value, str):
                values[key] = str(value)
        return values


class EventLog(ContentwithFormat):
    id: str
    display_name: str
    pql: str
    autogenerated: Union[bool, None] = None
    record_id: Union[str, None] = None
    default_event_log: Union[bool, None] = False
    internal_note: Union[str, None] = None
    description: Union[str, None] = None


class EventLogMetadata(PythonCoreBaseModel):
    event_logs: list[EventLog]


class Trigger(BaseModel):
    id: str
    display_name: str = Field(..., alias="displayName")
    filter_ids: list[str] = Field(..., alias="filterIds")
    type: str  # this may evolve to an enum later, but TBD


class PQLAttribute(ContentwithFormat):
    id: str
    display_name: str
    pql: str
    description: Union[str, None] = None
    internal_note: Union[str, None] = None
    global_filter: Union[bool, None] = Field(default=None, alias="global")
    column_type: Union[str, None] = None
    short_display_name: Union[str, None] = None
    format: Union[str, None] = None
    unit: Union[str, None] = None

    @model_validator(mode="before")
    def convert_datetimes(cls, values: dict) -> dict:  # pylint: disable=no-self-argument
        for key, value in values.items():
            if key == "pql" and not isinstance(value, str):
                values[key] = str(value)
        return values

    def get_full_id(self) -> str:
        return self.id


class PQLKpiAttribute(PQLAttribute):
    @staticmethod
    def from_pql_attribute(pql_attribute: PQLAttribute):
        return PQLKpiAttribute(**pql_attribute.model_dump())


class Record(PythonCoreBaseModel):
    id: str
    display_name: str
    description: Union[str, None] = None
    attributes: list[PQLAttribute]
    triggers: Union[list[Trigger], None] = None


class KnowledgeModel(PythonCoreBaseModel):
    data_model_id: str = Field(default="")
    km_id: Union[str, None] = None
    root_with_key: Union[str, None] = None
    draft_id: Union[str, None] = None
    records: list[Record] = []
    kpis: list[PQLAttribute] = []
    filters: list[PQLAttribute] = []
    variables: list[Variable] = []
    event_logs_metadata: Union[EventLogMetadata, None] = None
    is_datamodel_from_bg: Union[bool, None] = Field(default=False, alias="isDataModelFromBG")
    object_ids: Union[list[str], None] = None


class KnowledgeModelInternalService:
    """
    This class provides convienient methods to use semantic-layer endpoints to export data from pql queries.
    """

    sleep_time_ms: int = 200
    maximum_waiting_time_ms: int = 60000
    export_poll_interval_s: float = 2
    export_max_poll_interval_s: float = 30
    export_timeout_s: float = 60 * 30

    def __init__(
        self,
        knowledge_model: KnowledgeModel,
        draft: Union[bool, None] = True,
        pycelonis_client: Union[Client, None] = None,
        semantic_layer_client: Union[SemanticLayerClientBase, None] = None,
    ):
        # Dependency injection keeps the library easy to test and lets callers
        # provide a preconfigured client when they already manage auth/session
        # state themselves.
        self.semantic_layer_client = semantic_layer_client or get_semantic_layer_client()
        assert knowledge_model.root_with_key is not None, "Knowledge model root with key needs to be set"
        self._knowledge_model_key: str = knowledge_model.root_with_key
        self._draft = draft
        self._pycelonis_client = pycelonis_client

    async def export_with_km_id(self, pqls: list[PQL]) -> list[pd.DataFrame]:
        """
        Use semantic-layer endpoint to export data directly from knowledge model
        Input: list of PQLs
        Output: list of dataframes
        """
        queries = ["; ".join(_pql.queries) for _pql in pqls]
        data_export_request = KnowledgeModelQueryRequest(queries=queries)
        query_response = await self.semantic_layer_client.post_api_knowledge_models_query(
            rootWithKey=self._knowledge_model_key, request_body=data_export_request, draft=self._draft
        )
        dfs = self._postprocess_query_response_result(query_response)
        return dfs

    async def export_chunked(self, pql: PQL) -> pd.DataFrame:
        """
        Use the semantic-layer export endpoints to read a query result in parquet chunks.

        `export_with_km_id` returns the whole result as a single JSON body, which data-model-manager
        rejects with a 413 once it exceeds its response buffer. The export endpoints split the result
        into chunks of roughly 1GB instead, so they carry results that the query endpoint cannot.
        """
        assert self._pycelonis_client is not None, "A pycelonis client is needed to run a chunked export"
        query_context = QueryContext.STUDIO if self._draft else QueryContext.APPS

        export_id = await self._start_chunked_export(pql, query_context)
        chunk_ids = await self._wait_for_chunked_export(export_id, query_context)
        # Downloaded one at a time on purpose: chunks are roughly 1GB each, so fetching them
        # concurrently would multiply peak memory on an export that is already large by definition.
        chunks = [await self._download_export_chunk(export_id, chunk_id, query_context) for chunk_id in chunk_ids]
        if not chunks:
            # Only results too large for the query endpoint reach this method, so an empty export is a
            # failure. Returning a schemaless frame would instead surface as a missing column much later.
            raise BatchQueryExportException(f"Knowledge model export `{export_id}` finished without any result chunk.")

        dataframe = pd.concat(chunks, ignore_index=True)
        logger.info("chunked export `%s` loaded %s chunk(s), df.shape: `%s`", export_id, len(chunks), dataframe.shape)
        return dataframe

    async def _start_chunked_export(self, pql: PQL, query_context: QueryContext) -> str:
        """Requests a new export and returns its export id."""
        request = ExportKnowledgeModelByRootWithKeyRequest(
            exportType=PyCelonisExportType.PARQUET,
            query="; ".join(pql.queries),
            queryContext=query_context,
        )
        response = await asyncio.to_thread(
            SemanticLayerService.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports,
            self._pycelonis_client,
            self._knowledge_model_key,
            request,
        )
        export_id = self._export_status(response).id
        if export_id is None:
            raise BatchQueryExportException("Knowledge model export was requested but no export id was returned.")
        return str(export_id)

    async def _wait_for_chunked_export(self, export_id: str, query_context: QueryContext) -> list[int]:
        """Polls the export until it is done and returns the ids of its result chunks."""
        request = ExportStatusKnowledgeModelByRootWithKeyRequest(queryContext=query_context)
        deadline = time.monotonic() + self.export_timeout_s
        poll_interval = self.export_poll_interval_s

        while True:
            response = await asyncio.to_thread(
                SemanticLayerService.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id,
                self._pycelonis_client,
                self._knowledge_model_key,
                export_id,
                request,
            )
            status = self._export_status(response)

            if status.export_status == ProxyExportStatusV2.DONE:
                return [chunk.id for chunk in (status.exported_chunks or []) if chunk and chunk.id is not None]

            if status.export_status != ProxyExportStatusV2.RUNNING:
                raise BatchQueryExportException(
                    f"Knowledge model export `{export_id}` ended with status "
                    f"`{status.export_status}`: {status.messages}"
                )

            if time.monotonic() >= deadline:
                raise BatchQueryExportException(
                    f"Knowledge model export `{export_id}` did not finish within {self.export_timeout_s} seconds."
                )

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 2, self.export_max_poll_interval_s)

    async def _download_export_chunk(self, export_id: str, chunk_id: int, query_context: QueryContext) -> pd.DataFrame:
        """Downloads a single parquet chunk of a finished export."""
        request = ExportStatusKnowledgeModelByRootWithKeyRequest(queryContext=query_context)
        chunk = await asyncio.to_thread(
            SemanticLayerService.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id_chunks_chunk_id,
            self._pycelonis_client,
            self._knowledge_model_key,
            export_id,
            str(chunk_id),
            request,
        )
        return pd.read_parquet(chunk)

    @staticmethod
    def _export_status(response: Union[object, None]) -> ProxyDataExportStatusResponseV2:
        query_response = getattr(response, "query_response", None)
        if query_response is None:
            raise BatchQueryExportException("Knowledge model export returned no status.")
        return query_response

    def _postprocess_query_response_result(self, query_response: ProxyQueryResponseTransportV2) -> list[pd.DataFrame]:
        if query_response.multi_statement_query_results is None:
            raise BatchQueryExportException(
                "Something went wrong executing the KnowledgeModel query. No results for query given."
            )
        return [
            self._postporcess_multi_statement_query_result(statement_query_result)
            for statement_query_result in query_response.multi_statement_query_results
            if statement_query_result
        ]

    def _postporcess_multi_statement_query_result(
        self, multi_statement_query_result: MultiStatementQueryResult
    ) -> pd.DataFrame:
        if multi_statement_query_result.query_results is None:
            raise BatchQueryExportException("Something went wrong executing the query. No results for query given.")

        if multi_statement_query_result.status and multi_statement_query_result.status.errors:
            raise ValueError(f"KnowledgeModel query export failed: `{multi_statement_query_result.status.errors}`")
        query_results = multi_statement_query_result.query_results
        return self._postprocess_table_result(query_results[0])

    def _postprocess_table_result(self, table_result: ProxyTableResultV2) -> pd.DataFrame:
        """Converts table result to data frame."""
        if table_result is None:
            raise BatchQueryExportException(
                "Something went wrong executing the query. No table result found in given query results."
            )
        if table_result.data is None:
            raise BatchQueryExportException(
                "Something went wrong executing the query. No data found in given query results."
            )
        if table_result.column_meta_data is None:
            raise BatchQueryExportException(
                "Something went wrong executing the query. No meta data found in given query results."
            )

        return self._postprocess_data_types(table_result)

    def _postprocess_data_types(self, table_result: ProxyTableResultV2) -> pd.DataFrame:
        # map int to Int64 for None handling
        type_mapping = {"date": "datetime64[ns]", "int": "Int64"}
        data = np.array(table_result.data, dtype=object)
        columns = {}
        if not table_result.column_meta_data:
            return pd.DataFrame(data=data)
        for idx, meta in enumerate(table_result.column_meta_data):
            if data.shape[0] > 0:
                column = data[:, idx]
            else:
                column = np.array([])
            if meta:
                if meta.column_type == "date":
                    column = self._process_datetype(column)
                if meta.column_type:
                    columns[meta.column_name] = pd.Series(
                        data=column, dtype=type_mapping.get(meta.column_type, meta.column_type)
                    )
        return pd.DataFrame(data=columns)

    def _process_datetype(self, data: np.ndarray) -> np.ndarray:
        # when PQL DateTime Round function is used it returns the correct datatype but the values as string
        data = pd.to_numeric(data, errors="coerce")
        date_series = pd.Series(data).clip(
            lower=int(pd.Timestamp.min.value * 1e-6), upper=int(pd.Timestamp.max.value * 1e-6)
        )
        return pd.to_datetime(date_series, unit="ms").values

    async def export_data_frame(self, pql: PQL) -> pd.DataFrame:
        """Exports data as data frame from given pql query."""

        export_id = await self._start_export_data(pql, draft=self._draft)
        assert isinstance(export_id, str)

        _ = await self._wait_for_execution(export_id, draft=self._draft)

        return await self._collect_data(export_id, draft=self._draft)

    async def get_data_model_transport(self) -> DataModelTransport:
        return await self.semantic_layer_client.get_api_data_models_by_knowledge_model_id_knowledge_model_id(
            self._knowledge_model_key
        )

    async def _start_export_data(self, pql: PQL, draft: Union[bool, None] = True) -> str:
        """Starts data export and returns export id."""
        data_export_request = QueryExportRequestTransport(
            draftMode=draft,
            exportType=ProxyExportTypeV2.PARQUET,
            filters=[f.query for f in pql.filters],
            query=pql.queries[-1],
        )

        data_export_response = await self.semantic_layer_client.post_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export(
            knowledge_model_id=self._knowledge_model_key, request_body=data_export_request
        )
        assert data_export_response.id is not None, "Export id is None."
        return data_export_response.id

    async def _wait_for_execution(self, export_id: str, draft: Union[bool, None] = True) -> QueryExportStatusTransport:
        """Waits for export to finish and returns export status."""
        export_status_response = await self._get_export_status(export_id, draft=draft)

        total_time_elapsed_ms = 0
        while self._continue_waiting_for_execution(export_status_response):
            await asyncio.sleep(self.sleep_time_ms / 1000)

            total_time_elapsed_ms += self.sleep_time_ms

            if total_time_elapsed_ms > self.maximum_waiting_time_ms:
                break

            export_status_response = await self._get_export_status(export_id, draft=draft)
        return export_status_response

    async def _collect_data(self, export_id: str, draft: Union[bool, None] = True) -> pd.DataFrame:
        """Collects data from export and returns data frame."""
        dataframe = pd.read_parquet(
            await self.semantic_layer_client.get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id_result_chunk_id(
                knowledge_model_id=self._knowledge_model_key, export_id=export_id, draft_mode=draft, chunk_id=0
            )
        )
        logger.info("data frame loaded. df.shape: `%s`", dataframe.shape)
        return dataframe

    async def _get_export_status(self, export_id: str, draft: Union[bool, None] = True) -> QueryExportStatusTransport:
        """Returns export status."""
        return await self.semantic_layer_client.get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id(
            knowledge_model_id=self._knowledge_model_key, export_id=export_id, draft_mode=draft
        )

    def _continue_waiting_for_execution(self, export_status_response: QueryExportStatusTransport) -> bool:
        """Returns True if export is still running, False if it is done or raises an exception if it failed."""
        export_status = export_status_response.status

        if export_status == ExportStatus.RUNNING:
            return True

        if export_status == ExportStatus.DONE:
            return False

        if export_status == ExportStatus.EXPIRED:
            raise ValueError(export_status_response.messages)

        if export_status == ExportStatus.FAILED:
            raise ValueError(export_status_response.messages)

        raise RuntimeError("Unexpected export status.")


# Public name for consumers that do not need to know the historical internal
# class name used by Celoptima.
KnowledgeModelService = KnowledgeModelInternalService
