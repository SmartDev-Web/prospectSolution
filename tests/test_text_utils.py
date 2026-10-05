from app.text_utils import (
    company_name_similarity,
    extract_domain,
    find_email_addresses,
    find_phone_numbers,
    format_place_name,
    normalize_company_name,
    normalize_phone_number,
)


def test_normalize_phone_number_handles_international_formats():
    assert normalize_phone_number("+33 (0)4 67 02 96 96") == "04 67 02 96 96"
    assert normalize_phone_number("+33 4 67 02 96 96") == "04 67 02 96 96"
    assert normalize_phone_number("0033467029696") == "04 67 02 96 96"
    assert normalize_phone_number("04.67.41.30.68") == "04 67 41 30 68"


def test_normalize_company_name_drops_legal_forms_and_accents():
    assert normalize_company_name("SARL Boucherie Brûme") == "boucherie brume"
    assert normalize_company_name("Le Pascalou") == "pascalou"


def test_company_name_similarity_recognises_variants():
    assert company_name_similarity("EURL BOUCHERIE BRUME", "Boucherie Brume") == 1.0
    assert company_name_similarity("Pizzeria Le Pascalou", "Le Pascalou") >= 0.9
    assert company_name_similarity("Le Comptoir", "Boulangerie Martin") < 0.5


def test_format_place_name_keeps_french_particles_lowercase():
    assert format_place_name("CASTELNAU-LE-LEZ") == "Castelnau-le-Lez"
    assert format_place_name("SAINT-JEAN-DE-VEDAS") == "Saint-Jean-de-Vedas"
    assert format_place_name("LE CRES") == "Le Cres"
    assert format_place_name("MONTPELLIER") == "Montpellier"


def test_extract_domain_removes_www_and_scheme():
    assert extract_domain("https://www.omicron-hardtech.com/contact") == "omicron-hardtech.com"
    assert extract_domain("sfei.fr") == "sfei.fr"
    assert extract_domain(None) is None


def test_contact_extraction_ignores_image_names():
    text = "Appelez le 04 67 41 30 68 ou écrivez à contact@lepascalou.fr. logo@2x.png"
    assert find_phone_numbers(text) == ["04 67 41 30 68"]
    assert find_email_addresses(text) == ["contact@lepascalou.fr"]
