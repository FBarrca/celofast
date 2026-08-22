from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pycelonis.ems.data_integration.augmentation_table import AugmentationTable
from pycelonis.ems.data_integration.data_model import DataModel

from celofast import AugmentationValidationError
from celofast.resources.augmentation_table import AugmentationTableCollection


def make_native_table(name: str = "ML_RESULTS"):
    return SimpleNamespace(
        name=name,
        upsert=MagicMock(),
        remove=MagicMock(),
        delete=MagicMock(),
    )


def make_collection():
    data_model = MagicMock(spec=DataModel)
    data_model.id = "dm-id"
    native = make_native_table()
    data_model.get_augmentation_table.return_value = native
    data_model.create_augmentation_table.return_value = native
    collection = AugmentationTableCollection(cast(DataModel, data_model))
    return collection, data_model, native


def test_table_returns_cached_lazy_native_reference_and_remembers_key():
    collection, data_model, native = make_collection()

    first = collection.table("ML_RESULTS")
    second = collection.table("ML_RESULTS", key="CASE_ID")

    assert first is second
    assert first.name == "ML_RESULTS"
    assert first.key == "CASE_ID"
    assert first.native is native
    assert first.data_model is data_model
    assert collection.data_model is data_model
    data_model.get_augmentation_table.assert_called_once_with("ML_RESULTS")

    with pytest.raises(AugmentationValidationError, match="already configured"):
        collection.table("ML_RESULTS", key="OTHER_ID")


def test_create_uses_first_batch_for_schema_and_upserts_remaining_batches():
    collection, data_model, native = make_collection()
    frame = pd.DataFrame(
        {
            "CASE_ID": range(2_501),
            "SCORE": [0.5] * 2_501,
        }
    )
    original = frame.copy()

    handle = collection.create(
        frame,
        table_name="ML_RESULTS",
        key="CASE_ID",
        data_model_table_name="CASES",
        foreign_key_columns=[("CASE_ID", "ID")],
    )

    assert handle.key == "CASE_ID"
    create_call = data_model.create_augmentation_table.call_args
    assert len(create_call.kwargs["df"]) == 1_000
    assert create_call.kwargs["table_name"] == "ML_RESULTS"
    assert create_call.kwargs["key"] == "CASE_ID"
    assert create_call.kwargs["data_model_table_name"] == "CASES"
    assert create_call.kwargs["foreign_key_columns"] == [("CASE_ID", "ID")]
    assert [len(call.args[0]) for call in native.upsert.call_args_list] == [1_000, 501]
    pd.testing.assert_frame_equal(frame, original)


def test_upsert_batches_requests_and_empty_frames_are_no_ops():
    collection, _, native = make_collection()
    handle = collection.table("ML_RESULTS")

    handle.upsert(pd.DataFrame({"CASE_ID": range(2_001)}))

    assert [len(call.args[0]) for call in native.upsert.call_args_list] == [
        1_000,
        1_000,
        1,
    ]

    native.upsert.reset_mock()
    handle.upsert(pd.DataFrame({"CASE_ID": pd.Series(dtype="int64")}))
    native.upsert.assert_not_called()


def test_remove_uses_remembered_key_and_batches_requests():
    collection, _, native = make_collection()
    handle = collection.table("ML_RESULTS", key="CASE_ID")

    handle.remove(pd.DataFrame({"CASE_ID": range(1_001)}))

    assert [len(call.args[0]) for call in native.remove.call_args_list] == [1_000, 1]
    assert [call.kwargs["key"] for call in native.remove.call_args_list] == [
        "CASE_ID",
        "CASE_ID",
    ]


def test_remove_requires_a_known_key_and_key_column():
    collection, _, _ = make_collection()
    handle = collection.table("ML_RESULTS")

    with pytest.raises(AugmentationValidationError, match="key is required"):
        handle.remove(pd.DataFrame({"CASE_ID": [1]}))

    with pytest.raises(AugmentationValidationError, match="CASE_ID"):
        handle.remove(pd.DataFrame({"OTHER": [1]}), key="CASE_ID")

    configured = collection.table("CONFIGURED", key="CASE_ID")
    with pytest.raises(AugmentationValidationError, match="not 'OTHER_ID'"):
        configured.remove(
            pd.DataFrame({"OTHER_ID": [1]}),
            key="OTHER_ID",
        )


@pytest.mark.parametrize("batch_size", [0, -1, 1_001, True, 1.5])
def test_invalid_batch_sizes_are_rejected(batch_size):
    collection, _, _ = make_collection()

    with pytest.raises(AugmentationValidationError, match="batch_size"):
        collection.table("ML_RESULTS").upsert(
            pd.DataFrame({"CASE_ID": [1]}),
            batch_size=batch_size,
        )


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"table_name": ""}, "table_name"),
        ({"key": ""}, "key"),
        ({"data_model_table_name": ""}, "data_model_table_name"),
        ({"foreign_key_columns": []}, "foreign_key_columns"),
        ({"foreign_key_columns": [("MISSING", "ID")]}, "MISSING"),
    ],
)
def test_create_validates_definition_before_calling_pycelonis(kwargs, match):
    collection, data_model, _ = make_collection()
    arguments = {
        "table_name": "ML_RESULTS",
        "key": "CASE_ID",
        "data_model_table_name": "CASES",
        "foreign_key_columns": [("CASE_ID", "ID")],
    }
    arguments.update(kwargs)

    with pytest.raises(AugmentationValidationError, match=match):
        collection.create(pd.DataFrame({"CASE_ID": [1]}), **arguments)

    data_model.create_augmentation_table.assert_not_called()


def test_delete_delegates_then_invalidates_the_cached_reference():
    collection, data_model, first_native = make_collection()
    second_native = make_native_table()
    data_model.get_augmentation_table.side_effect = [first_native, second_native]
    first = collection.table("ML_RESULTS", key="CASE_ID")

    first.delete()
    second = collection.table("ML_RESULTS")

    first_native.delete.assert_called_once_with()
    assert second is not first
    assert second.native is second_native
    assert second.key is None
    assert data_model.get_augmentation_table.call_count == 2


def test_native_batch_failure_is_preserved_and_stops_later_requests():
    collection, _, native = make_collection()
    native.upsert.side_effect = [None, RuntimeError("native failure")]

    with pytest.raises(RuntimeError, match="native failure"):
        collection.table("ML_RESULTS").upsert(
            pd.DataFrame({"CASE_ID": range(2_500)})
        )

    assert native.upsert.call_count == 2
