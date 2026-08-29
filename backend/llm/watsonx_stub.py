"""IBM Watsonx provider stub — T2-9.

This module defines the provider interface that a future IBM Watsonx
integration would implement.  Per architecture Part A §9:

    "IBM Watsonx stub — provider interface exists but is NOT wired;
     future use only"

ALL public methods raise :class:`NotImplementedError`.

IMPORTANT:
- This stub must NOT be wired into any call chain.
- Do not import and call this from groq_provider.py or llm_service.py.
- It exists only so the interface is defined for a future sprint.
"""
from __future__ import annotations


class WatsonxProvider:
    """IBM Watsonx LLM provider stub.

    NOT wired — raises :class:`NotImplementedError` on every method.
    """

    def generate_complaint_description(self, **kwargs) -> object:  # type: ignore[return]
        """NOT IMPLEMENTED — future IBM Watsonx integration."""
        raise NotImplementedError(
            "WatsonxProvider is a stub and is not wired. "
            "Use GroqProvider or fallback_provider instead."
        )

    def generate_rti_draft(self, **kwargs) -> object:  # type: ignore[return]
        """NOT IMPLEMENTED — future IBM Watsonx integration."""
        raise NotImplementedError(
            "WatsonxProvider is a stub and is not wired. "
            "Use GroqProvider or fallback_provider instead."
        )

    def classify_category(self, **kwargs) -> object:  # type: ignore[return]
        """NOT IMPLEMENTED — future IBM Watsonx integration."""
        raise NotImplementedError(
            "WatsonxProvider is a stub and is not wired. "
            "Use GroqProvider or fallback_provider instead."
        )
