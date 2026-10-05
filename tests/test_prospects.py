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


def test_google_maps_listing_completes_a_registry_prospect():
    prospect_identifier, _ = prospect_repository.upsert_prospect(build_registry_candidate())
    prospect_repository.record_website_check(prospect_identifier, "https://www.littoral.com/", "domain_guess", "medium", ["nom dans le nom de domaine"])
    prospect_repository.enrich_from_listing(prospect_identifier, ProspectCandidate(
        name="Boucherie Brume", source="google_maps", phone="0467000000", website_url="https://boucherie-brume.fr/", google_rating=4.8, google_review_count=120,
    ))
    enriched_prospect = prospect_repository.get_prospect(prospect_identifier)
    assert enriched_prospect["phone"] == "04 67 00 00 00"
    assert enriched_prospect["website_url"] == "https://boucherie-brume.fr/"
    assert enriched_prospect["website_confidence"] == "high"
    assert enriched_prospect["google_review_count"] == 120
    assert "google_maps" in enriched_prospect["sources"]
    assert prospect_repository.list_ids_without_phone(10) == []


def test_chain_cleanup_removes_franchises_only():
    prospect_repository.upsert_prospect(build_registry_candidate())
    prospect_repository.upsert_prospect(build_registry_candidate(name="SUBWAY SUBAUNES", legal_name="SUBAUNES", siret="11122233300011", latitude=43.70))
    assert prospect_repository.remove_chains() == ["SUBWAY SUBAUNES"]


def test_duplicates_are_detected_and_merged_with_their_history():
    first_identifier, _ = prospect_repository.upsert_prospect(build_registry_candidate())
    prospect_repository.add_activity(first_identifier, ActivityCreate(kind="call", outcome="callback", next_follow_up="2030-02-01"))
    second_identifier = prospect_repository._insert_prospect(ProspectCandidate(
        name="Boucherie Brume Castelnau", source="google_maps", latitude=43.6371, longitude=3.9101, phone="04 67 00 00 00",
        website_url="https://boucherie-brume.fr/", google_rating=4.6, google_review_count=80,
    ))
    third_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Pizzeria Napoli", source="openstreetmap", latitude=43.6372, longitude=3.9102))
    assert prospect_repository.merge_all_duplicates() == 1
    merged_prospect = prospect_repository.get_prospect_detail(first_identifier)
    assert prospect_repository.get_prospect(second_identifier) is None
    assert prospect_repository.get_prospect(third_identifier) is not None
    assert merged_prospect["website_url"] == "https://boucherie-brume.fr/"
    assert merged_prospect["google_review_count"] == 80
    assert merged_prospect["status"] == "callback"
    assert merged_prospect["sources"] == ["government_registry", "google_maps"]
    assert len(merged_prospect["activities"]) == 1


def test_manual_merge_keeps_the_oldest_prospect():
    first_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Atelier Dupont", source="openstreetmap"))
    second_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Dupont Menuiserie", source="google_maps", phone="0601020304"))
    merged_prospect = prospect_repository.merge_prospects([second_identifier, first_identifier])
    assert merged_prospect["id"] == first_identifier and merged_prospect["phone"] == "0601020304"


def test_list_can_be_sorted_by_any_column_in_both_directions():
    prospect_repository._insert_prospect(ProspectCandidate(name="Beta", source="manual", city="Lattes", employee_minimum=10))
    prospect_repository._insert_prospect(ProspectCandidate(name="Alpha", source="manual", city="Mauguio", employee_minimum=0))
    prospect_repository._insert_prospect(ProspectCandidate(name="Gamma", source="manual"))
    assert [row["name"] for row in prospect_repository.list_prospects({"sort": "name"})] == ["Alpha", "Beta", "Gamma"]
    assert [row["name"] for row in prospect_repository.list_prospects({"sort": "name", "sort_direction": "desc"})] == ["Gamma", "Beta", "Alpha"]
    assert [row["name"] for row in prospect_repository.list_prospects({"sort": "employees"})] == ["Beta", "Alpha", "Gamma"]
    assert [row["name"] for row in prospect_repository.list_prospects({"sort": "city", "sort_direction": "desc"})] == ["Alpha", "Beta", "Gamma"]


def test_establishments_of_one_company_become_one_prospect():
    first_identifier, _ = prospect_repository.upsert_prospect(build_registry_candidate(siret="91884780700024", name="MULTANI"))
    second_identifier, created = prospect_repository.upsert_prospect(build_registry_candidate(siret="91884780700032", name="MULTANI", latitude=43.60, longitude=3.86))
    assert not created and first_identifier == second_identifier


