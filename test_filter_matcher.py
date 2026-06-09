#!/usr/bin/env python3
"""Test FilterMatcher logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

from db.models import Propiedad
from notifications.filter_matcher import FilterMatcher


def test_filter_matching():
    """Test property matching against filters."""
    print("\n" + "="*80)
    print("🧪 TESTING FILTER MATCHER")
    print("="*80 + "\n")

    # Create test properties
    prop1 = Propiedad(
        id=1,
        hash_unico="hash1",
        url_original="http://example.com/1",
        titulo="Piso en Centro - 3 hab",
        precio=150000,
        superficie_m2=85,
        habitaciones=3,
        banos=2,
        barrio="Centro",
        direccion="Calle Principal, 123",
        tipo_propiedad="Piso",
        estado="Buen estado",
        amenidades=["Ascensor", "Garaje"],
        fuente_id=1
    )

    prop2 = Propiedad(
        id=2,
        hash_unico="hash2",
        url_original="http://example.com/2",
        titulo="Casa en Crevillet - Nueva",
        precio=250000,
        superficie_m2=150,
        habitaciones=4,
        banos=3,
        barrio="Crevillet",
        direccion="Avenida del Ejercito, 456",
        tipo_propiedad="Casa",
        estado="Nueva",
        amenidades=["Ascensor", "Piscina", "Terraza"],
        fuente_id=1
    )

    prop3 = Propiedad(
        id=3,
        hash_unico="hash3",
        url_original="http://example.com/3",
        titulo="Apartamento en Zona Norte - Barato",
        precio=80000,
        superficie_m2=45,
        habitaciones=1,
        banos=1,
        barrio="Zona Norte",
        direccion="Calle Secundaria, 789",
        tipo_propiedad="Apartamento",
        estado="Para reformar",
        amenidades=[],
        fuente_id=1
    )

    # Test cases
    test_cases = [
        {
            "name": "Filter: Precio máx 200k",
            "criterios": {"precio_max": 200000},
            "expected_matches": [prop1, prop3],
        },
        {
            "name": "Filter: Zona Crevillet",
            "criterios": {"barrio": "Crevillet"},
            "expected_matches": [prop2],
        },
        {
            "name": "Filter: 3+ habitaciones y precio < 300k",
            "criterios": {"habitaciones": 3, "precio_max": 300000},
            "expected_matches": [prop1, prop2],
        },
        {
            "name": "Filter: Ascensor + Precio máx 200k",
            "criterios": {"amenidades": "Ascensor", "precio_max": 200000},
            "expected_matches": [prop1],
        },
        {
            "name": "Filter: Estado = Nueva",
            "criterios": {"estado": "Nueva"},
            "expected_matches": [prop2],
        },
        {
            "name": "Filter: 100+ m² y precio < 300k",
            "criterios": {"m2_min": 100, "precio_max": 300000},
            "expected_matches": [prop2],
        },
    ]

    # Run tests
    all_properties = [prop1, prop2, prop3]
    passed = 0
    failed = 0

    for test in test_cases:
        name = test["name"]
        criterios = test["criterios"]
        expected = test["expected_matches"]

        # Create a mock FiltroAlerta-like object
        class MockFiltro:
            def __init__(self, crit):
                import json
                self.criterios_json = json.dumps(crit)

        filtro = MockFiltro(criterios)

        # Get matches
        matches = FilterMatcher.get_matching_properties(all_properties, filtro)

        # Check results
        match_ids = set(p.id for p in matches)
        expected_ids = set(p.id for p in expected)

        if match_ids == expected_ids:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1

        print(f"{status} | {name}")
        print(f"     Criterios: {FilterMatcher.format_criteria(criterios)}")
        print(f"     Encontradas: {len(matches)}/3 - IDs: {match_ids}")
        if match_ids != expected_ids:
            print(f"     Esperadas: {expected_ids}")
        print()

    # Summary
    print("="*80)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*80 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = test_filter_matching()
    sys.exit(0 if success else 1)
