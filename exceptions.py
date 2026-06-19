"""
ivc/exceptions.py
=================
Domain-specific exception hierarchy for the IVC pipeline.

Catch IVCError to handle any IVC-specific failure generically.
Sub-class for targeted recovery logic.
"""

from __future__ import annotations


class IVCError(Exception):
    """Base class for all IVC pipeline errors."""


class SimulationError(IVCError):
    """Raised when the dark-store simulator fails to generate valid data."""


class ValidationError(IVCError):
    """Raised when a detection module receives malformed input."""


class ConfigurationError(IVCError):
    """Raised when required configuration values are missing or invalid."""


class InsufficientDataError(IVCError):
    """Raised when a statistical detector has too few samples to compute baselines."""
    def __init__(self, category: str, n_samples: int, minimum: int = 5) -> None:
        super().__init__(
            f"Category '{category}' has only {n_samples} samples "
            f"(minimum required: {minimum}). "
            "Falling back to global baseline — results may be less accurate."
        )
        self.category  = category
        self.n_samples = n_samples
        self.minimum   = minimum
