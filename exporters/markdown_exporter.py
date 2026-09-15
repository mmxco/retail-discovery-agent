"""
Markdown Executive Briefing Exporter
Renders a DiscoveryDossier into a clean, styled Markdown executive brief.
"""

from core.models import DiscoveryDossier

__all__ = ["export_dossier_to_markdown"]


def export_dossier_to_markdown(dossier: DiscoveryDossier) -> str:
    """Generates a styled Markdown executive briefing representation of the dossier."""
    corp_str = f" | **Corporate Website:** {dossier.corporate_domain}" if dossier.corporate_domain else ""
    lines = [
        f"# Executive Discovery Brief for {dossier.account_name}",
        f"**Target Account:** {dossier.account_name} | **Retail Domain:** {dossier.domain}{corp_str} | **Generated:** {dossier.generated_at[:10]}",
        f"**Retail Segment:** {dossier.retail_segment} | **Scale:** {dossier.estimated_scale}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        dossier.executive_summary,
        "",
        "---",
        "",
        "## 2. Technology Stack Footprint",
        f"- **E-Commerce Platform:** {dossier.tech_stack.ecommerce_platform or 'Undetected / Custom Headless'}",
        f"- **Point of Sale (POS):** {dossier.tech_stack.point_of_sale or 'Legacy In-Store Architecture'}",
        f"- **Core ERP / Merchandising:** {dossier.tech_stack.erp_core or 'Tier-1 Legacy Suite'}",
        f"- **Order Management (DOM/OMS):** {dossier.tech_stack.order_management or 'Distributed / Monolithic'}",
        f"- **Warehouse / Supply Chain:** {dossier.tech_stack.warehouse_supply_chain or 'Legacy WMS'}",
    ]

    if dossier.tech_stack.analytics_and_marketing:
        lines.append(f"- **Analytics & Marketing:** {', '.join(dossier.tech_stack.analytics_and_marketing)}")
    if dossier.tech_stack.detected_technologies:
        lines.append(f"- **Detected Footprints:** {', '.join(dossier.tech_stack.detected_technologies)}")
    if dossier.tech_stack.architecture_signals:
        lines.append(f"- **Architecture Signals:** {'; '.join(dossier.tech_stack.architecture_signals)}")

    lines.extend(["", "---", "", "## 3. Executive Pain Points (The Value Triangle)"])
    for i, p in enumerate(dossier.pain_points, start=1):
        lines.extend([
            f"### {i}. {p.category}",
            f"- **Technical Gap:** {p.technical_gap}",
            f"- **Operational Friction:** {p.operational_friction}",
            f"- **Financial Impact:** {p.financial_impact}",
            f"- **Affected Stakeholders:** {', '.join(p.affected_executives)}",
            "",
        ])

    lines.extend(["---", "", "## 4. Persona-Specific Discovery Questions"])
    for i, q in enumerate(dossier.discovery_questions, start=1):
        lines.extend([
            f"### {i}. {q.target_persona} — *{q.theme}*",
            f"> **Question:** \"{q.question}\"",
            f"- **What to Listen For:** {q.what_to_listen_for}",
            f"- **Value Wedge:** {q.value_wedge}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 5. Recommended Pre-Sales Discovery Strategy",
        dossier.recommended_discovery_strategy,
        "",
    ])

    return "\n".join(lines)
