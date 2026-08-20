import uuid
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from celofast.services.knowledge_model_service import KnowledgeModel, KnowledgeModelService
from pycelonis import pql
from pycelonis.service.semantic_layer.service import (
    ExportChunk,
    ExportQueryResponse,
    ProxyDataExportStatusResponseV2,
    ProxyExportStatusV2,
    ProxyExportTypeV2,
    QueryContext,
)
from python_core_ems.exception import BatchQueryExportException

EXPORT_ID = uuid.uuid4()


def export_response(status, chunk_ids=(), messages=None):
    return ExportQueryResponse(
        queryResponse=ProxyDataExportStatusResponseV2(
            id=EXPORT_ID,
            exportStatus=status,
            exportType=ProxyExportTypeV2.PARQUET,
            exportedChunks=[ExportChunk(id=chunk_id) for chunk_id in chunk_ids],
            messages=messages,
        )
    )


@pytest.fixture
def service():
    with patch("celofast.services.knowledge_model_service.get_semantic_layer_client"):
        knowledge_model = KnowledgeModel(root_with_key="root.key")
        yield KnowledgeModelService(knowledge_model=knowledge_model, draft=True, pycelonis_client=MagicMock())


@pytest.fixture
def query():
    return pql.PQL(columns=[pql.PQLColumn(query="attr_pql", name="rcrd.attr")])


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_concatenates_every_chunk(mock_semantic_layer_service, service, query):
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.DONE, chunk_ids=(0, 1)
    )

    chunks = [pd.DataFrame({"col": [1, 2]}), pd.DataFrame({"col": [3]})]
    with patch("celofast.services.knowledge_model_service.pd.read_parquet", side_effect=chunks):
        result = await service.export_chunked(query)

    pd.testing.assert_frame_equal(result, pd.DataFrame({"col": [1, 2, 3]}))

    downloads = (
        mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id_chunks_chunk_id
    )
    assert [call.args[3] for call in downloads.call_args_list] == ["0", "1"]


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_sends_full_query_and_studio_context_for_draft(
    mock_semantic_layer_service, service, query
):
    start = mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports
    start.return_value = export_response(ProxyExportStatusV2.RUNNING)
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.DONE, chunk_ids=(0,)
    )

    query += pql.PQLFilter(query="FILTER attr_pql > 0;")
    with patch("celofast.services.knowledge_model_service.pd.read_parquet", return_value=pd.DataFrame({"col": [1]})):
        await service.export_chunked(query)

    request = start.call_args.args[2]
    assert request.export_type == ProxyExportTypeV2.PARQUET
    assert request.query_context == QueryContext.STUDIO
    # Filters have no dedicated field on the export request, so they must ride along in the query.
    assert request.query == "; ".join(query.queries)
    assert "FILTER attr_pql > 0;" in request.query


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_uses_apps_context_when_not_draft(mock_semantic_layer_service, service, query):
    service._draft = False
    start = mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports
    start.return_value = export_response(ProxyExportStatusV2.RUNNING)
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.DONE, chunk_ids=(0,)
    )

    with patch("celofast.services.knowledge_model_service.pd.read_parquet", return_value=pd.DataFrame({"col": [1]})):
        await service.export_chunked(query)

    assert start.call_args.args[2].query_context == QueryContext.APPS


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_polls_until_the_export_is_done(mock_semantic_layer_service, service, query):
    service.export_poll_interval_s = 0
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    status = (
        mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id
    )
    status.side_effect = [
        export_response(ProxyExportStatusV2.RUNNING),
        export_response(ProxyExportStatusV2.RUNNING),
        export_response(ProxyExportStatusV2.DONE, chunk_ids=(0,)),
    ]

    with patch("celofast.services.knowledge_model_service.pd.read_parquet", return_value=pd.DataFrame({"col": [1]})):
        result = await service.export_chunked(query)

    assert status.call_count == 3
    pd.testing.assert_frame_equal(result, pd.DataFrame({"col": [1]}))


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_backs_off_between_polls(mock_semantic_layer_service, service, query):
    service.export_poll_interval_s = 1
    service.export_max_poll_interval_s = 4
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.side_effect = [
        *[export_response(ProxyExportStatusV2.RUNNING)] * 4,
        export_response(ProxyExportStatusV2.DONE, chunk_ids=(0,)),
    ]

    with patch("celofast.services.knowledge_model_service.asyncio.sleep") as mock_sleep:
        with patch("celofast.services.knowledge_model_service.pd.read_parquet", return_value=pd.DataFrame({"col": [1]})):
            await service.export_chunked(query)

    # Doubles each round and then holds at the ceiling, instead of hammering the endpoint at a fixed rate.
    assert [call.args[0] for call in mock_sleep.call_args_list] == [1, 2, 4, 4]


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_raises_when_the_export_reports_no_chunks(mock_semantic_layer_service, service, query):
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.DONE
    )

    # A result that did not fit the query endpoint cannot legitimately export to nothing, and an empty
    # frame would only fail later as a missing column.
    with pytest.raises(BatchQueryExportException, match="without any result chunk"):
        await service.export_chunked(query)


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_raises_when_the_export_fails(mock_semantic_layer_service, service, query):
    service.export_poll_interval_s = 0
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.FAILED, messages=["engine ran out of memory"]
    )

    with pytest.raises(BatchQueryExportException, match="engine ran out of memory"):
        await service.export_chunked(query)


@patch("celofast.services.knowledge_model_service.SemanticLayerService")
async def test_export_chunked_raises_when_polling_times_out(mock_semantic_layer_service, service, query):
    service.export_poll_interval_s = 0
    service.export_timeout_s = 0
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )
    mock_semantic_layer_service.post_api_knowledge_models_by_knowledge_model_root_with_key_root_with_key_exports_export_id.return_value = export_response(
        ProxyExportStatusV2.RUNNING
    )

    with pytest.raises(BatchQueryExportException, match="did not finish within"):
        await service.export_chunked(query)
