"""
Legacy Compatibility Bridge for Data Models
Re-exports all Pydantic V2 schemas from the centralized core/models.py
"""

from core.models import (
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
    DiscoveryDossier,
    LegacyDomainCategory,
    TargetSystemDetection,
    LegacyERPPainPointItem,
    LegacyERPPainPoints,
    NoLegacyERPPainPointsFoundError,
    PainPoint,
    DiscoveryBrief,
    PressReleaseItem,
    ScrapeResult,
)

__all__ = [
    "TechStackIndicators",
    "ExecutivePainPoints",
    "DiscoveryQuestions",
    "DiscoveryDossier",
    "LegacyDomainCategory",
    "TargetSystemDetection",
    "LegacyERPPainPointItem",
    "LegacyERPPainPoints",
    "NoLegacyERPPainPointsFoundError",
    "PainPoint",
    "DiscoveryBrief",
    "PressReleaseItem",
    "ScrapeResult",
]