def test_user_defined_chain_removes_every_matching_prospect():
    prospect_repository.upsert_prospect(build_registry_candidate())
    prospect_repository.upsert_prospect(build_registry_candidate(name="LOLITA BOUTIQUE LATTES", legal_name="SARL LOLA", siret="22233344400011", latitude=43.70))
    assert prospect_repository.remove_chains([]) == []
    assert prospect_repository.remove_chains(["lolita"]) == ["LOLITA BOUTIQUE LATTES"]


def test_list_can_be_filtered_around_a_place():
    prospect_repository._insert_prospect(ProspectCandidate(name="Centre", source="manual", latitude=43.6108, longitude=3.8767))
    prospect_repository._insert_prospect(ProspectCandidate(name="Quatre km", source="manual", latitude=43.6468, longitude=3.8767))
    prospect_repository._insert_prospect(ProspectCandidate(name="Vingt km", source="manual", latitude=43.7908, longitude=3.8767))
    prospect_repository._insert_prospect(ProspectCandidate(name="Sans coordonnées", source="manual", city="Montpellier"))
    prospect_repository._insert_prospect(ProspectCandidate(name="Ailleurs sans coordonnées", source="manual", city="Nîmes"))
    area = {"center_latitude": 43.6108, "center_longitude": 3.8767, "radius_km": 5, "area_city": "Montpellier"}
    rows = prospect_repository.list_prospects({**area, "sort": "distance"})
    assert [(row["name"], row["distance_km"]) for row in rows] == [("Centre", 0.0), ("Quatre km", 4.0), ("Sans coordonnées", None)]
    assert [row["name"] for row in prospect_repository.list_prospects({**area, "sort": "distance", "sort_direction": "desc"})][:2] == ["Quatre km", "Centre"]


def test_multiple_choice_filters_combine_values_with_or_and_filters_with_and():
    prospect_repository._insert_prospect(ProspectCandidate(name="Chez Paul", source="manual", sector_key="restaurant", city="Lattes", phone="0467000001"))
    prospect_repository._insert_prospect(ProspectCandidate(name="Rose et Lys", source="manual", sector_key="florist", city="lattes"))
    prospect_repository._insert_prospect(ProspectCandidate(name="Taxi Bleu", source="manual", sector_key="taxi", city="Mauguio", phone="0467000002"))
    prospect_repository._insert_prospect(ProspectCandidate(name="Garage Sud", source="manual", sector_key="garage", city="Lattes", phone="0467000003"))
    prospect_repository._insert_prospect(ProspectCandidate(name="Sans secteur", source="manual", city="Lattes"))
    def listed_names(filters):
        return sorted(row["name"] for row in prospect_repository.list_prospects(filters))
    assert listed_names({"sector_key": ["restaurant", "florist", "taxi"]}) == ["Chez Paul", "Rose et Lys", "Taxi Bleu"]
    assert listed_names({"sector_key": "restaurant,florist,taxi", "city": ["LATTES"]}) == ["Chez Paul", "Rose et Lys"]
    assert listed_names({"sector_key": ["restaurant", "florist", "taxi"], "phone": "with"}) == ["Chez Paul", "Taxi Bleu"]
    assert listed_names({"sector_key": ["unclassified"]}) == ["Sans secteur"]
    prospect_repository._insert_prospect(ProspectCandidate(name="Site Mauguio", source="manual", city="Mauguio", website_url="https://site-mauguio.fr"))
    assert listed_names({"opportunity_level": ["unscanned", "unknown_website"], "city": ["Mauguio"]}) == ["Site Mauguio", "Taxi Bleu"]
    facets = prospect_repository.facets()
    assert facets["sector_key"]["restaurant"] == 1 and facets["sector_key"]["unclassified"] == 2
    assert facets["city"][0] == {"city": "Lattes", "total": 4} and facets["opportunity_level"]["unscanned"] == 1


def test_bulk_update_and_delete_apply_to_the_selection_only():
    first_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Un", source="manual"))
    second_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Deux", source="manual"))
    third_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Trois", source="manual"))
    assert prospect_repository.update_prospects([first_identifier, second_identifier, 999], {"status": "to_call"}) == 2
    assert prospect_repository.get_prospect(third_identifier)["status"] == "new"
    assert prospect_repository.delete_prospects([first_identifier, 999]) == 1
    assert [row["name"] for row in prospect_repository.list_prospects({"status": ["to_call"]})] == ["Deux"]
