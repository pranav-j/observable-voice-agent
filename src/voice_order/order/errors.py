"""Domain errors. The tools layer turns these into structured error results for the LLM."""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNKNOWN_ITEM = "UNKNOWN_ITEM"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    SIZE_REQUIRED = "SIZE_REQUIRED"
    INVALID_SIZE = "INVALID_SIZE"
    INVALID_MODIFIER = "INVALID_MODIFIER"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    UNKNOWN_LINE = "UNKNOWN_LINE"
    INVALID_NAME = "INVALID_NAME"
    INVALID_PHONE = "INVALID_PHONE"
    READBACK_REQUIRED = "READBACK_REQUIRED"
    ORDER_CLOSED = "ORDER_CLOSED"


class OrderError(Exception):
    def __init__(self, code: ErrorCode, message: str, alternatives: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.alternatives = alternatives  # item ids the agent can offer instead
