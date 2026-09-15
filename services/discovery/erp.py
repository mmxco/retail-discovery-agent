"""Legacy ERP extractor service."""
from legacy_erp_extractor import (
    LegacyDomainCategory,
    TargetSystemDetection,
    LegacyERPPainPointItem,
    LegacyERPPainPoints,
    NoLegacyERPPainPointsFoundError,
    LEGACY_ERP_SYSTEM_INSTRUCTION,
    extract_legacy_erp_pain_points,
)

__all__ = [
    "LegacyDomainCategory",
    "TargetSystemDetection",
    "LegacyERPPainPointItem",
    "LegacyERPPainPoints",
    "NoLegacyERPPainPointsFoundError",
    "LEGACY_ERP_SYSTEM_INSTRUCTION",
    "extract_legacy_erp_pain_points",
]
