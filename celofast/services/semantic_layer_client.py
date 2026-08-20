import logging
import typing
from abc import ABC
from io import BytesIO
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import Field, StrictBool, StrictInt, StrictStr
from python_core_internal_client import AsyncClient, PythonCoreBaseEnum, PythonCoreBaseModel, PythonCoreDatetime

logger = logging.getLogger("python_core_internal_client.semantic_layer")

JsonNode = Any

class ExternalAsyncClient(AsyncClient):
    def _set_headers(
        self,
        headers: dict[str, str],
    ) -> dict[str, str]:
        return headers

class CascadeType(PythonCoreBaseEnum):
    DELETE = "DELETE"


class ContentNodeType(PythonCoreBaseEnum):
    ASSET = "ASSET"
    PACKAGE = "PACKAGE"
    FOLDER = "FOLDER"
    IMAGE = "IMAGE"


class RelationType(PythonCoreBaseEnum):
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"


class MetadataType(PythonCoreBaseEnum):
    KPI = "KPI"
    RECORD = "RECORD"
    VARIABLE = "VARIABLE"
    ACTIVITY = "ACTIVITY"
    FILTER = "FILTER"
    ACTION = "ACTION"
    ANOMALY = "ANOMALY"
    ATTRIBUTE = "ATTRIBUTE"
    NEW_ATTRIBUTE = "NEW_ATTRIBUTE"
    AUGMENTED_ATTRIBUTE = "AUGMENTED_ATTRIBUTE"
    PRIORITY = "PRIORITY"
    FLAG = "FLAG"
    EVENT_LOG = "EVENT_LOG"
    DATA_TRIGGER = "DATA_TRIGGER"


class ScopeType(PythonCoreBaseEnum):
    DISABLED = "DISABLED"


