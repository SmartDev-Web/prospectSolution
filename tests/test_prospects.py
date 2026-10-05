from app.models import ActivityCreate, ProspectCandidate
from app.prospects import prospect_repository


def build_registry_candidate(**overrides) -> ProspectCandidate:
    values = dict(
        name="BOUCHERIE BRUME",
        source="government_registry",
        legal_name="EURL BOUCHERIE BRUME",
        siret="12345678900011",
        naf_code="47.22Z",
        sector_key="butcher",
        postal_code="34170",
        city="CASTELNAU-LE-LEZ",
        latitude=43.6370,
        longitude=3.9100,
    )
    values.update(overrides)
    return ProspectCandidate(**values)


def test_same_business_from_two_sources_is_merged():
    registry_identifier, registry_created = prospect_repository.upsert_prospect(build_registry_candidate())
    osm_identifier, osm_created = prospect_repository.upsert_prospect(ProspectCandidate(
        name="Boucherie Brume",
        source="openstreetmap",
        latitude=43.6372,
        longitude=3.9102,
        phone="+33 4 67 00 00 00",
        website_url="https://boucherie-brume.fr",
        website_origin="openstreetmap",
    ))
    merged_prospect = prospect_repository.get_prospect(registry_identifier)
    assert registry_created and not osm_created
    assert osm_identifier == registry_identifier
    assert merged_prospect["website_domain"] == "boucherie-brume.fr"
    assert merged_prospect["phone"] == "04 67 00 00 00"
    assert merged_prospect["siret"] == "12345678900011"
    assert merged_prospect["sources"] == ["government_registry", "openstreetmap"]


def test_different_businesses_at_the_same_place_stay_separate():
    first_identifier, _ = prospect_repository.upsert_prospect(build_registry_candidate())
    second_identifier, created = prospect_repository.upsert_prospect(build_registry_candidate(name="Pizzeria Napoli", legal_name="SAS NAPOLI", siret="98765432100011"))
    assert created
    assert first_identifier != second_identifier


def test_logging_a_call_moves_the_pipeline_forward():
    prospect_identifier, _ = prospect_repository.upsert_prospect(build_registry_candidate())
    updated_prospect = prospect_repository.add_activity(prospect_identifier, ActivityCreate(kind="call", outcome="no_answer", next_follow_up="2030-01-02"))
    assert updated_prospect["status"] == "called_no_answer"
    assert updated_prospect["next_follow_up"] == "2030-01-02"
    assert [row["id"] for row in prospect_repository.list_due_follow_ups("2030-01-02")] == [prospect_identifier]


def test_csv_export_contains_prospects():
    prospect_repository.upsert_prospect(build_registry_candidate())
    csv_content = prospect_repository.export_csv({})
    assert "BOUCHERIE BRUME" in csv_content
    assert csv_content.splitlines()[0].lstrip("﻿").startswith("id;name;")
