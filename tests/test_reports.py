from app.reports.rules import build_missing_website_findings, build_rule_based_report
from app.settings_service import DEFAULT_SETTINGS


def test_report_for_business_without_website():
    prospect = {"name": "Boucherie Brume", "sector_key": "butcher", "city": "CASTELNAU-LE-LEZ", "category_label": "Boucheries et charcuteries", "social_url": "https://www.facebook.com/brume"}
    findings = build_missing_website_findings(prospect)
    report = build_rule_based_report(prospect, findings, None, "no_website", {**DEFAULT_SETTINGS, "freelancer_first_name": "Alex"})
    assert [finding["code"] for finding in findings] == ["no_website", "social_only"]
    assert "Castelnau-le-Lez" in findings[0]["impact"]
    assert report["call_script"][0]["lines"][0].startswith("Bonjour, Alex")
    assert "click & collect" in " ".join(report["improvements"]).lower()
    assert report["email"]["subject"].endswith("Boucherie Brume")