class KpiDirection(PythonCoreBaseEnum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NEUTRAL = "NEUTRAL"
    NONE = "NONE"


class ParameterType(PythonCoreBaseEnum):
    VARIABLE = "VARIABLE"
    TABLE = "TABLE"
    INTEGER = "INTEGER"
    TEXT = "TEXT"
    PQL = "PQL"


class TransitionType(PythonCoreBaseEnum):
    NON_INTERLEAVED = "NON_INTERLEAVED"
    INTERLEAVED = "INTERLEAVED"


class LayerKind(PythonCoreBaseEnum):
    BASE = "BASE"
    EXTENSION = "EXTENSION"


class SortDirection(PythonCoreBaseEnum):
    ASC = "ASC"
    DESC = "DESC"


class TaskStatus(PythonCoreBaseEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    RESOLVED = "RESOLVED"
    SNOOZED = "SNOOZED"


class ColumnType(PythonCoreBaseEnum):
    INTEGER = "INTEGER"
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"


class TableColumnType(PythonCoreBaseEnum):
    IDENTIFIER_COLUMN = "IDENTIFIER_COLUMN"
    KPI_COLUMN = "KPI_COLUMN"
    RECORD_ATTRIBUTE_COLUMN = "RECORD_ATTRIBUTE_COLUMN"
    RECORD_NEW_ATTRIBUTE_COLUMN = "RECORD_NEW_ATTRIBUTE_COLUMN"
    TASK_COUNT_COLUMN = "TASK_COUNT_COLUMN"
    ACTIVE_PRIORITY_COLUMN = "ACTIVE_PRIORITY_COLUMN"
    EMPTY_COLUMN = "EMPTY_COLUMN"


class ComputeCallerType(PythonCoreBaseEnum):
    PROCESS_WORKSPACE = "PROCESS_WORKSPACE"
    KNOWLEDGE_MODEL = "KNOWLEDGE_MODEL"
    VIEW = "VIEW"
    DATA_MODEL = "DATA_MODEL"


class DataPermissionStrategy(PythonCoreBaseEnum):
    AND = "AND"
    OR = "OR"


class AcceleratorSelectionKind(PythonCoreBaseEnum):
    SELECTION = "SELECTION"
    FILTER = "FILTER"


class AcceleratorSelectionType(PythonCoreBaseEnum):
    DATE = "DATE"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    THROUGHPUT = "THROUGHPUT"
    PROCESS = "PROCESS"
    REWORK = "REWORK"
    ERROR = "ERROR"
    GENERIC = "GENERIC"


class ProcessType(PythonCoreBaseEnum):
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"
    GENERIC = "GENERIC"


class ProcessWorkspaceKpiValidationStatus(PythonCoreBaseEnum):
    VALID = "VALID"
    DIMENSION_ERROR = "DIMENSION_ERROR"
    COMPUTE_ERROR = "COMPUTE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class JobType(PythonCoreBaseEnum):
    EXCEL = "EXCEL"
    CSV = "CSV"


class AutoMergeExecutionMode(PythonCoreBaseEnum):
    DISTINCT = "DISTINCT"
    NON_DISTINCT = "NON_DISTINCT"


class CalendarDay(PythonCoreBaseEnum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class DataModelCalendarType(PythonCoreBaseEnum):
    NONE = "NONE"
    CUSTOM = "CUSTOM"
    FACTORY = "FACTORY"


class ProxyExportTypeV2(PythonCoreBaseEnum):
    PARQUET = "PARQUET"
    EXCEL = "EXCEL"
    CSV = "CSV"


class QueryType(PythonCoreBaseEnum):
    FORMULA = "FORMULA"
    RAW = "RAW"


class JobStatus(PythonCoreBaseEnum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    READY = "READY"
    UNDEFINED = "UNDEFINED"
    CANCELED = "CANCELED"
    NOTRUNNING = "NOTRUNNING"
    DONEWITHERRORS = "DONEWITHERRORS"


class SnippetType(PythonCoreBaseEnum):
    TEXT = "TEXT"
    JSON = "JSON"
    YAML = "YAML"


class DataModelLoadStatus(PythonCoreBaseEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    WARNING = "WARNING"
    LOST_CONNECTION = "LOST_CONNECTION"
    CANCELED = "CANCELED"
    CANCELLING = "CANCELLING"


class ExceptionReference(PythonCoreBaseModel):
    reference: Optional["str"] = Field(None, alias="reference")
    message: Optional["str"] = Field(None, alias="message")
    short_message: Optional["str"] = Field(None, alias="shortMessage")


class FrontendHandledBackendError(PythonCoreBaseModel):
    frontend_error_key: Optional["str"] = Field(None, alias="frontendErrorKey")
    error_information: Optional["Any"] = Field(None, alias="errorInformation")


class FinalModelOptions(PythonCoreBaseModel):
    with_variable_replacement: Optional["bool"] = Field(None, alias="withVariableReplacement")
    with_autogenerated_data_model_data: Optional["bool"] = Field(None, alias="withAutogeneratedDataModelData")
    with_default_values: Optional["bool"] = Field(None, alias="withDefaultValues")
    validate_pql: Optional["bool"] = Field(None, alias="validatePql")
    with_unknown_variables_validation: Optional["bool"] = Field(None, alias="withUnknownVariablesValidation")
    with_resolved_scopes: Optional["bool"] = Field(None, alias="withResolvedScopes")


class YamlMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    key: Optional["str"] = Field(None, alias="key")
    parent_node_id: Optional["str"] = Field(None, alias="parentNodeId")
    final_model_options: Optional["FinalModelOptions"] = Field(None, alias="finalModelOptions")
    content: Optional["str"] = Field(None, alias="content")
    visual_editor_validation: Optional["bool"] = Field(None, alias="visualEditorValidation")


class AssetMetadataTransport(PythonCoreBaseModel):
    used_variables: Optional["List[Optional[VariableDefinition]]"] = Field(None, alias="usedVariables")
    related_assets: Optional["List[Optional[RelatedAsset]]"] = Field(None, alias="relatedAssets")
    asset_usages: Optional["List[Optional[AssetUsage]]"] = Field(None, alias="assetUsages")
    metadata: Optional["JsonNode"] = Field(None, alias="metadata")
    hidden: Optional["bool"] = Field(None, alias="hidden")


class AssetUsage(PythonCoreBaseModel):
    object_id: Optional["str"] = Field(None, alias="objectId")
    target_objects: Optional["List[Optional[TargetUsageMetadata]]"] = Field(None, alias="targetObjects")


class ContentNodeBaseTransport(PythonCoreBaseModel):
    reference: Optional["str"] = Field(None, alias="reference")
    version: Optional["str"] = Field(None, alias="version")
    external: Optional["bool"] = Field(None, alias="external")


class ContentNodeTransport(PythonCoreBaseModel):
    permissions: Optional["List[Optional[str]]"] = Field(None, alias="permissions")
    tenant_id: Optional["str"] = Field(None, alias="tenantId")
    id: Optional["str"] = Field(None, alias="id")
    key: Optional["str"] = Field(None, alias="key")
    name: Optional["str"] = Field(None, alias="name")
    root_node_key: Optional["str"] = Field(None, alias="rootNodeKey")
    base: Optional["ContentNodeBaseTransport"] = Field(None, alias="base")
    asset_type: Optional["str"] = Field(None, alias="assetType")
    node_type: Optional["ContentNodeType"] = Field(None, alias="nodeType")
    parent_node_key: Optional["str"] = Field(None, alias="parentNodeKey")
    parent_node_id: Optional["str"] = Field(None, alias="parentNodeId")
    invalid_content: Optional["bool"] = Field(None, alias="invalidContent")
    serialized_content: Optional["str"] = Field(None, alias="serializedContent")
    serialization_type: Optional["str"] = Field(None, alias="serializationType")
    draft_id: Optional["str"] = Field(None, alias="draftId")
    working_draft_id: Optional["str"] = Field(None, alias="workingDraftId")
    activated_draft_id: Optional["str"] = Field(None, alias="activatedDraftId")
    show_in_viewer_mode: Optional["bool"] = Field(None, alias="showInViewerMode")
    public_available: Optional["bool"] = Field(None, alias="publicAvailable")
    embeddable: Optional["bool"] = Field(None, alias="embeddable")
    root_node_id: Optional["str"] = Field(None, alias="rootNodeId")
    order: Optional["int"] = Field(None, alias="order")
    source: Optional["str"] = Field(None, alias="source")
    asset_metadata_transport: Optional["AssetMetadataTransport"] = Field(None, alias="assetMetadataTransport")
    space_id: Optional["str"] = Field(None, alias="spaceId")
    change_date: Optional["PythonCoreDatetime"] = Field(None, alias="changeDate")
    created_by_id: Optional["str"] = Field(None, alias="createdById")
    creation_date: Optional["PythonCoreDatetime"] = Field(None, alias="creationDate")
    created_by_name: Optional["str"] = Field(None, alias="createdByName")
    updated_by: Optional["str"] = Field(None, alias="updatedBy")
    root_with_key: Optional["str"] = Field(None, alias="rootWithKey")
    object_id: Optional["str"] = Field(None, alias="objectId")
    asset: Optional["bool"] = Field(None, alias="asset")
    root: Optional["bool"] = Field(None, alias="root")
    identifier: Optional["str"] = Field(None, alias="identifier")


class RelatedAsset(PythonCoreBaseModel):
    object_id: Optional["str"] = Field(None, alias="objectId")
    type_: Optional["str"] = Field(None, alias="type")
    relation_type: Optional["RelationType"] = Field(None, alias="relationType")
    cascade_type: Optional["CascadeType"] = Field(None, alias="cascadeType")


class SourceUsageMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")


class TargetUsageMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    type_: Optional["str"] = Field(None, alias="type")
    source_objects: Optional["List[Optional[SourceUsageMetadata]]"] = Field(None, alias="sourceObjects")


class VariableDefinition(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    type_: Optional["str"] = Field(None, alias="type")
    description: Optional["str"] = Field(None, alias="description")
    source: Optional["str"] = Field(None, alias="source")
    runtime: Optional["bool"] = Field(None, alias="runtime")
    metadata: Optional["JsonNode"] = Field(None, alias="metadata")


class VariableMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    value: Optional["str"] = Field(None, alias="value")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class AttributeMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    column_type: Optional["str"] = Field(None, alias="columnType")
    unit: Optional["str"] = Field(None, alias="unit")
    format: Optional["str"] = Field(None, alias="format")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class AugmentedAttributeMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    possible_values: Optional["List[Optional[str]]"] = Field(None, alias="possibleValues")
    default_value: Optional["str"] = Field(None, alias="defaultValue")
    column_type: Optional["str"] = Field(None, alias="columnType")
    pql: Optional["str"] = Field(None, alias="pql")
    unit: Optional["str"] = Field(None, alias="unit")
    format: Optional["str"] = Field(None, alias="format")
    housekeeping: Optional["bool"] = Field(None, alias="housekeeping")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class BusinessRecordMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    augmented: Optional["bool"] = Field(None, alias="augmented")
    identifier: Optional["PqlBaseMetadata"] = Field(None, alias="identifier")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    attributes: Optional["List[Optional[AttributeMetadata]]"] = Field(None, alias="attributes")
    new_attributes: Optional["List[Optional[NewAttributeMetadata]]"] = Field(None, alias="newAttributes")
    augmented_attributes: Optional["List[Optional[AugmentedAttributeMetadata]]"] = Field(
        None, alias="augmentedAttributes"
    )
    flags: Optional["List[Optional[PqlBaseMetadata]]"] = Field(None, alias="flags")
    priorities: Optional["List[Optional[RecordPriorityMetadata]]"] = Field(None, alias="priorities")
    data_triggers: Optional["List[Optional[DataTriggerMetadata]]"] = Field(None, alias="dataTriggers")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class DataTriggerMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class NewAttributeMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    possible_values: Optional["List[Optional[str]]"] = Field(None, alias="possibleValues")
    default_value: Optional["str"] = Field(None, alias="defaultValue")
    column_type: Optional["str"] = Field(None, alias="columnType")
    unit: Optional["str"] = Field(None, alias="unit")
    format: Optional["str"] = Field(None, alias="format")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class PqlBaseMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")


class RecordPriorityMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    kpi: Optional["str"] = Field(None, alias="kpi")


class AnomalyKpiMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    kpi_id: Optional["str"] = Field(None, alias="kpiId")
    impact_calculation: Optional["str"] = Field(None, alias="impactCalculation")
    scope: Optional["ScopeType"] = Field(None, alias="scope")


class FlagAnomalyTransport(PythonCoreBaseModel):
    flag: Optional["PqlBaseMetadata"] = Field(None, alias="flag")
    kpis: Optional["List[Optional[AnomalyKpiMetadata]]"] = Field(None, alias="kpis")
    knowledge_object_id: Optional["str"] = Field(None, alias="knowledgeObjectId")


class AugmentedAttributeMetadataV2(PythonCoreBaseModel):
    augmentation_table_name_suffix: Optional["str"] = Field(None, alias="augmentationTableNameSuffix")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    column_type: Optional["str"] = Field(None, alias="columnType")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    data_model_table: Optional["str"] = Field(None, alias="dataModelTable")
    default_value: Optional["str"] = Field(None, alias="defaultValue")
    description: Optional["str"] = Field(None, alias="description")
    display_name: Optional["str"] = Field(None, alias="displayName")
    format: Optional["str"] = Field(None, alias="format")
    housekeeping: Optional["bool"] = Field(None, alias="housekeeping")
    id: Optional["str"] = Field(None, alias="id")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    possible_values: Optional["List[Optional[str]]"] = Field(None, alias="possibleValues")
    pql: Optional["str"] = Field(None, alias="pql")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    type_: Optional["MetadataType"] = Field(None, alias="type")
    unit: Optional["str"] = Field(None, alias="unit")


class BaseMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")


class KpiBenchmarking(PythonCoreBaseModel):
    value: Optional["str"] = Field(None, alias="value")
    action: Optional["KpiBenchmarkingAction"] = Field(None, alias="action")
    leading_bucket: Optional["PerformanceBucket"] = Field(None, alias="leadingBucket")
    exceeding_bucket: Optional["PerformanceBucket"] = Field(None, alias="exceedingBucket")
    achieving_bucket: Optional["PerformanceBucket"] = Field(None, alias="achievingBucket")
    lagging_bucket: Optional["PerformanceBucket"] = Field(None, alias="laggingBucket")


class KpiBenchmarkingAction(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    description: Optional["str"] = Field(None, alias="description")
    link: Optional["str"] = Field(None, alias="link")


class KpiMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    unit: Optional["str"] = Field(None, alias="unit")
    format: Optional["str"] = Field(None, alias="format")
    breakdowns: Optional["List[Optional[BaseMetadata]]"] = Field(None, alias="breakdowns")
    aggregations: Optional["List[Optional[str]]"] = Field(None, alias="aggregations")
    parameters: Optional["List[Optional[ParameterMetadata]]"] = Field(None, alias="parameters")
    targets: Optional["List[Optional[TargetMetadata]]"] = Field(None, alias="targets")
    desired_direction: Optional["KpiDirection"] = Field(None, alias="desiredDirection")
    priority: Optional["bool"] = Field(None, alias="priority")
    benchmarking: Optional["KpiBenchmarking"] = Field(None, alias="benchmarking")
    type_: Optional["MetadataType"] = Field(None, alias="type")
    benchmarkable: Optional["bool"] = Field(None, alias="benchmarkable")


class ParameterMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    default_value: Optional["str"] = Field(None, alias="defaultValue")
    type_: Optional["ParameterType"] = Field(None, alias="type")


class PerformanceBucket(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    text_snippet: Optional["str"] = Field(None, alias="textSnippet")
    text_snippet_active: Optional["str"] = Field(None, alias="textSnippetActive")
    upper_value: Optional["str"] = Field(None, alias="upperValue")
    lower_value: Optional["str"] = Field(None, alias="lowerValue")


class TargetMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    value: Optional["str"] = Field(None, alias="value")
    date_from: Optional["str"] = Field(None, alias="dateFrom")
    date_until: Optional["str"] = Field(None, alias="dateUntil")
    filters: Optional["List[Optional[str]]"] = Field(None, alias="filters")


class FilterMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    global_: Optional["bool"] = Field(None, alias="global")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class EventLogTransitionTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    event_log_id: Optional["str"] = Field(None, alias="eventLogId")
    type_: Optional["TransitionType"] = Field(None, alias="type")


class EventLogTransport(PythonCoreBaseModel):
    event_log: Optional["SingleEventLogMetadata"] = Field(None, alias="eventLog")
    transitions: Optional["List[Optional[EventLogTransitionTransport]]"] = Field(None, alias="transitions")


class SingleEventLogMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    record_id: Optional["str"] = Field(None, alias="recordId")
    default_event_log: Optional["bool"] = Field(None, alias="defaultEventLog")


class ActionInput(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    attribute: Optional["str"] = Field(None, alias="attribute")


class ActionMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    skill_id: Optional["str"] = Field(None, alias="skillId")
    skill_key: Optional["str"] = Field(None, alias="skillKey")
    records: Optional["List[Optional[str]]"] = Field(None, alias="records")
    filters: Optional["List[Optional[str]]"] = Field(None, alias="filters")
    inputs: Optional["List[Optional[ActionInput]]"] = Field(None, alias="inputs")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class ActivityMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    value: Optional["str"] = Field(None, alias="value")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class AlertMetric(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    pql: Optional["str"] = Field(None, alias="pql")
    message: Optional["str"] = Field(None, alias="message")


class AnomalyMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    flag: Optional["str"] = Field(None, alias="flag")
    kpi_ids: Optional["List[Optional[str]]"] = Field(None, alias="kpiIds")
    kpis: Optional["List[Optional[AnomalyKpiMetadata]]"] = Field(None, alias="kpis")
    mom_change: Optional["str"] = Field(None, alias="momChange")
    knowledge_object_id: Optional["str"] = Field(None, alias="knowledgeObjectId")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class EventLogKpi(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    event_log_id: Optional["str"] = Field(None, alias="eventLogId")
    node_kpi_ids: Optional["List[Optional[str]]"] = Field(None, alias="nodeKpiIds")
    edge_kpi_ids: Optional["List[Optional[str]]"] = Field(None, alias="edgeKpiIds")
    node_kpis: Optional["List[Optional[KpiWithAlert]]"] = Field(None, alias="nodeKpis")
    edge_kpis: Optional["List[Optional[KpiWithAlert]]"] = Field(None, alias="edgeKpis")


class EventLogKpiView(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    icon: Optional["str"] = Field(None, alias="icon")
    event_log_kpis: Optional["List[Optional[EventLogKpi]]"] = Field(None, alias="eventLogKpis")
    transition_kpis: Optional["List[Optional[EventLogTransitionKpi]]"] = Field(None, alias="transitionKpis")


class EventLogMetadata(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    pql: Optional["str"] = Field(None, alias="pql")
    filter_ids: Optional["List[Optional[str]]"] = Field(None, alias="filterIds")
    type_: Optional["MetadataType"] = Field(None, alias="type")


class EventLogTransition(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    first_event_log_id: Optional["str"] = Field(None, alias="firstEventLogId")
    second_event_log_id: Optional["str"] = Field(None, alias="secondEventLogId")
    type_: Optional["TransitionType"] = Field(None, alias="type")


class EventLogTransitionKpi(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    scope: Optional["ScopeType"] = Field(None, alias="scope")
    internal_note: Optional["str"] = Field(None, alias="internalNote")
    custom_attributes: Optional["JsonNode"] = Field(None, alias="customAttributes")
    auto_generated: Optional["bool"] = Field(None, alias="autoGenerated")
    transition_id: Optional["str"] = Field(None, alias="transitionId")
    kpi_id: Optional["str"] = Field(None, alias="kpiId")


class FinalWithAutogeneratedBaseRequest(PythonCoreBaseModel):
    process_workspace_id: Optional["str"] = Field(None, alias="processWorkspaceId")
    extension_knowledge_model: Optional["LayerTransport"] = Field(None, alias="extensionKnowledgeModel")


class KpiWithAlert(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    kpi_id: Optional["str"] = Field(None, alias="kpiId")
    icon: Optional["str"] = Field(None, alias="icon")
    alert_metrics: Optional["List[Optional[AlertMetric]]"] = Field(None, alias="alertMetrics")


class LayerBase(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    version: Optional["str"] = Field(None, alias="version")
    app_store_based: Optional["bool"] = Field(None, alias="appStoreBased")


class LayerMetadata(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    display_name: Optional["str"] = Field(None, alias="displayName")
    version: Optional["str"] = Field(None, alias="version")


class LayerTransport(PythonCoreBaseModel):
    kind: Optional["LayerKind"] = Field(None, alias="kind")
    metadata: Optional["LayerMetadata"] = Field(None, alias="metadata")
    base: Optional["LayerBase"] = Field(None, alias="base")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    records: Optional["List[Optional[BusinessRecordMetadata]]"] = Field(None, alias="records")
    kpis: Optional["List[Optional[KpiMetadata]]"] = Field(None, alias="kpis")
    filters: Optional["List[Optional[FilterMetadata]]"] = Field(None, alias="filters")
    variables: Optional["List[Optional[VariableMetadata]]"] = Field(None, alias="variables")
    activities: Optional["List[Optional[ActivityMetadata]]"] = Field(None, alias="activities")
    event_logs_metadata: Optional["NewEventLogMetadata"] = Field(None, alias="eventLogsMetadata")
    anomalies: Optional["List[Optional[AnomalyMetadata]]"] = Field(None, alias="anomalies")
    event_logs: Optional["List[Optional[EventLogMetadata]]"] = Field(None, alias="eventLogs")
    custom_objects: Optional["List[Optional[BaseMetadata]]"] = Field(None, alias="customObjects")
    id: Optional["str"] = Field(None, alias="id")
    tenant_id: Optional["str"] = Field(None, alias="tenantId")
    actions: Optional["List[Optional[ActionMetadata]]"] = Field(None, alias="actions")
    node_entity_id: Optional["str"] = Field(None, alias="nodeEntityId")


class NewEventLogMetadata(PythonCoreBaseModel):
    event_logs: Optional["List[Optional[SingleEventLogMetadata]]"] = Field(None, alias="eventLogs")
    transitions: Optional["List[Optional[EventLogTransition]]"] = Field(None, alias="transitions")
    kpi_views: Optional["List[Optional[EventLogKpiView]]"] = Field(None, alias="kpiViews")


class FinalLayerTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    layer: Optional["LayerTransport"] = Field(None, alias="layer")
    yaml_object: Optional["str"] = Field(None, alias="yamlObject")


class FrontendLogTransport(PythonCoreBaseModel):
    stacktrace: Optional["str"] = Field(None, alias="stacktrace")
    url: Optional["str"] = Field(None, alias="url")


class ColumnConfig(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    show_alerts: Optional["bool"] = Field(None, alias="showAlerts")
    show_tasks: Optional["bool"] = Field(None, alias="showTasks")
    kpi_parameters: Optional["List[Optional[KpiParameter]]"] = Field(None, alias="kpiParameters")


class KpiParameter(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    value: Optional["str"] = Field(None, alias="value")


class LayerBasedQuery(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    column_configs: Optional["List[Optional[ColumnConfig]]"] = Field(None, alias="columnConfigs")
    filter: Optional["QueryFilter"] = Field(None, alias="filter")
    pagination: Optional["Pagination"] = Field(None, alias="pagination")
    order_by: Optional["List[Optional[TableColumnSorting]]"] = Field(None, alias="orderBy")
    include_record_identifiers: Optional["bool"] = Field(None, alias="includeRecordIdentifiers")
    distinct: Optional["bool"] = Field(None, alias="distinct")


class LayerBasedQueryRequest(PythonCoreBaseModel):
    layer_transport: Optional["LayerTransport"] = Field(None, alias="layerTransport")
    query: Optional["LayerBasedQuery"] = Field(None, alias="query")


class Pagination(PythonCoreBaseModel):
    page_index: Optional["int"] = Field(None, alias="pageIndex")
    page_size: Optional["int"] = Field(None, alias="pageSize")

class ProxyColumnMetaDataV2(PythonCoreBaseModel):
    aggregation: Optional["bool"] = Field(None, alias="aggregation")
    column_name: Optional["str"] = Field(None, alias="columnName")
    column_type: Optional["str"] = Field(None, alias="columnType")
    filter_expression: Optional["str"] = Field(None, alias="filterExpression")
    format: Optional["str"] = Field(None, alias="format")

class ProxyQueryStatisticsV2(PythonCoreBaseModel):
    query_compile_time_ms: Optional["int"] = Field(None, alias="queryCompileTimeMs")
    query_execution_time_ms: Optional["int"] = Field(None, alias="queryExecutionTimeMs")
    query_result_size_in_bytes: Optional["int"] = Field(None, alias="queryResultSizeInBytes")

class ProxyTableResultV2(PythonCoreBaseModel):
    available: Optional["List[Optional[List[Optional[bool]]]]"] = Field(None, alias="available")
    column_meta_data: Optional["List[Optional[ProxyColumnMetaDataV2]]"] = Field(None, alias="columnMetaData")
    common_table_name: Optional["str"] = Field(None, alias="commonTableName")
    count: Optional["int"] = Field(None, alias="count")
    data: Optional["List[Optional[List[Optional[Any]]]]"] = Field(None, alias="data")
    name: Optional["str"] = Field(None, alias="name")
    offset: Optional["int"] = Field(None, alias="offset")
    others: Optional["List[Optional[Any]]"] = Field(None, alias="others")
    overall_count: Optional["int"] = Field(None, alias="overallCount")
    selected: Optional["List[Optional[List[Optional[bool]]]]"] = Field(None, alias="selected")
    string_hashes: Optional["List[Optional[List[Optional[str]]]]"] = Field(None, alias="stringHashes")

class QueryMessageErrorTag(PythonCoreBaseEnum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    DATA_MODEL_NOT_LOADED = "DATA_MODEL_NOT_LOADED"
    TIMEOUT = "TIMEOUT"
    GENERIC_USER_ERROR = "GENERIC_USER_ERROR"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"

class ProxyErrorMessage(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")
    tags: Optional["List[Optional[QueryMessageErrorTag]]"] = Field(None, alias="tags")

class ProxyWarningMessage(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")
    tags: Optional["List[Optional[QueryMessageWarningTag]]"] = Field(None, alias="tags")

class QueryMessageWarningTag(PythonCoreBaseEnum):
    COMPILATION = "COMPILATION"

class QueryStatus(PythonCoreBaseEnum):
    SUCCESS = "SUCCESS"
    CLIENT_ERROR = "CLIENT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"

class ProxyStatusTransport(PythonCoreBaseModel):
    errors: Optional["List[Optional[ProxyErrorMessage]]"] = Field(None, alias="errors")
    query_status_code: Optional["QueryStatus"] = Field(None, alias="queryStatusCode")
    warnings: Optional["List[Optional[ProxyWarningMessage]]"] = Field(None, alias="warnings")

class MultiStatementQueryResult(PythonCoreBaseModel):
    load_version: Optional["str"] = Field(None, alias="loadVersion")
    name: Optional["str"] = Field(None, alias="name")
    query_results: Optional["List[Optional[ProxyTableResultV2]]"] = Field(None, alias="queryResults")
    query_statistics: Optional["ProxyQueryStatisticsV2"] = Field(None, alias="queryStatistics")
    status: Optional["ProxyStatusTransport"] = Field(None, alias="status")

class ProxyQueryResponseTransportV2(PythonCoreBaseModel):
    multi_statement_query_results: Optional["List[Optional[MultiStatementQueryResult]]"] = Field(
        None, alias="multiStatementQueryResults"
    )

class QueryExportRequestTransport(PythonCoreBaseModel):
    draft_mode: Optional["bool"] = Field(None, alias="draftMode")
    export_type: Optional["ProxyExportTypeV2"] = Field(None, alias="exportType")
    filters: Optional["List[Optional[str]]"] = Field(None, alias="filters")
    query: Optional["str"] = Field(None, alias="query")


class QueryExportStatusTransport(PythonCoreBaseModel):
    chunks_count: Optional["int"] = Field(None, alias="chunksCount")
    id: Optional["str"] = Field(None, alias="id")
    messages: Optional["List[Optional[str]]"] = Field(None, alias="messages")
    status: Optional["ExportStatus"] = Field(None, alias="status")
    type_: Optional["ProxyExportTypeV2"] = Field(None, alias="type")


class QueryFilter(PythonCoreBaseModel):
    pql_filters: Optional["List[Optional[str]]"] = Field(None, alias="pqlFilters")
    task_filters: Optional["List[Optional[TaskFilter]]"] = Field(None, alias="taskFilters")


class TableColumnSorting(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    direction: Optional["SortDirection"] = Field(None, alias="direction")


class TaskFilter(PythonCoreBaseModel):
    column_id: Optional["str"] = Field(None, alias="columnId")
    record_metadata_id: Optional["str"] = Field(None, alias="recordMetadataId")
    task_statuses: Optional["List[Optional[TaskStatus]]"] = Field(None, alias="taskStatuses")
    assignee_identity_ids: Optional["List[Optional[str]]"] = Field(None, alias="assigneeIdentityIds")
    affect_task_count_only: Optional["bool"] = Field(None, alias="affectTaskCountOnly")


class ColumnHeader(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    display_name: Optional["str"] = Field(None, alias="displayName")
    short_display_name: Optional["str"] = Field(None, alias="shortDisplayName")
    description: Optional["str"] = Field(None, alias="description")
    pql: Optional["str"] = Field(None, alias="pql")
    record_metadata_id: Optional["str"] = Field(None, alias="recordMetadataId")
    data_type: Optional["ColumnType"] = Field(None, alias="dataType")
    column_type: Optional["TableColumnType"] = Field(None, alias="columnType")
    format: Optional["str"] = Field(None, alias="format")
    unit: Optional["str"] = Field(None, alias="unit")
    sort_direction: Optional["SortDirection"] = Field(None, alias="sortDirection")
    error: Optional["str"] = Field(None, alias="error")
    aggregation: Optional["bool"] = Field(None, alias="aggregation")
    sortable: Optional["bool"] = Field(None, alias="sortable")
    editable: Optional["bool"] = Field(None, alias="editable")
    filterable: Optional["bool"] = Field(None, alias="filterable")


class RecordAlert(PythonCoreBaseModel):
    record_id: Optional["str"] = Field(None, alias="recordId")
    alert_id: Optional["str"] = Field(None, alias="alertId")
    description: Optional["str"] = Field(None, alias="description")


class RecordTask(PythonCoreBaseModel):
    record_id: Optional["str"] = Field(None, alias="recordId")
    task_id: Optional["str"] = Field(None, alias="taskId")
    name: Optional["str"] = Field(None, alias="name")
    label: Optional["str"] = Field(None, alias="label")
    owner: Optional["str"] = Field(None, alias="owner")
    status: Optional["TaskStatus"] = Field(None, alias="status")


class RowCell(PythonCoreBaseModel):
    value: Optional["str"] = Field(None, alias="value")
    formatted_value: Optional["str"] = Field(None, alias="formattedValue")
    type_: Optional["ColumnType"] = Field(None, alias="type")
    alerts: Optional["List[Optional[RecordAlert]]"] = Field(None, alias="alerts")
    tasks: Optional["List[Optional[RecordTask]]"] = Field(None, alias="tasks")


class TableResponse(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    headers: Optional["List[Optional[ColumnHeader]]"] = Field(None, alias="headers")
    rows: Optional["List[Optional[TableRow]]"] = Field(None, alias="rows")
    total_count: Optional["int"] = Field(None, alias="totalCount")
    error: Optional["str"] = Field(None, alias="error")


class TableRow(PythonCoreBaseModel):
    cells: Optional["List[Optional[RowCell]]"] = Field(None, alias="cells")


class LayerBasedBatchQueryRequest(PythonCoreBaseModel):
    layer_transport: Optional["LayerTransport"] = Field(None, alias="layerTransport")
    queries: Optional["List[Optional[LayerBasedQuery]]"] = Field(None, alias="queries")

class KnowledgeModelQueryRequest(PythonCoreBaseModel):
    queries: Optional["List[Optional[str]]"] = Field(None, alias="queries")


class PqlErrorTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    message: Optional["str"] = Field(None, alias="message")
    regex: Optional["str"] = Field(None, alias="regex")
    start_line_number: Optional["int"] = Field(None, alias="startLineNumber")
    start_column_position: Optional["int"] = Field(None, alias="startColumnPosition")
    end_line_number: Optional["int"] = Field(None, alias="endLineNumber")
    end_column_position: Optional["int"] = Field(None, alias="endColumnPosition")
    syntax_error: Optional["bool"] = Field(None, alias="syntaxError")


class ComputeCallerInfo(PythonCoreBaseModel):
    object_id: Optional["str"] = Field(None, alias="objectId")
    object_type: Optional["ComputeCallerType"] = Field(None, alias="objectType")


class DataCommand(PythonCoreBaseModel):
    cube_id: Optional["str"] = Field(None, alias="cubeId")
    commands: Optional["List[Optional[DataQuery]]"] = Field(None, alias="commands")


class DataCommandBatchRequest(PythonCoreBaseModel):
    variables: Optional["List[Optional[Variable]]"] = Field(None, alias="variables")
    requests: Optional["List[Optional[DataCommandBatchTransport]]"] = Field(None, alias="requests")


class DataCommandBatchTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    request: Optional["DataCommand"] = Field(None, alias="request")


class DataQuery(PythonCoreBaseModel):
    computation_id: Optional["int"] = Field(None, alias="computationId")
    queries: Optional["List[Optional[str]]"] = Field(None, alias="queries")
    is_transient: Optional["bool"] = Field(None, alias="isTransient")


class LayerComputeTransport(PythonCoreBaseModel):
    caller_info: Optional["ComputeCallerInfo"] = Field(None, alias="callerInfo")
    layer: Optional["LayerTransport"] = Field(None, alias="layer")
    request: Optional["QueryRequest"] = Field(None, alias="request")
    draft: Optional["bool"] = Field(None, alias="draft")


class QueryRequest(PythonCoreBaseModel):
    batch_request: Optional["DataCommandBatchRequest"] = Field(None, alias="batchRequest")
    filters: Optional["List[Optional[str]]"] = Field(None, alias="filters")


class Variable(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    type_: Optional["str"] = Field(None, alias="type")
    value: Optional["str"] = Field(None, alias="value")


class DataPermissionRule(PythonCoreBaseModel):
    values: Optional["List[Optional[str]]"] = Field(None, alias="values")
    column_id: Optional["str"] = Field(None, alias="columnId")
    table_id: Optional["str"] = Field(None, alias="tableId")


class ExportStatus(PythonCoreBaseEnum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class Kpi(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    template: Optional["str"] = Field(None, alias="template")
    parameter_count: Optional["int"] = Field(None, alias="parameterCount")
    error: Optional["str"] = Field(None, alias="error")
    formula: Optional["str"] = Field(None, alias="formula")


class KpiInformation(PythonCoreBaseModel):
    kpis: Optional["Dict[str, Optional[Kpi]]"] = Field(None, alias="kpis")


class BatchQueryByKnowledgeModelIdTransport(PythonCoreBaseModel):
    draft: Optional["bool"] = Field(None, alias="draft")
    filters: Optional["List[Optional[str]]"] = Field(None, alias="filters")
    requests: Optional["List[Optional[DataCommandBatchTransport]]"] = Field(None, alias="requests")


class PostBatchQueryTransport(PythonCoreBaseModel):
    analysis_commands: Optional["List[Optional[DataCommandBatchTransport]]"] = Field(None, alias="analysisCommands")
    query_environment: Optional["QueryEnvironment"] = Field(None, alias="queryEnvironment")


class QueryEnvironment(PythonCoreBaseModel):
    accelerator_session_id: Optional["str"] = Field(None, alias="acceleratorSessionId")
    process_id: Optional["str"] = Field(None, alias="processId")
    user_id: Optional["str"] = Field(None, alias="userId")
    user_name: Optional["str"] = Field(None, alias="userName")
    load_script: Optional["str"] = Field(None, alias="loadScript")
    kpi_infos: Optional["KpiInformation"] = Field(None, alias="kpiInfos")
    data_permission_rules: Optional["List[Optional[DataPermissionRule]]"] = Field(None, alias="dataPermissionRules")
    data_permission_strategy: Optional["DataPermissionStrategy"] = Field(None, alias="dataPermissionStrategy")


class LayerPhoenixComputeTransport(PythonCoreBaseModel):
    caller_info: Optional["ComputeCallerInfo"] = Field(None, alias="callerInfo")
    layer: Optional["LayerTransport"] = Field(None, alias="layer")
    queries: Optional["List[Optional[LayerBasedQuery]]"] = Field(None, alias="queries")
    draft: Optional["bool"] = Field(None, alias="draft")


class AcceleratorSelectionFilter(PythonCoreBaseModel):
    default_inactive: Optional["bool"] = Field(None, alias="defaultInactive")
    kind: Optional["AcceleratorSelectionKind"] = Field(None, alias="kind")
    expression: Optional["str"] = Field(None, alias="expression")
    type_: Optional["AcceleratorSelectionType"] = Field(None, alias="type")
    enabled: Optional["bool"] = Field(None, alias="enabled")
    null_selected: Optional["bool"] = Field(None, alias="nullSelected")
    entries_selected: Optional["int"] = Field(None, alias="entriesSelected")
    entries_total: Optional["int"] = Field(None, alias="entriesTotal")
    values_total: Optional["int"] = Field(None, alias="valuesTotal")
    values_selected: Optional["int"] = Field(None, alias="valuesSelected")
    cases_total: Optional["int"] = Field(None, alias="casesTotal")
    cases_selected: Optional["int"] = Field(None, alias="casesSelected")
    table_name: Optional["str"] = Field(None, alias="tableName")
    data_type: Optional["AcceleratorSelectionType"] = Field(None, alias="dataType")
    configuration: Optional["Any"] = Field(None, alias="configuration")
    pinned: Optional["bool"] = Field(None, alias="pinned")
    temporary: Optional["bool"] = Field(None, alias="temporary")
    id: Optional["str"] = Field(None, alias="id")
    position: Optional["int"] = Field(None, alias="position")
    volatile_filter: Optional["bool"] = Field(None, alias="volatileFilter")
    name: Optional["str"] = Field(None, alias="name")
    format: Optional["str"] = Field(None, alias="format")
    first_selected_values: Optional["List[Optional[str]]"] = Field(None, alias="firstSelectedValues")
    first_non_selected_values: Optional["List[Optional[str]]"] = Field(None, alias="firstNonSelectedValues")


class AcceleratorTableStatistics(PythonCoreBaseModel):
    table_name: Optional["str"] = Field(None, alias="tableName")
    table_count: Optional["int"] = Field(None, alias="tableCount")
    filtered_count: Optional["int"] = Field(None, alias="filteredCount")
    case_table: Optional["bool"] = Field(None, alias="caseTable")
    activity_table: Optional["bool"] = Field(None, alias="activityTable")


class DataCommandBatchListResult(PythonCoreBaseModel):
    results: Optional["List[Optional[DataCommandBatchResultTransport]]"] = Field(None, alias="results")
    error: Optional["str"] = Field(None, alias="error")
    batch_list_id: Optional["int"] = Field(None, alias="batchListId")


class DataCommandBatchResultTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    result: Optional["PqlMultiResultTransport"] = Field(None, alias="result")


class ExplainNode(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    description: Optional["str"] = Field(None, alias="description")
    input_nodes: Optional["List[Optional[ExplainNode]]"] = Field(None, alias="inputNodes")


class MessageTransport(PythonCoreBaseModel):
    translation_code: Optional["str"] = Field(None, alias="translationCode")
    parameters: Optional["List[Optional[TranslationParameter]]"] = Field(None, alias="parameters")


class MissingColumnInfo(PythonCoreBaseModel):
    column_name: Optional["str"] = Field(None, alias="columnName")
    table_name: Optional["str"] = Field(None, alias="tableName")
    potential_meant_columns: Optional["List[Optional[str]]"] = Field(None, alias="potentialMeantColumns")


class PqlCompilationExceptionTransport(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")


class PqlMultiResultTransport(PythonCoreBaseModel):
    components: Optional["Dict[str, Optional[PqlResultTransport]]"] = Field(None, alias="components")
    selections: Optional["List[Optional[AcceleratorSelectionFilter]]"] = Field(None, alias="selections")
    table_statistics: Optional["List[Optional[AcceleratorTableStatistics]]"] = Field(None, alias="tableStatistics")
    message: Optional["str"] = Field(None, alias="message")
    error_messages: Optional["List[Optional[MessageTransport]]"] = Field(None, alias="errorMessages")
    pql_compilation_exception: Optional["PqlCompilationExceptionTransport"] = Field(
        None, alias="pqlCompilationException"
    )
    pql_syntax_exception: Optional["PqlSyntaxExceptionTransport"] = Field(None, alias="pqlSyntaxException")
    pql_token_manager_exception: Optional["PqlTokenManagerExceptionTransport"] = Field(
        None, alias="pqlTokenManagerException"
    )
    missing_columns: Optional["Dict[str, Optional[List[Optional[MissingColumnInfo]]]]"] = Field(
        None, alias="missingColumns"
    )


class PqlResultQueryStatistics(PythonCoreBaseModel):
    query_execution_time_ms: Optional["int"] = Field(None, alias="queryExecutionTimeMs")
    query_compile_time_ms: Optional["int"] = Field(None, alias="queryCompileTimeMs")
    query_result_size_in_bytes: Optional["int"] = Field(None, alias="queryResultSizeInBytes")


class PqlResultTransport(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")
    error_messages: Optional["List[Optional[MessageTransport]]"] = Field(None, alias="errorMessages")
    warnings: Optional["List[Optional[str]]"] = Field(None, alias="warnings")
    warning_messages: Optional["List[Optional[MessageTransport]]"] = Field(None, alias="warningMessages")
    result_index: Optional["Dict[str, Optional[int]]"] = Field(None, alias="resultIndex")
    results: Optional["List[Optional[TableResult]]"] = Field(None, alias="results")
    query_statistics: Optional["PqlResultQueryStatistics"] = Field(None, alias="queryStatistics")
    load_version: Optional["str"] = Field(None, alias="loadVersion")
    augmentation_table_used: Optional["bool"] = Field(None, alias="augmentationTableUsed")


class PqlSyntaxExceptionTransport(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")
    token: Optional["str"] = Field(None, alias="token")
    begin_column: Optional["int"] = Field(None, alias="beginColumn")
    begin_line: Optional["int"] = Field(None, alias="beginLine")
    end_column: Optional["int"] = Field(None, alias="endColumn")
    end_line: Optional["int"] = Field(None, alias="endLine")


class PqlTokenManagerExceptionTransport(PythonCoreBaseModel):
    message: Optional["str"] = Field(None, alias="message")


class TableMetaData(PythonCoreBaseModel):
    column_name: Optional["str"] = Field(None, alias="columnName")
    column_type: Optional["str"] = Field(None, alias="columnType")
    expression_lhs: Optional["str"] = Field(None, alias="expressionLhs")
    format: Optional["str"] = Field(None, alias="format")


class TableResult(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    utc_timestamps: Optional["bool"] = Field(None, alias="utcTimestamps")
    explain_nodes: Optional["List[Optional[ExplainNode]]"] = Field(None, alias="explainNodes")
    meta_data: Optional["List[Optional[TableMetaData]]"] = Field(None, alias="metaData")
    data: Optional["List[Optional[List[Optional[Any]]]]"] = Field(None, alias="data")
    string_hashes: Optional["List[Optional[List[Optional[str]]]]"] = Field(None, alias="stringHashes")
    rids: Optional["List[Optional[int]]"] = Field(None, alias="rids")
    ids: Optional["List[Optional[List[Optional[int]]]]"] = Field(None, alias="ids")
    overall_count: Optional["int"] = Field(None, alias="overallCount")
    offset: Optional["int"] = Field(None, alias="offset")
    count: Optional["int"] = Field(None, alias="count")
    export_chunks: Optional["int"] = Field(None, alias="exportChunks")
    error: Optional["bool"] = Field(None, alias="error")
    message: Optional["str"] = Field(None, alias="message")
    selected: Optional["List[Optional[List[Optional[bool]]]]"] = Field(None, alias="selected")
    available: Optional["List[Optional[List[Optional[bool]]]]"] = Field(None, alias="available")
    has_others: Optional["List[Optional[bool]]"] = Field(None, alias="hasOthers")
    others: Optional["List[Optional[Any]]"] = Field(None, alias="others")
    warnings: Optional["List[Optional[str]]"] = Field(None, alias="warnings")
    common_table_name: Optional["str"] = Field(None, alias="commonTableName")


class TranslationParameter(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    value: Optional["str"] = Field(None, alias="value")


class DataModelVariableTransport(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    description: Optional["str"] = Field(None, alias="description")


class KnowledgeModelWithDataModelTransport(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    name: Optional["str"] = Field(None, alias="name")
    root_key: Optional["str"] = Field(None, alias="rootKey")
    parent_node_id: Optional["str"] = Field(None, alias="parentNodeId")
    data_model_variable: Optional["DataModelVariableTransport"] = Field(None, alias="dataModelVariable")


class ProcessTypeValidationRequest(PythonCoreBaseModel):
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    process_type: Optional["ProcessType"] = Field(None, alias="processType")


class ProcessTypeValidationResponse(PythonCoreBaseModel):
    kpi_to_validation: Optional["Dict[str, Optional[ProcessWorkspaceKpiValidationMessage]]"] = Field(
        None, alias="kpiToValidation"
    )


class ProcessWorkspaceKpiValidationMessage(PythonCoreBaseModel):
    status: Optional["ProcessWorkspaceKpiValidationStatus"] = Field(None, alias="status")
    pql_errors: Optional["str"] = Field(None, alias="pqlErrors")


class CloneRequestTransport(PythonCoreBaseModel):
    source_teams: Optional["List[Optional[TeamSlimTransport]]"] = Field(None, alias="sourceTeams")


class TeamSlimTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    domain: Optional["str"] = Field(None, alias="domain")
    clone_data: Optional["bool"] = Field(None, alias="cloneData")


class CloneResultTransport(PythonCoreBaseModel):
    cloned_source_teams: Optional["List[Optional[TeamSlimTransport]]"] = Field(None, alias="clonedSourceTeams")
    failed_source_teams: Optional["List[Optional[TeamSlimTransport]]"] = Field(None, alias="failedSourceTeams")


class EraserLogMessageTransport(PythonCoreBaseModel):
    team_id: Optional["str"] = Field(None, alias="teamId")
    date: Optional["PythonCoreDatetime"] = Field(None, alias="date")
    message: Optional["str"] = Field(None, alias="message")


class ExportingJobConfigurationTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    job_type: Optional["JobType"] = Field(None, alias="jobType")
    title: Optional["str"] = Field(None, alias="title")
    layer_based_query_request: Optional["LayerBasedQueryRequest"] = Field(None, alias="layerBasedQueryRequest")
    layer_id_name: Optional["str"] = Field(None, alias="layerIdName")
    draft_layer: Optional["bool"] = Field(None, alias="draftLayer")
    user_id: Optional["str"] = Field(None, alias="userId")


class ExportInitializationTransport(PythonCoreBaseModel):
    order_id: Optional["str"] = Field(None, alias="orderId")


class DataModelColumnTransport(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    type_: Optional["ColumnType"] = Field(None, alias="type")
    primary_key: Optional["bool"] = Field(None, alias="primaryKey")


class DataModelConfigurationTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    activity_table_id: Optional["str"] = Field(None, alias="activityTableId")
    case_table_id: Optional["str"] = Field(None, alias="caseTableId")
    default_configuration: Optional["bool"] = Field(None, alias="defaultConfiguration")
    case_id_column: Optional["str"] = Field(None, alias="caseIdColumn")
    activity_column: Optional["str"] = Field(None, alias="activityColumn")
    timestamp_column: Optional["str"] = Field(None, alias="timestampColumn")
    sorting_column: Optional["str"] = Field(None, alias="sortingColumn")
    end_timestamp_column: Optional["str"] = Field(None, alias="endTimestampColumn")
    cost_column: Optional["str"] = Field(None, alias="costColumn")
    user_column: Optional["str"] = Field(None, alias="userColumn")
    use_parallel_process: Optional["bool"] = Field(None, alias="useParallelProcess")
    parallel_process_parent_column: Optional["str"] = Field(None, alias="parallelProcessParentColumn")
    parallel_process_child_column: Optional["str"] = Field(None, alias="parallelProcessChildColumn")


class DataModelCustomCalendarEntryTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    day: Optional["CalendarDay"] = Field(None, alias="day")
    working_day: Optional["bool"] = Field(None, alias="workingDay")
    start_time: Optional["int"] = Field(None, alias="startTime")
    end_time: Optional["int"] = Field(None, alias="endTime")


class DataModelCustomCalendarTransport(PythonCoreBaseModel):
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    entries: Optional["List[Optional[DataModelCustomCalendarEntryTransport]]"] = Field(None, alias="entries")


class DataModelFactoryCalendarTransport(PythonCoreBaseModel):
    table_name: Optional["str"] = Field(None, alias="tableName")
    data_source_id: Optional["str"] = Field(None, alias="dataSourceId")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")


class DataModelForeignKeyColumnTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    source_column_name: Optional["str"] = Field(None, alias="sourceColumnName")
    target_column_name: Optional["str"] = Field(None, alias="targetColumnName")


class DataModelForeignKeyTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    source_table_id: Optional["str"] = Field(None, alias="sourceTableId")
    target_table_id: Optional["str"] = Field(None, alias="targetTableId")
    columns: Optional["List[Optional[DataModelForeignKeyColumnTransport]]"] = Field(None, alias="columns")


class DataModelTableTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    data_source_id: Optional["str"] = Field(None, alias="dataSourceId")
    name: Optional["str"] = Field(None, alias="name")
    alias: Optional["str"] = Field(None, alias="alias")
    columns: Optional["List[Optional[DataModelColumnTransport]]"] = Field(None, alias="columns")
    use_direct_storage: Optional["bool"] = Field(None, alias="useDirectStorage")
    primary_keys: Optional["List[Optional[str]]"] = Field(None, alias="primaryKeys")
    alias_or_name: Optional["str"] = Field(None, alias="aliasOrName")


class DataModelTransport(PythonCoreBaseModel):
    permissions: Optional["List[Optional[str]]"] = Field(None, alias="permissions")
    id: Optional["str"] = Field(None, alias="id")
    name: Optional["str"] = Field(None, alias="name")
    description: Optional["str"] = Field(None, alias="description")
    create_date: Optional["PythonCoreDatetime"] = Field(None, alias="createDate")
    changed_date: Optional["PythonCoreDatetime"] = Field(None, alias="changedDate")
    configuration_skipped: Optional["bool"] = Field(None, alias="configurationSkipped")
    pool_id: Optional["str"] = Field(None, alias="poolId")
    unavailable: Optional["bool"] = Field(None, alias="unavailable")
    editable: Optional["bool"] = Field(None, alias="editable")
    creator_user_id: Optional["str"] = Field(None, alias="creatorUserId")
    tables: Optional["List[Optional[DataModelTableTransport]]"] = Field(None, alias="tables")
    foreign_keys: Optional["List[Optional[DataModelForeignKeyTransport]]"] = Field(None, alias="foreignKeys")
    process_configurations: Optional["List[Optional[DataModelConfigurationTransport]]"] = Field(
        None, alias="processConfigurations"
    )
    data_model_calendar_type: Optional["DataModelCalendarType"] = Field(None, alias="dataModelCalendarType")
    factory_calendar: Optional["DataModelFactoryCalendarTransport"] = Field(None, alias="factoryCalendar")
    custom_calendar: Optional["DataModelCustomCalendarTransport"] = Field(None, alias="customCalendar")
    original_id: Optional["str"] = Field(None, alias="originalId")
    eventlog_automerge_enabled: Optional["bool"] = Field(None, alias="eventlogAutomergeEnabled")
    auto_merge_execution_mode: Optional["AutoMergeExecutionMode"] = Field(None, alias="autoMergeExecutionMode")
    object_id: Optional["str"] = Field(None, alias="objectId")
    event_log_count: Optional["int"] = Field(None, alias="eventLogCount")


class ComputeQueryTransport(PythonCoreBaseModel):
    formula: Optional["str"] = Field(None, alias="formula")
    query_type: Optional["QueryType"] = Field(None, alias="queryType")
    semantic_model_content: Optional["str"] = Field(None, alias="semanticModelContent")
    root_key: Optional["str"] = Field(None, alias="rootKey")
    semantic_model_key: Optional["str"] = Field(None, alias="semanticModelKey")


class ComputeBatchQueryTransport(PythonCoreBaseModel):
    queries: Optional["List[Optional[ComputeQuery]]"] = Field(None, alias="queries")
    semantic_model_content: Optional["str"] = Field(None, alias="semanticModelContent")
    root_key: Optional["str"] = Field(None, alias="rootKey")
    semantic_model_key: Optional["str"] = Field(None, alias="semanticModelKey")


class ComputeQuery(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    formula: Optional["str"] = Field(None, alias="formula")


class ComputeQueryResult(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    table_result: Optional["TableResult"] = Field(None, alias="tableResult")


class BatchQueryTransport(PythonCoreBaseModel):
    requests: Optional["List[Optional[DataCommandBatchTransport]]"] = Field(None, alias="requests")
    semantic_model_content: Optional["str"] = Field(None, alias="semanticModelContent")
    root_key: Optional["str"] = Field(None, alias="rootKey")


class NodeUsageTransport(PythonCoreBaseModel):
    id: Optional["str"] = Field(None, alias="id")
    key: Optional["str"] = Field(None, alias="key")
    root_key: Optional["str"] = Field(None, alias="rootKey")
    name: Optional["str"] = Field(None, alias="name")
    asset_type: Optional["str"] = Field(None, alias="assetType")
    source_objects: Optional["List[Optional[SourceUsageMetadata]]"] = Field(None, alias="sourceObjects")


class LayerYamlTransport(PythonCoreBaseModel):
    yaml: Optional["str"] = Field(None, alias="yaml")
    with_comments: Optional["bool"] = Field(None, alias="withComments")


class LayerBaseTransport(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    version: Optional["str"] = Field(None, alias="version")
    app_store_based: Optional["bool"] = Field(None, alias="appStoreBased")
    name: Optional["str"] = Field(None, alias="name")
    root_name: Optional["str"] = Field(None, alias="rootName")


class Feature(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    enabled: Optional["bool"] = Field(None, alias="enabled")


class ValidatedKnowledgeRepository(PythonCoreBaseModel):
    knowledge_repository: Optional["LayerTransport"] = Field(None, alias="knowledgeRepository")
    validity: Optional["Dict[str, Optional[ProcessWorkspaceKpiValidationMessage]]"] = Field(None, alias="validity")


class PqlEntity(PythonCoreBaseModel):
    table: Optional["str"] = Field(None, alias="table")
    column: Optional["str"] = Field(None, alias="column")


class ProcessWorkspacePqlEntityTransport(PythonCoreBaseModel):
    process_entity_map: Optional["Dict[str, Optional[Dict[str, Optional[List[Optional[PqlEntity]]]]]]"] = Field(
        None, alias="processEntityMap"
    )


class ComputePoolTransport(PythonCoreBaseModel):
    permissions: Optional["List[Optional[str]]"] = Field(None, alias="permissions")
    id: Optional["str"] = Field(None, alias="id")
    name: Optional["str"] = Field(None, alias="name")
    connected: Optional["bool"] = Field(None, alias="connected")
    object_id: Optional["str"] = Field(None, alias="objectId")


class StudioComputeNodeDescriptor(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    pool_id: Optional["str"] = Field(None, alias="poolId")


class StudioDataModelTransport(PythonCoreBaseModel):
    node: Optional["StudioComputeNodeDescriptor"] = Field(None, alias="node")
    loaded: Optional["bool"] = Field(None, alias="loaded")
    data_pool: Optional["ComputePoolTransport"] = Field(None, alias="dataPool")


class VariableAssignment(PythonCoreBaseModel):
    key: Optional["str"] = Field(None, alias="key")
    value: Optional["Any"] = Field(None, alias="value")
    type_: Optional["str"] = Field(None, alias="type")


class SemanticLayerConsumer(PythonCoreBaseModel):
    name: Optional["str"] = Field(None, alias="name")
    type_: Optional["str"] = Field(None, alias="type")
    href: Optional["str"] = Field(None, alias="href")
    source: Optional["str"] = Field(None, alias="source")
    count: Optional["int"] = Field(None, alias="count")


class BusinessRecordMetadataPql(PythonCoreBaseModel):
    pql: Optional["str"] = Field(None, alias="pql")


class DataModelColumn(PythonCoreBaseModel):
    pql: Optional["str"] = Field(None, alias="pql")
    table_name: Optional["str"] = Field(None, alias="tableName")
    column_name: Optional["str"] = Field(None, alias="columnName")


class ValidationUniqueTransport(PythonCoreBaseModel):
    unique: Optional["bool"] = Field(None, alias="unique")


class DocumentationItem(PythonCoreBaseModel):
    title: Optional["str"] = Field(None, alias="title")
    name_on_editor: Optional["str"] = Field(None, alias="nameOnEditor")
    tag: Optional["str"] = Field(None, alias="tag")
    description: Optional["str"] = Field(None, alias="description")
    link: Optional["str"] = Field(None, alias="link")
    required: Optional["bool"] = Field(None, alias="required")
    required_fields: Optional["List[Optional[str]]"] = Field(None, alias="requiredFields")
    possible_values: Optional["List[Optional[str]]"] = Field(None, alias="possibleValues")
    syntax: Optional["List[Optional[DocumentationItemSyntax]]"] = Field(None, alias="syntax")


class DocumentationItemSyntax(PythonCoreBaseModel):
    description: Optional["str"] = Field(None, alias="description")
    type_: Optional["SnippetType"] = Field(None, alias="type")
    example: Optional["str"] = Field(None, alias="example")
    example_as_node: Optional["JsonNode"] = Field(None, alias="exampleAsNode")
    snippet: Optional["str"] = Field(None, alias="snippet")
    snippet_as_node: Optional["JsonNode"] = Field(None, alias="snippetAsNode")
    hide_use_snippet: Optional["bool"] = Field(None, alias="hideUseSnippet")


class DocumentationTransport(PythonCoreBaseModel):
    documentation_item_list: Optional["List[Optional[DocumentationItem]]"] = Field(None, alias="documentationItemList")


class ComputeNodeDescriptor(PythonCoreBaseModel):
    permissions: Optional["List[Optional[str]]"] = Field(None, alias="permissions")
    name: Optional["str"] = Field(None, alias="name")
    data_model_id: Optional["str"] = Field(None, alias="dataModelId")
    pool_id: Optional["str"] = Field(None, alias="poolId")
    object_id: Optional["str"] = Field(None, alias="objectId")


class DataModelLoad(PythonCoreBaseModel):
    load_status: Optional["DataModelLoadStatus"] = Field(None, alias="loadStatus")
    live_data_model_available: Optional["bool"] = Field(None, alias="liveDataModelAvailable")


ExceptionReference.model_rebuild()
FrontendHandledBackendError.model_rebuild()
FinalModelOptions.model_rebuild()
YamlMetadata.model_rebuild()
AssetMetadataTransport.model_rebuild()
AssetUsage.model_rebuild()
ContentNodeBaseTransport.model_rebuild()
ContentNodeTransport.model_rebuild()
RelatedAsset.model_rebuild()
SourceUsageMetadata.model_rebuild()
TargetUsageMetadata.model_rebuild()
VariableDefinition.model_rebuild()
VariableMetadata.model_rebuild()
AttributeMetadata.model_rebuild()
AugmentedAttributeMetadata.model_rebuild()
BusinessRecordMetadata.model_rebuild()
DataTriggerMetadata.model_rebuild()
NewAttributeMetadata.model_rebuild()
PqlBaseMetadata.model_rebuild()
RecordPriorityMetadata.model_rebuild()
AnomalyKpiMetadata.model_rebuild()
FlagAnomalyTransport.model_rebuild()
BaseMetadata.model_rebuild()
KpiBenchmarking.model_rebuild()
KpiBenchmarkingAction.model_rebuild()
KpiMetadata.model_rebuild()
ParameterMetadata.model_rebuild()
PerformanceBucket.model_rebuild()
TargetMetadata.model_rebuild()
FilterMetadata.model_rebuild()
EventLogTransitionTransport.model_rebuild()
EventLogTransport.model_rebuild()
SingleEventLogMetadata.model_rebuild()
ActionInput.model_rebuild()
ActionMetadata.model_rebuild()
ActivityMetadata.model_rebuild()
AlertMetric.model_rebuild()
AnomalyMetadata.model_rebuild()
EventLogKpi.model_rebuild()
EventLogKpiView.model_rebuild()
EventLogMetadata.model_rebuild()
EventLogTransition.model_rebuild()
EventLogTransitionKpi.model_rebuild()
FinalWithAutogeneratedBaseRequest.model_rebuild()
KpiWithAlert.model_rebuild()
LayerBase.model_rebuild()
LayerMetadata.model_rebuild()
LayerTransport.model_rebuild()
NewEventLogMetadata.model_rebuild()
FinalLayerTransport.model_rebuild()
FrontendLogTransport.model_rebuild()
ColumnConfig.model_rebuild()
KpiParameter.model_rebuild()
LayerBasedQuery.model_rebuild()
LayerBasedQueryRequest.model_rebuild()
Pagination.model_rebuild()
QueryFilter.model_rebuild()
TableColumnSorting.model_rebuild()
TaskFilter.model_rebuild()
ColumnHeader.model_rebuild()
RecordAlert.model_rebuild()
RecordTask.model_rebuild()
RowCell.model_rebuild()
TableResponse.model_rebuild()
TableRow.model_rebuild()
LayerBasedBatchQueryRequest.model_rebuild()
PqlErrorTransport.model_rebuild()
ComputeCallerInfo.model_rebuild()
DataCommand.model_rebuild()
DataCommandBatchRequest.model_rebuild()
DataCommandBatchTransport.model_rebuild()
DataQuery.model_rebuild()
LayerComputeTransport.model_rebuild()
QueryRequest.model_rebuild()
Variable.model_rebuild()
DataPermissionRule.model_rebuild()
Kpi.model_rebuild()
KpiInformation.model_rebuild()
PostBatchQueryTransport.model_rebuild()
QueryEnvironment.model_rebuild()
LayerPhoenixComputeTransport.model_rebuild()
AcceleratorSelectionFilter.model_rebuild()
AcceleratorTableStatistics.model_rebuild()
DataCommandBatchListResult.model_rebuild()
DataCommandBatchResultTransport.model_rebuild()
ExplainNode.model_rebuild()
MessageTransport.model_rebuild()
MissingColumnInfo.model_rebuild()
PqlCompilationExceptionTransport.model_rebuild()
PqlMultiResultTransport.model_rebuild()
PqlResultQueryStatistics.model_rebuild()
PqlResultTransport.model_rebuild()
PqlSyntaxExceptionTransport.model_rebuild()
PqlTokenManagerExceptionTransport.model_rebuild()
TableMetaData.model_rebuild()
TableResult.model_rebuild()
TranslationParameter.model_rebuild()
DataModelVariableTransport.model_rebuild()
KnowledgeModelWithDataModelTransport.model_rebuild()
ProcessTypeValidationRequest.model_rebuild()
ProcessTypeValidationResponse.model_rebuild()
ProcessWorkspaceKpiValidationMessage.model_rebuild()
CloneRequestTransport.model_rebuild()
TeamSlimTransport.model_rebuild()
CloneResultTransport.model_rebuild()
EraserLogMessageTransport.model_rebuild()
ExportingJobConfigurationTransport.model_rebuild()
ExportInitializationTransport.model_rebuild()
DataModelColumnTransport.model_rebuild()
DataModelConfigurationTransport.model_rebuild()
DataModelCustomCalendarEntryTransport.model_rebuild()
DataModelCustomCalendarTransport.model_rebuild()
DataModelFactoryCalendarTransport.model_rebuild()
DataModelForeignKeyColumnTransport.model_rebuild()
DataModelForeignKeyTransport.model_rebuild()
DataModelTableTransport.model_rebuild()
DataModelTransport.model_rebuild()
ComputeQueryTransport.model_rebuild()
ComputeBatchQueryTransport.model_rebuild()
ComputeQuery.model_rebuild()
ComputeQueryResult.model_rebuild()
BatchQueryTransport.model_rebuild()
NodeUsageTransport.model_rebuild()
LayerYamlTransport.model_rebuild()
LayerBaseTransport.model_rebuild()
Feature.model_rebuild()
ValidatedKnowledgeRepository.model_rebuild()
PqlEntity.model_rebuild()
ProcessWorkspacePqlEntityTransport.model_rebuild()
ComputePoolTransport.model_rebuild()
StudioComputeNodeDescriptor.model_rebuild()
StudioDataModelTransport.model_rebuild()
VariableAssignment.model_rebuild()
SemanticLayerConsumer.model_rebuild()
BusinessRecordMetadataPql.model_rebuild()
DataModelColumn.model_rebuild()
ValidationUniqueTransport.model_rebuild()
DocumentationItem.model_rebuild()
DocumentationItemSyntax.model_rebuild()
DocumentationTransport.model_rebuild()
ComputeNodeDescriptor.model_rebuild()
DataModelLoad.model_rebuild()
MultiStatementQueryResult.model_rebuild()
ProxyQueryResponseTransportV2.model_rebuild()
ProxyTableResultV2.model_rebuild()
ProxyColumnMetaDataV2.model_rebuild()
ProxyQueryStatisticsV2.model_rebuild()
ProxyStatusTransport.model_rebuild()
ProxyErrorMessage.model_rebuild()
ProxyWarningMessage.model_rebuild()
KnowledgeModelQueryRequest.model_rebuild()



class SemanticLayerClientBase(ABC):
    client: AsyncClient

    def __init__(self, base_url: str, **kwargs: Any) -> None:
        self.client = AsyncClient(base_url=base_url, **kwargs)

    async def put_api_semantic_models_model_entity_id_no_validation(
        self, model_entity_id: str, request_body: YamlMetadata, **kwargs: Any
    ) -> ContentNodeTransport:
        return await self.client.request(
            method="PUT",
            url=f"/api/semantic-models/{model_entity_id}/no-validation",
            request_body=request_body,
            parse_json=True,
            type_=ContentNodeTransport,
            **kwargs,
        )

    async def put_api_knowledge_model_layer_asset_id_variables_variable_id(
        self, layer_asset_id: str, variable_id: str, request_body: VariableMetadata, **kwargs: Any
    ) -> VariableMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/variables/{variable_id}",
            request_body=request_body,
            parse_json=True,
            type_=VariableMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_variables_variable_id(
        self, layer_asset_id: str, variable_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/variables/{variable_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_records_record_id(
        self, layer_asset_id: str, record_id: str, request_body: BusinessRecordMetadata, **kwargs: Any
    ) -> BusinessRecordMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}",
            request_body=request_body,
            parse_json=True,
            type_=BusinessRecordMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_records_record_id(
        self, layer_asset_id: str, record_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_records_record_id_flags_flag_id(
        self, layer_asset_id: str, record_id: str, flag_id: str, request_body: FlagAnomalyTransport, **kwargs: Any
    ) -> PqlBaseMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/flags/{flag_id}",
            request_body=request_body,
            parse_json=True,
            type_=PqlBaseMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_records_record_id_flags_flag_id(
        self, layer_asset_id: str, record_id: str, flag_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/flags/{flag_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_records_record_id_augmented_attributes_attribute_id(
        self,
        layer_asset_id: str,
        record_id: str,
        attribute_id: str,
        request_body: AugmentedAttributeMetadata,
        **kwargs: Any,
    ) -> AugmentedAttributeMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/augmented-attributes/{attribute_id}",
            request_body=request_body,
            parse_json=True,
            type_=AugmentedAttributeMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_records_record_id_augmented_attributes_attribute_id(
        self, layer_asset_id: str, record_id: str, attribute_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/augmented-attributes/{attribute_id}",
            **kwargs,
        )

    async def put_api_knowledge_model_layer_asset_id_records_record_id_attributes_attribute_id(
        self, layer_asset_id: str, record_id: str, attribute_id: str, request_body: AttributeMetadata, **kwargs: Any
    ) -> AttributeMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/attributes/{attribute_id}",
            request_body=request_body,
            parse_json=True,
            type_=AttributeMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_records_record_id_attributes_attribute_id(
        self, layer_asset_id: str, record_id: str, attribute_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/attributes/{attribute_id}",
            **kwargs,
        )

    async def put_api_knowledge_model_layer_asset_id_kpis_kpi_id(
        self, layer_asset_id: str, kpi_id: str, request_body: KpiMetadata, **kwargs: Any
    ) -> KpiMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/kpis/{kpi_id}",
            request_body=request_body,
            parse_json=True,
            type_=KpiMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_kpis_kpi_id(
        self, layer_asset_id: str, kpi_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/kpis/{kpi_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_filters_filter_id(
        self, layer_asset_id: str, filter_id: str, request_body: FilterMetadata, **kwargs: Any
    ) -> FilterMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/filters/{filter_id}",
            request_body=request_body,
            parse_json=True,
            type_=FilterMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_filters_filter_id(
        self, layer_asset_id: str, filter_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/filters/{filter_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_event_logs_event_log_id(
        self, layer_asset_id: str, event_log_id: str, request_body: EventLogTransport, **kwargs: Any
    ) -> SingleEventLogMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/event-logs/{event_log_id}",
            request_body=request_body,
            parse_json=True,
            type_=SingleEventLogMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_event_logs_event_log_id(
        self, layer_asset_id: str, event_log_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/event-logs/{event_log_id}", **kwargs
        )

    async def put_api_knowledge_model_layer_asset_id_actions_action_id(
        self, layer_asset_id: str, action_id: str, request_body: ActionMetadata, **kwargs: Any
    ) -> ActionMetadata:
        return await self.client.request(
            method="PUT",
            url=f"/api/knowledge-model/{layer_asset_id}/actions/{action_id}",
            request_body=request_body,
            parse_json=True,
            type_=ActionMetadata,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_actions_action_id(
        self, layer_asset_id: str, action_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/actions/{action_id}", **kwargs
        )

    async def post_api_semantic_models(self, request_body: YamlMetadata, **kwargs: Any) -> ContentNodeTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/semantic-models",
            request_body=request_body,
            parse_json=True,
            type_=ContentNodeTransport,
            **kwargs,
        )

    async def post_api_process_workspace_layers_extension(
        self, request_body: FinalWithAutogeneratedBaseRequest, **kwargs: Any
    ) -> FinalLayerTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/process-workspace/layers/extension",
            request_body=request_body,
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def post_api_logging_frontend(self, request_body: FrontendLogTransport, **kwargs: Any) -> None:
        return await self.client.request(
            method="POST", url=f"/api/logging/frontend", request_body=request_body, **kwargs
        )

    async def post_api_layers_id_name_query(
        self, id_name: str, request_body: LayerBasedQueryRequest, is_draft: Optional["bool"] = None, **kwargs: Any
    ) -> TableResponse:
        params: Dict[str, Any] = {}
        if is_draft is not None:
            if isinstance(is_draft, PythonCoreBaseModel):
                params.update(is_draft.json_dict(by_alias=True))
            elif isinstance(is_draft, dict):
                params.update(is_draft)
            else:
                params["isDraft"] = is_draft
        return await self.client.request(
            method="POST",
            url=f"/api/layers/{id_name}/query",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=TableResponse,
            **kwargs,
        )

    async def post_api_layers_id_name_query_batch(
        self, id_name: str, request_body: LayerBasedBatchQueryRequest, is_draft: Optional["bool"] = None, **kwargs: Any
    ) -> List[Optional[TableResponse]]:
        params: Dict[str, Any] = {}
        if is_draft is not None:
            if isinstance(is_draft, PythonCoreBaseModel):
                params.update(is_draft.json_dict(by_alias=True))
            elif isinstance(is_draft, dict):
                params.update(is_draft)
            else:
                params["isDraft"] = is_draft
        return await self.client.request(
            method="POST",
            url=f"/api/layers/{id_name}/query/batch",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[TableResponse]],
            **kwargs,
        )

    async def post_api_layer_id_name_validate_pql(
        self, id_name: str, request_body: YamlMetadata, root_key: Optional["str"] = None, **kwargs: Any
    ) -> List[Optional[PqlErrorTransport]]:
        params: Dict[str, Any] = {}
        if root_key is not None:
            if isinstance(root_key, PythonCoreBaseModel):
                params.update(root_key.json_dict(by_alias=True))
            elif isinstance(root_key, dict):
                params.update(root_key)
            else:
                params["rootKey"] = root_key
        return await self.client.request(
            method="POST",
            url=f"/api/layer/{id_name}/validate-pql",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[PqlErrorTransport]],
            **kwargs,
        )

    async def post_api_layer_id_name_final(
        self, id_name: str, request_body: FinalModelOptions, **kwargs: Any
    ) -> FinalLayerTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/layer/{id_name}/final",
            request_body=request_body,
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def post_api_layer_id_name_base(
        self, id_name: str, request_body: FinalModelOptions, **kwargs: Any
    ) -> FinalLayerTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/layer/{id_name}/base",
            request_body=request_body,
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def post_api_layer_final(
        self, request_body: YamlMetadata, root_key: Optional["str"] = None, **kwargs: Any
    ) -> FinalLayerTransport:
        params: Dict[str, Any] = {}
        if root_key is not None:
            if isinstance(root_key, PythonCoreBaseModel):
                params.update(root_key.json_dict(by_alias=True))
            elif isinstance(root_key, dict):
                params.update(root_key)
            else:
                params["rootKey"] = root_key
        return await self.client.request(
            method="POST",
            url=f"/api/layer/final",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_variables(
        self, layer_asset_id: str, request_body: VariableMetadata, **kwargs: Any
    ) -> VariableMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/variables",
            request_body=request_body,
            parse_json=True,
            type_=VariableMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records(
        self, layer_asset_id: str, request_body: BusinessRecordMetadata, **kwargs: Any
    ) -> BusinessRecordMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records",
            request_body=request_body,
            parse_json=True,
            type_=BusinessRecordMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_record_id_identifier_upsert(
        self, layer_asset_id: str, record_id: str, request_body: PqlBaseMetadata, **kwargs: Any
    ) -> PqlBaseMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/identifier/upsert",
            request_body=request_body,
            parse_json=True,
            type_=PqlBaseMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_record_id_flags(
        self, layer_asset_id: str, record_id: str, request_body: FlagAnomalyTransport, **kwargs: Any
    ) -> PqlBaseMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/flags",
            request_body=request_body,
            parse_json=True,
            type_=PqlBaseMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_record_id_augmented_attributes(
        self, layer_asset_id: str, record_id: str, request_body: AugmentedAttributeMetadata, **kwargs: Any
    ) -> AugmentedAttributeMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/augmented-attributes",
            request_body=request_body,
            parse_json=True,
            type_=AugmentedAttributeMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_record_id_attributes(
        self, layer_asset_id: str, record_id: str, request_body: AttributeMetadata, **kwargs: Any
    ) -> AttributeMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/attributes",
            request_body=request_body,
            parse_json=True,
            type_=AttributeMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_record_id_attributes_upsert(
        self, layer_asset_id: str, record_id: str, request_body: AttributeMetadata, **kwargs: Any
    ) -> AttributeMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/attributes/upsert",
            request_body=request_body,
            parse_json=True,
            type_=AttributeMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_records_upsert(
        self, layer_asset_id: str, request_body: BusinessRecordMetadata, **kwargs: Any
    ) -> BusinessRecordMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/records/upsert",
            request_body=request_body,
            parse_json=True,
            type_=BusinessRecordMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_kpis(
        self, layer_asset_id: str, request_body: KpiMetadata, **kwargs: Any
    ) -> KpiMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/kpis",
            request_body=request_body,
            parse_json=True,
            type_=KpiMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_kpis_upsert(
        self, layer_asset_id: str, request_body: KpiMetadata, **kwargs: Any
    ) -> KpiMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/kpis/upsert",
            request_body=request_body,
            parse_json=True,
            type_=KpiMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_filters(
        self, layer_asset_id: str, request_body: FilterMetadata, **kwargs: Any
    ) -> FilterMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/filters",
            request_body=request_body,
            parse_json=True,
            type_=FilterMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_filters_upsert(
        self, layer_asset_id: str, request_body: FilterMetadata, **kwargs: Any
    ) -> FilterMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/filters/upsert",
            request_body=request_body,
            parse_json=True,
            type_=FilterMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_event_logs(
        self, layer_asset_id: str, request_body: EventLogTransport, **kwargs: Any
    ) -> SingleEventLogMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/event-logs",
            request_body=request_body,
            parse_json=True,
            type_=SingleEventLogMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_layer_asset_id_actions(
        self, layer_asset_id: str, request_body: ActionMetadata, **kwargs: Any
    ) -> ActionMetadata:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/actions",
            request_body=request_body,
            parse_json=True,
            type_=ActionMetadata,
            **kwargs,
        )

    async def post_api_knowledge_model_resolve_query(
        self, request_body: LayerComputeTransport, **kwargs: Any
    ) -> PostBatchQueryTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/resolve-query",
            request_body=request_body,
            parse_json=True,
            type_=PostBatchQueryTransport,
            **kwargs,
        )

    async def post_api_knowledge_model_phoenix_compute(
        self, request_body: LayerPhoenixComputeTransport, **kwargs: Any
    ) -> List[Optional[TableResponse]]:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/phoenix-compute",
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[TableResponse]],
            **kwargs,
        )

    async def post_api_knowledge_model_compute(
        self, request_body: LayerComputeTransport, **kwargs: Any
    ) -> DataCommandBatchListResult:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/compute",
            request_body=request_body,
            parse_json=True,
            type_=DataCommandBatchListResult,
            **kwargs,
        )

    async def post_api_knowledge_model_by_data_model(
        self, request_body: KnowledgeModelWithDataModelTransport, **kwargs: Any
    ) -> LayerTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/by-data-model",
            request_body=request_body,
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def post_api_export_data_queries(
        self, request_body: ExportingJobConfigurationTransport, **kwargs: Any
    ) -> ExportInitializationTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/export-data-queries",
            request_body=request_body,
            parse_json=True,
            type_=ExportInitializationTransport,
            **kwargs,
        )

    async def post_api_data_models_by_knowledge_model_id_knowledge_model_id_reload(
        self, knowledge_model_id: str, **kwargs: Any
    ) -> DataModelTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/data-models/by-knowledge-model-id/{knowledge_model_id}/reload",
            parse_json=True,
            type_=DataModelTransport,
            **kwargs,
        )

    async def post_api_compute_query(self, request_body: ComputeQueryTransport, **kwargs: Any) -> TableResult:
        return await self.client.request(
            method="POST",
            url=f"/api/compute-query",
            request_body=request_body,
            parse_json=True,
            type_=TableResult,
            **kwargs,
        )

    async def post_api_compute_query_by_knowledge_model_id_knowledge_model_id(
        self, knowledge_model_id: str, request_body: ComputeQueryTransport, **kwargs: Any
    ) -> TableResult:
        return await self.client.request(
            method="POST",
            url=f"/api/compute-query/by-knowledge-model-id/{knowledge_model_id}",
            request_body=request_body,
            parse_json=True,
            type_=TableResult,
            **kwargs,
        )

    async def post_api_compute_query_batch(
        self, request_body: ComputeBatchQueryTransport, **kwargs: Any
    ) -> List[Optional[ComputeQueryResult]]:
        return await self.client.request(
            method="POST",
            url=f"/api/compute-query/batch",
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[ComputeQueryResult]],
            **kwargs,
        )

    async def post_api_compute_query_batch_by_semantic_model(
        self, request_body: BatchQueryTransport, **kwargs: Any
    ) -> DataCommandBatchListResult:
        return await self.client.request(
            method="POST",
            url=f"/api/compute-query/batch/by-semantic-model",
            request_body=request_body,
            parse_json=True,
            type_=DataCommandBatchListResult,
            **kwargs,
        )

    async def get_favicon_ico(self, **kwargs: Any) -> None:
        return await self.client.request(method="GET", url=f"/favicon.ico", **kwargs)

    async def get_api_views_by_root_key_root_key(
        self, root_key: str, **kwargs: Any
    ) -> List[Optional[ContentNodeTransport]]:
        return await self.client.request(
            method="GET",
            url=f"/api/views/by-root-key/{root_key}",
            parse_json=True,
            type_=List[Optional[ContentNodeTransport]],
            **kwargs,
        )

    async def get_api_semantic_models_root_key_key_usages(
        self,
        root_key: str,
        key: str,
        target_object_id: Optional["str"] = None,
        target_object_type: Optional["str"] = None,
        **kwargs: Any,
    ) -> List[Optional[NodeUsageTransport]]:
        params: Dict[str, Any] = {}
        if target_object_id is not None:
            if isinstance(target_object_id, PythonCoreBaseModel):
                params.update(target_object_id.json_dict(by_alias=True))
            elif isinstance(target_object_id, dict):
                params.update(target_object_id)
            else:
                params["targetObjectId"] = target_object_id
        if target_object_type is not None:
            if isinstance(target_object_type, PythonCoreBaseModel):
                params.update(target_object_type.json_dict(by_alias=True))
            elif isinstance(target_object_type, dict):
                params.update(target_object_type)
            else:
                params["targetObjectType"] = target_object_type
        return await self.client.request(
            method="GET",
            url=f"/api/semantic-models/{root_key}/{key}/usages",
            params=params,
            parse_json=True,
            type_=List[Optional[NodeUsageTransport]],
            **kwargs,
        )

    async def get_api_semantic_models_id(self, id: str, **kwargs: Any) -> ContentNodeTransport:
        return await self.client.request(
            method="GET", url=f"/api/semantic-models/{id}", parse_json=True, type_=ContentNodeTransport, **kwargs
        )

    async def get_api_semantic_models_id_content(self, id: str, **kwargs: Any) -> LayerYamlTransport:
        return await self.client.request(
            method="GET", url=f"/api/semantic-models/{id}/content", parse_json=True, type_=LayerYamlTransport, **kwargs
        )

    async def get_api_semantic_models_by_root_with_key_root_with_key(
        self, root_with_key: str, **kwargs: Any
    ) -> ContentNodeTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/semantic-models/by-root-with-key/{root_with_key}",
            parse_json=True,
            type_=ContentNodeTransport,
            **kwargs,
        )

    async def get_api_semantic_models_bases(
        self, root_key: Optional["str"] = None, **kwargs: Any
    ) -> List[Optional[LayerBaseTransport]]:
        params: Dict[str, Any] = {}
        if root_key is not None:
            if isinstance(root_key, PythonCoreBaseModel):
                params.update(root_key.json_dict(by_alias=True))
            elif isinstance(root_key, dict):
                params.update(root_key)
            else:
                params["rootKey"] = root_key
        return await self.client.request(
            method="GET",
            url=f"/api/semantic-models/bases",
            params=params,
            parse_json=True,
            type_=List[Optional[LayerBaseTransport]],
            **kwargs,
        )

    async def get_api_public_features_global(self, **kwargs: Any) -> List[Optional[Feature]]:
        return await self.client.request(
            method="GET", url=f"/api/public/features/global", parse_json=True, type_=List[Optional[Feature]], **kwargs
        )

    async def get_api_public_authentication_status(self, **kwargs: Any) -> bool:
        return await self.client.request(
            method="GET", url=f"/api/public/authentication/status", parse_json=True, type_=bool, **kwargs
        )

    async def get_api_process_workspace_layers_extension_layer_key(
        self, layer_key: str, **kwargs: Any
    ) -> FinalLayerTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/process-workspace/layers/extension/{layer_key}",
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def get_api_process_workspace_layers_data_model_sneak_peek_data_model_id(
        self, data_model_id: str, **kwargs: Any
    ) -> LayerTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/process-workspace/layers/data-model-sneak-peek/{data_model_id}",
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def get_api_process_workspace_layers_by_process_workspace_id_process_workspace_id(
        self, process_workspace_id: str, **kwargs: Any
    ) -> ValidatedKnowledgeRepository:
        return await self.client.request(
            method="GET",
            url=f"/api/process-workspace/layers/by-process-workspace-id/{process_workspace_id}",
            parse_json=True,
            type_=ValidatedKnowledgeRepository,
            **kwargs,
        )

    async def get_api_process_workspace_analysis_pql_entities(
        self, **kwargs: Any
    ) -> ProcessWorkspacePqlEntityTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/process-workspace/analysis/pql-entities",
            parse_json=True,
            type_=ProcessWorkspacePqlEntityTransport,
            **kwargs,
        )

    async def get_api_pm_nodes_root_key_assigned_data_models(
        self, root_key: str, **kwargs: Any
    ) -> List[Optional[StudioDataModelTransport]]:
        return await self.client.request(
            method="GET",
            url=f"/api/pm/nodes/{root_key}/assigned-data-models",
            parse_json=True,
            type_=List[Optional[StudioDataModelTransport]],
            **kwargs,
        )

    async def get_api_pm_nodes_key_variables(
        self, key: str, type_: Optional["str"] = None, **kwargs: Any
    ) -> List[Optional[VariableDefinition]]:
        params: Dict[str, Any] = {}
        if type_ is not None:
            if isinstance(type_, PythonCoreBaseModel):
                params.update(type_.json_dict(by_alias=True))
            elif isinstance(type_, dict):
                params.update(type_)
            else:
                params["type"] = type_
        return await self.client.request(
            method="GET",
            url=f"/api/pm/nodes/{key}/variables",
            params=params,
            parse_json=True,
            type_=List[Optional[VariableDefinition]],
            **kwargs,
        )

    async def get_api_pm_nodes_key_variables_assignments(
        self, key: str, type_: Optional["str"] = None, **kwargs: Any
    ) -> List[Optional[VariableAssignment]]:
        params: Dict[str, Any] = {}
        if type_ is not None:
            if isinstance(type_, PythonCoreBaseModel):
                params.update(type_.json_dict(by_alias=True))
            elif isinstance(type_, dict):
                params.update(type_)
            else:
                params["type"] = type_
        return await self.client.request(
            method="GET",
            url=f"/api/pm/nodes/{key}/variables-assignments",
            params=params,
            parse_json=True,
            type_=List[Optional[VariableAssignment]],
            **kwargs,
        )

    async def get_api_model_consumers_id_name(
        self, id_name: str, **kwargs: Any
    ) -> List[Optional[SemanticLayerConsumer]]:
        return await self.client.request(
            method="GET",
            url=f"/api/model-consumers/{id_name}",
            parse_json=True,
            type_=List[Optional[SemanticLayerConsumer]],
            **kwargs,
        )

    async def get_api_layers_knowledge_model_key_records_id_pql_query(
        self,
        knowledge_model_key: str,
        id: str,
        query_offset: Optional["int"] = None,
        query_limit: Optional["int"] = None,
        attributes_limit: Optional["int"] = None,
        **kwargs: Any,
    ) -> BusinessRecordMetadataPql:
        params: Dict[str, Any] = {}
        if query_offset is not None:
            if isinstance(query_offset, PythonCoreBaseModel):
                params.update(query_offset.json_dict(by_alias=True))
            elif isinstance(query_offset, dict):
                params.update(query_offset)
            else:
                params["queryOffset"] = query_offset
        if query_limit is not None:
            if isinstance(query_limit, PythonCoreBaseModel):
                params.update(query_limit.json_dict(by_alias=True))
            elif isinstance(query_limit, dict):
                params.update(query_limit)
            else:
                params["queryLimit"] = query_limit
        if attributes_limit is not None:
            if isinstance(attributes_limit, PythonCoreBaseModel):
                params.update(attributes_limit.json_dict(by_alias=True))
            elif isinstance(attributes_limit, dict):
                params.update(attributes_limit)
            else:
                params["attributesLimit"] = attributes_limit
        return await self.client.request(
            method="GET",
            url=f"/api/layers/{knowledge_model_key}/records/{id}/pql-query",
            params=params,
            parse_json=True,
            type_=BusinessRecordMetadataPql,
            **kwargs,
        )

    async def get_api_layers_knowledge_model_key_records_id_identifier_columns(
        self, knowledge_model_key: str, id: str, **kwargs: Any
    ) -> List[Optional[DataModelColumn]]:
        return await self.client.request(
            method="GET",
            url=f"/api/layers/{knowledge_model_key}/records/{id}/identifier/columns",
            parse_json=True,
            type_=List[Optional[DataModelColumn]],
            **kwargs,
        )

    async def get_api_layer_id_name(self, id_name: str, **kwargs: Any) -> FinalLayerTransport:
        return await self.client.request(
            method="GET", url=f"/api/layer/{id_name}", parse_json=True, type_=FinalLayerTransport, **kwargs
        )

    async def get_api_layer_final_base(self, id: Optional["str"] = None, **kwargs: Any) -> FinalLayerTransport:
        params: Dict[str, Any] = {}
        if id is not None:
            if isinstance(id, PythonCoreBaseModel):
                params.update(id.json_dict(by_alias=True))
            elif isinstance(id, dict):
                params.update(id)
            else:
                params["id"] = id
        return await self.client.request(
            method="GET",
            url=f"/api/layer/final-base",
            params=params,
            parse_json=True,
            type_=FinalLayerTransport,
            **kwargs,
        )

    async def get_api_layer_by_root_key_root_key(
        self, root_key: str, draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> List[Optional[LayerTransport]]:
        params: Dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="GET",
            url=f"/api/layer/by-root-key/{root_key}",
            params=params,
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def get_api_knowledge_model_layer_asset_id_variables_resolved(
        self, layer_asset_id: str, **kwargs: Any
    ) -> List[Optional[VariableMetadata]]:
        return await self.client.request(
            method="GET",
            url=f"/api/knowledge-model/{layer_asset_id}/variables/resolved",
            parse_json=True,
            type_=List[Optional[VariableMetadata]],
            **kwargs,
        )

    async def get_api_knowledge_model_layer_asset_id_records_record_id_identifier_validate_uniqueness(
        self, layer_asset_id: str, record_id: str, **kwargs: Any
    ) -> ValidationUniqueTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/identifier/validate-uniqueness",
            parse_json=True,
            type_=ValidationUniqueTransport,
            **kwargs,
        )

    async def get_api_export_data_queries_order_id_status(self, order_id: str, **kwargs: Any) -> JobStatus:
        return await self.client.request(
            method="GET", url=f"/api/export-data-queries/{order_id}/status", parse_json=True, type_=JobStatus, **kwargs
        )

    async def get_api_export_data_queries_order_id_result(self, order_id: str, **kwargs: Any) -> None:
        return await self.client.request(method="GET", url=f"/api/export-data-queries/{order_id}/result", **kwargs)

    async def get_api_documentation(self, **kwargs: Any) -> DocumentationTransport:
        return await self.client.request(
            method="GET", url=f"/api/documentation", parse_json=True, type_=DocumentationTransport, **kwargs
        )

    async def get_api_data_models(self, **kwargs: Any) -> List[Optional[ComputeNodeDescriptor]]:
        return await self.client.request(
            method="GET",
            url=f"/api/data-models",
            parse_json=True,
            type_=List[Optional[ComputeNodeDescriptor]],
            **kwargs,
        )

    async def get_api_data_models_data_model_id(self, data_model_id: str, **kwargs: Any) -> DataModelTransport:
        return await self.client.request(
            method="GET", url=f"/api/data-models/{data_model_id}", parse_json=True, type_=DataModelTransport, **kwargs
        )

    async def get_api_data_models_by_knowledge_model_id_knowledge_model_id(
        self, knowledge_model_id: str, **kwargs: Any
    ) -> DataModelTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/data-models/by-knowledge-model-id/{knowledge_model_id}",
            parse_json=True,
            type_=DataModelTransport,
            **kwargs,
        )

    async def get_api_data_models_by_knowledge_model_id_knowledge_model_id_load(
        self, knowledge_model_id: str, **kwargs: Any
    ) -> DataModelLoad:
        return await self.client.request(
            method="GET",
            url=f"/api/data-models/by-knowledge-model-id/{knowledge_model_id}/load",
            parse_json=True,
            type_=DataModelLoad,
            **kwargs,
        )

    async def delete_api_knowledge_model_layer_asset_id_transitions_transition_id(
        self, layer_asset_id: str, transition_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/transitions/{transition_id}", **kwargs
        )

    async def delete_api_knowledge_model_layer_asset_id_records_record_id_identifier(
        self, layer_asset_id: str, record_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE", url=f"/api/knowledge-model/{layer_asset_id}/records/{record_id}/identifier", **kwargs
        )

    async def get_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="GET", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def put_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="PUT", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def post_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="POST", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def delete_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="DELETE", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def options_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="OPTIONS", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def head_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="HEAD", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )

    async def patch_error(self, **kwargs: Any) -> Dict[str, Optional[Any]]:
        return await self.client.request(
            method="PATCH", url=f"/error", parse_json=True, type_=Dict[str, Optional[Any]], **kwargs
        )


class SemanticLayerClient(SemanticLayerClientBase):
    async def put_api_internal_layers_metadata_id_kpi_metadata_kpi_id_targets_target_id(
        self,
        metadata_id: str,
        kpi_id: str,
        target_id: str,
        request_body: TargetMetadata,
        draft: Optional["bool"] = None,
        **kwargs: Any,
    ) -> TargetMetadata:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="PUT",
            url=f"/api/internal/layers/{metadata_id}/kpi-metadata/{kpi_id}/targets/{target_id}",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=TargetMetadata,
            **kwargs,
        )

    async def delete_api_internal_layers_metadata_id_kpi_metadata_kpi_id_targets_target_id(
        self, metadata_id: str, kpi_id: str, target_id: str, draft: Optional["bool"] = None, **kwargs: Any
    ) -> None:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="DELETE",
            url=f"/api/internal/layers/{metadata_id}/kpi-metadata/{kpi_id}/targets/{target_id}",
            params=params,
            **kwargs,
        )

    async def post_api_internal_validation_for_process_type(
        self, request_body: ProcessTypeValidationRequest, **kwargs: Any
    ) -> ProcessTypeValidationResponse:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/validation/for-process-type",
            request_body=request_body,
            parse_json=True,
            type_=ProcessTypeValidationResponse,
            **kwargs,
        )

    async def post_api_internal_v2_clone(
        self, request_body: CloneRequestTransport, **kwargs: Any
    ) -> CloneResultTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/v2/clone",
            request_body=request_body,
            parse_json=True,
            type_=CloneResultTransport,
            **kwargs,
        )

    async def post_api_internal_teams_team_id_erase(
        self, team_id: str, **kwargs: Any
    ) -> List[Optional[EraserLogMessageTransport]]:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/teams/{team_id}/erase",
            parse_json=True,
            type_=List[Optional[EraserLogMessageTransport]],
            **kwargs,
        )

    async def post_api_internal_layers_metadata_id_kpi_metadata_kpi_id_targets(
        self, metadata_id: str, kpi_id: str, request_body: TargetMetadata, draft: Optional["bool"] = None, **kwargs: Any
    ) -> TargetMetadata:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{metadata_id}/kpi-metadata/{kpi_id}/targets",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=TargetMetadata,
            **kwargs,
        )

    async def post_api_internal_layers_metadata_id_kpi_metadata_kpi_id_prioritize(
        self, metadata_id: str, kpi_id: str, draft: Optional["bool"] = None, **kwargs: Any
    ) -> LayerTransport:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{metadata_id}/kpi-metadata/{kpi_id}/prioritize",
            params=params,
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def post_api_internal_layers_metadata_id_kpi_metadata_remove_prioritization(
        self, metadata_id: str, draft: Optional["bool"] = None, **kwargs: Any
    ) -> LayerTransport:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{metadata_id}/kpi-metadata/remove-prioritization",
            params=params,
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def post_api_internal_layers_id_get_by_options(
        self,
        id: str,
        request_body: FinalModelOptions,
        version: Optional["str"] = None,
        draft: Optional["bool"] = None,
        **kwargs: Any,
    ) -> LayerTransport:
        params: Dict[str, Any] = {}
        if version is not None:
            if isinstance(version, PythonCoreBaseModel):
                params.update(version.json_dict(by_alias=True))
            elif isinstance(version, dict):
                params.update(version)
            else:
                params["version"] = version
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{id}/get-by-options",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def post_api_internal_layers_id_name_query(
        self, id_name: str, request_body: LayerBasedQueryRequest, is_draft: Optional["bool"] = None, **kwargs: Any
    ) -> TableResponse:
        params: Dict[str, Any] = {}
        if is_draft is not None:
            if isinstance(is_draft, PythonCoreBaseModel):
                params.update(is_draft.json_dict(by_alias=True))
            elif isinstance(is_draft, dict):
                params.update(is_draft)
            else:
                params["isDraft"] = is_draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{id_name}/query",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=TableResponse,
            **kwargs,
        )

    async def post_api_internal_layers_id_name_query_batch(
        self, id_name: str, request_body: LayerBasedBatchQueryRequest, is_draft: Optional["bool"] = None, **kwargs: Any
    ) -> List[Optional[TableResponse]]:
        params: Dict[str, Any] = {}
        if is_draft is not None:
            if isinstance(is_draft, PythonCoreBaseModel):
                params.update(is_draft.json_dict(by_alias=True))
            elif isinstance(is_draft, dict):
                params.update(is_draft)
            else:
                params["isDraft"] = is_draft
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/{id_name}/query/batch",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[TableResponse]],
            **kwargs,
        )

    async def post_api_internal_layers_by_ids(
        self, request_body: List[Optional[str]], draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> List[Optional[LayerTransport]]:
        params: Dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/by-ids",
            params=params,
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def post_api_internal_layers_by_data_model_data_model_id(
        self, data_model_id: str, request_body: FinalModelOptions, **kwargs: Any
    ) -> List[Optional[LayerTransport]]:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/layers/by-data-model/{data_model_id}",
            request_body=request_body,
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def post_api_internal_compute_query_batch_by_knowledge_model_knowledge_model_id(
        self, knowledge_model_id: str, request_body: BatchQueryByKnowledgeModelIdTransport, **kwargs: Any
    ) -> DataCommandBatchListResult:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/compute-query/batch/by-knowledge-model/{knowledge_model_id}",
            request_body=request_body,
            parse_json=True,
            type_=DataCommandBatchListResult,
            **kwargs,
        )
    
    async def get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id(
        self, knowledge_model_id: str, export_id: str, draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> QueryExportStatusTransport:
        params: Dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="GET",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export/{export_id}",
            params=params,
            parse_json=True,
            type_=QueryExportStatusTransport,
            **kwargs,
        )

    async def get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id_result_chunk_id(
        self, knowledge_model_id: str, export_id: str, chunk_id: int, draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> BytesIO:
        params: Dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="GET",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export/{export_id}/result/{chunk_id}",
            params=params,
            parse_json=True,
            type_=BytesIO,
            **kwargs,
        )

    async def post_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export(
        self, knowledge_model_id: str, request_body: QueryExportRequestTransport, **kwargs: Any
    ) -> QueryExportStatusTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export",
            request_body=request_body,
            parse_json=True,
            type_=QueryExportStatusTransport,
            **kwargs,
        )
    
    async def get_api_internal_root_root_key_layers(
        self,
        root_key: str,
        draft_mode: Optional["bool"] = None,
        include_invalid_models: Optional["bool"] = None,
        **kwargs: Any,
    ) -> List[Optional[LayerTransport]]:
        params: Dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        if include_invalid_models is not None:
            if isinstance(include_invalid_models, PythonCoreBaseModel):
                params.update(include_invalid_models.json_dict(by_alias=True))
            elif isinstance(include_invalid_models, dict):
                params.update(include_invalid_models)
            else:
                params["includeInvalidModels"] = include_invalid_models
        return await self.client.request(
            method="GET",
            url=f"/api/internal/root/{root_key}/layers",
            params=params,
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def get_api_internal_query_environment_semantic_model_id(
        self, semantic_model_id: str, draft: Optional["bool"] = None, **kwargs: Any
    ) -> QueryEnvironment:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="GET",
            url=f"/api/internal/query/environment/{semantic_model_id}",
            params=params,
            parse_json=True,
            type_=QueryEnvironment,
            **kwargs,
        )

    async def get_api_internal_layers(self, **kwargs: Any) -> List[Optional[LayerTransport]]:
        return await self.client.request(
            method="GET", url=f"/api/internal/layers", parse_json=True, type_=List[Optional[LayerTransport]], **kwargs
        )

    async def get_api_internal_layers_knowledge_model_key_records_id_pql_query(
        self,
        knowledge_model_key: str,
        id: str,
        query_offset: Optional["int"] = None,
        query_limit: Optional["int"] = None,
        attributes_limit: Optional["int"] = None,
        **kwargs: Any,
    ) -> BusinessRecordMetadataPql:
        params: Dict[str, Any] = {}
        if query_offset is not None:
            if isinstance(query_offset, PythonCoreBaseModel):
                params.update(query_offset.json_dict(by_alias=True))
            elif isinstance(query_offset, dict):
                params.update(query_offset)
            else:
                params["queryOffset"] = query_offset
        if query_limit is not None:
            if isinstance(query_limit, PythonCoreBaseModel):
                params.update(query_limit.json_dict(by_alias=True))
            elif isinstance(query_limit, dict):
                params.update(query_limit)
            else:
                params["queryLimit"] = query_limit
        if attributes_limit is not None:
            if isinstance(attributes_limit, PythonCoreBaseModel):
                params.update(attributes_limit.json_dict(by_alias=True))
            elif isinstance(attributes_limit, dict):
                params.update(attributes_limit)
            else:
                params["attributesLimit"] = attributes_limit
        return await self.client.request(
            method="GET",
            url=f"/api/internal/layers/{knowledge_model_key}/records/{id}/pql-query",
            params=params,
            parse_json=True,
            type_=BusinessRecordMetadataPql,
            **kwargs,
        )

    async def get_api_internal_layers_id(
        self, id: str, version: Optional["str"] = None, draft: Optional["bool"] = None, **kwargs: Any
    ) -> LayerTransport:
        params: Dict[str, Any] = {}
        if version is not None:
            if isinstance(version, PythonCoreBaseModel):
                params.update(version.json_dict(by_alias=True))
            elif isinstance(version, dict):
                params.update(version)
            else:
                params["version"] = version
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return await self.client.request(
            method="GET",
            url=f"/api/internal/layers/{id}",
            params=params,
            parse_json=True,
            type_=LayerTransport,
            **kwargs,
        )

    async def get_api_internal_layers_without_permissions(self, **kwargs: Any) -> List[Optional[LayerTransport]]:
        return await self.client.request(
            method="GET",
            url=f"/api/internal/layers/without-permissions",
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def get_api_internal_layers_filtered_by_permissions(self, **kwargs: Any) -> List[Optional[LayerTransport]]:
        return await self.client.request(
            method="GET",
            url=f"/api/internal/layers/filtered-by-permissions",
            parse_json=True,
            type_=List[Optional[LayerTransport]],
            **kwargs,
        )

    async def get_api_internal_layers_data_model_id_identifier_columns(
        self, id: str, pql: Optional["str"] = None, **kwargs: Any
    ) -> List[Optional[DataModelColumn]]:
        params: Dict[str, Any] = {}
        if pql is not None:
            if isinstance(pql, PythonCoreBaseModel):
                params.update(pql.json_dict(by_alias=True))
            elif isinstance(pql, dict):
                params.update(pql)
            else:
                params["pql"] = pql
        return await self.client.request(
            method="GET",
            url=f"/api/internal/layers/data-model/{id}/identifier/columns",
            params=params,
            parse_json=True,
            type_=List[Optional[DataModelColumn]],
            **kwargs,
        )


class SemanticLayerExternalClient(SemanticLayerClientBase):
    def __init__(self, base_url: str, headers: dict[str, str], **kwargs: Any) -> None:
        self.client = ExternalAsyncClient(base_url=base_url, headers=headers, **kwargs)
        self.client.client.timeout = 320

    def post_api_knowledge_models_query(self, rootWithKey: str, request_body: KnowledgeModelQueryRequest, draft: Optional[bool] = None,**kwargs: Any) -> ProxyQueryResponseTransportV2:
        params: Dict[str, Any] = {}
        if draft is not None:
            if isinstance(draft, PythonCoreBaseModel):
                params.update(draft.json_dict(by_alias=True))
            elif isinstance(draft, dict):
                params.update(draft)
            else:
                params["draft"] = draft
        return self.client.request(
            method="POST",
            url=f"/api/knowledge-models/{rootWithKey}/query",
            request_body=request_body,
            params=params,
            parse_json=True,
            type_=ProxyQueryResponseTransportV2,
            **kwargs,
        )

    async def post_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export(
        self, knowledge_model_id: str, request_body: QueryExportRequestTransport, **kwargs: Any
    ) -> QueryExportStatusTransport:
        return await self.client.request(
            method="POST",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export",
            request_body=request_body,
            parse_json=True,
            type_=QueryExportStatusTransport,
            **kwargs,
        )

    async def get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id_result_chunk_id(
        self, knowledge_model_id: str, export_id: str, chunk_id: int, draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> BytesIO:
        params: dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="GET",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export/{export_id}/result/{chunk_id}",
            params=params,
            parse_json=True,
            type_=BytesIO,
            **kwargs,
        )

    async def get_api_internal_compute_query_by_knowledge_model_knowledge_model_id_export_export_id(
        self, knowledge_model_id: str, export_id: str, draft_mode: Optional["bool"] = None, **kwargs: Any
    ) -> QueryExportStatusTransport:
        params: dict[str, Any] = {}
        if draft_mode is not None:
            if isinstance(draft_mode, PythonCoreBaseModel):
                params.update(draft_mode.json_dict(by_alias=True))
            elif isinstance(draft_mode, dict):
                params.update(draft_mode)
            else:
                params["draftMode"] = draft_mode
        return await self.client.request(
            method="GET",
            url=f"/api/internal/compute-query/by-knowledge-model/{knowledge_model_id}/export/{export_id}",
            params=params,
            parse_json=True,
            type_=QueryExportStatusTransport,
            **kwargs,
        )


    async def post_api_knowledge_model_layer_asset_id_augmented_attributes_v2(
        self,
        layer_asset_id: str,
        request_body: AugmentedAttributeMetadataV2,
        parse_json: bool = True,
        raise_for_status: bool = True,
        **kwargs: Any,
    ) -> AugmentedAttributeMetadataV2:
        return await self.client.request(
            method="POST",
            url=f"/api/knowledge-model/{layer_asset_id}/augmented-attributes/v2",
            request_body=request_body,
            parse_json=parse_json,
            raise_for_status=raise_for_status,
            type_=AugmentedAttributeMetadataV2,
            **kwargs,
        )


    async def delete_api_knowledge_model_layer_asset_id_augmented_attributes_v2_attribute_id(
        self, layer_asset_id: str, attribute_id: str, **kwargs: Any
    ) -> None:
        return await self.client.request(
            method="DELETE",
            url=f"/api/knowledge-model/{layer_asset_id}/augmented-attributes/v2/{attribute_id}",
            **kwargs,
        )


    async def get_semantic_models_by_root_with_key(
        self, km_root_key: str, km_key: str, **kwargs: Any
    ) -> ContentNodeTransport:
        return await self.client.request(
            method="GET",
            url=f"/api/semantic-models/by-root-with-key/{km_root_key}.{km_key}",
            parse_json=True,
            type_=ContentNodeTransport,
            **kwargs,
        )
