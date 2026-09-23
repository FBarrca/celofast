"""Celofast-specific exceptions.

Dictionary execution preserves PyCelonis and SaolaPy exceptions. The query
builder translates recognized query errors to QueryValidationError and retains
their native error chains; unrelated execution failures remain unchanged.
"""


class CeloFastError(Exception):
    """Base class for errors raised by CeloFast itself.

    Catch this class when an application wants to handle validation and
    resource-selection failures uniformly while still allowing native
    PyCelonis/SaolaPy execution exceptions to pass through unchanged.
    """


class ResourceNotFoundError(CeloFastError):
    """Raised when an exact-key Studio resource cannot be found.

    This includes Knowledge Models and Views selected through ``CeloFast.km``
    and ``CeloFast.view``; ``TableNotFoundError`` specializes it for View
    table selectors.
    """


class ResourceAmbiguityError(CeloFastError):
    """Raised when a resource selector matches more than one resource.

    The resolver uses this instead of guessing, allowing callers to correct an
    ambiguous Studio key or table display name explicitly.
    """


class ResourceResolutionError(CeloFastError):
    """Raised when a related Celonis resource cannot be resolved.

    Typical causes are a KM with no final Data Model ID or a Data Model that
    is not present in any accessible Data Pool.
    """


class ViewContentError(CeloFastError):
    """Raised when serialized Studio View content fails native validation.

    The error covers missing serialized content and YAML that cannot be parsed
    into PyCelonis's typed ``ViewContent`` model.  The original parse or
    validation exception is retained as the cause.
    """


class TableNotFoundError(ResourceNotFoundError):
    """Raised when a View table has no matching ID or exact display name."""


class AmbiguousTableError(ResourceAmbiguityError):
    """Raised when an exact View table display name is not unique.

    The message includes the matching component IDs and tab names so callers
    can retry with a stable component ID.
    """


class ComponentNotFoundError(ResourceNotFoundError):
    """Raised when a typed View component selector has no match."""


class AmbiguousComponentError(ResourceAmbiguityError):
    """Raised when a typed View component display name is not unique."""


class ComponentVariableError(CeloFastError, ValueError):
    """Raised when a View input is not bound to a declared KM variable."""


class QueryValidationError(CeloFastError, ValueError):
    """Raised when a query definition, binding, or execution option is invalid.

    It subclasses ``ValueError`` for compatibility with callers that already
    handle standard argument-validation failures.
    """


class AugmentationValidationError(CeloFastError, ValueError):
    """Raised when an augmentation-table operation has invalid local input.

    This covers malformed names, DataFrames, foreign-key declarations, and
    batch sizes. Native PyCelonis and server-side augmentation errors remain
    unchanged so callers retain their original types and error details.
    """


class UnresolvedVariableError(QueryValidationError):
    """Raised when executable PQL contains an unbound ``${name}`` placeholder.

    Placeholders inside line or block comments are intentionally ignored by
    the binder and therefore do not trigger this exception.
    """


class ObjectMappingError(CeloFastError, ValueError):
    """Raised when captured records cannot be generated as identified objects.

    Generation lists every record, key, type, or relationship that needs an
    explicit mapping or exclusion instead of weakening the object contract.
    """


class ObjectNotFoundError(ResourceNotFoundError):
    """Raised when ``get(key)`` finds no object with that business key."""


class ObjectIdentityError(CeloFastError):
    """Raised when retrieved rows have a null key or conflicting values for one key."""


class ObjectValueError(CeloFastError, ValueError):
    """Raised when a retrieved or filter value does not match its declared type."""
