"""Exceptions exposed by the reusable View reader."""


class CelonisViewReaderError(Exception):
    """Base exception for the component."""


class ContextResolutionError(CelonisViewReaderError):
    """Raised when Studio, Knowledge Model, or Data Model metadata cannot be resolved."""


class ViewFormatError(CelonisViewReaderError):
    """Raised when a published View does not have the expected table structure."""


class TableNotFoundError(ViewFormatError):
    """Raised when the requested table component is absent from the View."""


class PqlResolutionError(CelonisViewReaderError):
    """Raised when a PQL reference or variable cannot be resolved safely."""
