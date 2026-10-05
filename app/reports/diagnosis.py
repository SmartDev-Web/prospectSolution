"""Final diagnosis of a scan, combining the analyzer's findings with the corrections made by the user."""
from typing import Any

from app.reports.rules import build_rule_based_report
from app.scanner.catalog import CATEGORY_LABELS, compute_opportunity_level, compute_score


def build_custom_finding(position: int, custom_finding: dict[str, Any]) -> dict[str, Any]:
    """Turn a point written by the user into a finding shaped like the analyzer's."""
    return {
        "code": f"custom_{position}",
        "category": custom_finding["category"],
        "category_label": CATEGORY_LABELS[custom_finding["category"]],
        "severity": custom_finding["severity"],
        "title": custom_finding["title"],
        "impact": custom_finding.get("impact") or "",
        "recommendation": custom_finding.get("recommendation") or "",
        "call_hook": "",
        "evidence": {},
        "custom": True,
    }


def apply_diagnosis_overrides(raw_findings: list[dict[str, Any]], overrides: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Remove the findings the user dismissed and add the points the user wrote."""
    dismissed_codes = set((overrides or {}).get("dismissed_codes") or [])
    kept_findings = [finding for finding in raw_findings if finding["code"] not in dismissed_codes]
    custom_findings = [build_custom_finding(position, custom_finding) for position, custom_finding in enumerate((overrides or {}).get("custom_findings") or [])]
    return kept_findings + custom_findings


def has_overrides(overrides: dict[str, Any] | None) -> bool:
    """Tell whether the user changed anything in the diagnosis."""
    return bool(overrides and (overrides.get("dismissed_codes") or overrides.get("custom_findings") or overrides.get("summary")))


def finalize_diagnosis(
    prospect: dict[str, Any],
    raw_findings: list[dict[str, Any]],
    strengths: list[dict[str, str]],
    metrics: dict[str, Any],
    reachable: bool,
    settings: dict[str, Any],
) -> tuple[int | None, str, dict[str, Any]]:
    """Compute the score, the opportunity level and the sales report from the corrected findings."""
    overrides = prospect.get("diagnosis_overrides") or {}
    effective_findings = apply_diagnosis_overrides(raw_findings, overrides)
    unmeasured_categories = metrics.get("unmeasured_categories")
    unreachable_confirmed = not reachable and "site_unreachable" not in set(overrides.get("dismissed_codes") or [])
    if not prospect.get("website_url"):
        score = None
    elif unreachable_confirmed:
        score = 0
    else:
        score = compute_score(effective_findings, unmeasured_categories)
    opportunity_level = compute_opportunity_level(score, has_website=bool(prospect.get("website_url")), reachable=not unreachable_confirmed)
    report = build_rule_based_report(prospect, effective_findings, strengths, score, opportunity_level, settings, unmeasured_categories)
    dismissed_codes = set(overrides.get("dismissed_codes") or [])
    report["dismissed_findings"] = [finding for finding in raw_findings if finding["code"] in dismissed_codes]
    report["custom_findings"] = overrides.get("custom_findings") or []
    report["manually_edited"] = has_overrides(overrides)
    if overrides.get("summary"):
        report["summary"] = overrides["summary"]
    return score, opportunity_level, report
