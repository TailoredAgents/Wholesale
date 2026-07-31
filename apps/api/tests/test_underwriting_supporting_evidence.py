from app.services.underwriting_supporting_evidence import (
    collect_supporting_market_evidence,
)


def test_supporting_evidence_is_normalized_and_excluded_from_valuation() -> None:
    class Provider:
        def get_sale_listings(self, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "id": "subject",
                    "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
                    "status": "Active",
                    "price": 299000,
                },
                {
                    "id": "listing-1",
                    "formattedAddress": "125 Peachtree St, Atlanta, GA 30303",
                    "status": "Active",
                    "listingType": "Standard",
                    "propertyType": "Single Family",
                    "price": 325000,
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "squareFootage": 1750,
                    "daysOnMarket": 18,
                },
            ]

        def get_market_statistics(self, **_: object) -> dict[str, object]:
            return {
                "zipCode": "30303",
                "saleData": {
                    "lastUpdatedDate": "2026-07-30T00:00:00Z",
                    "medianPrice": 310000,
                    "averagePrice": 335000,
                    "medianPricePerSquareFoot": 185.5,
                    "averageDaysOnMarket": 27,
                    "medianDaysOnMarket": 21,
                    "totalListings": 48,
                    "newListings": 9,
                    "history": [
                        {"date": "2025-07-01", "medianPrice": 295000},
                    ],
                },
            }

    evidence = collect_supporting_market_evidence(
        Provider(),
        address="123 Peachtree St, Atlanta, GA 30303",
        postal_code="30303",
        subject_facts={
            "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1800,
        },
        local_property_type="single_family",
    )

    assert evidence["status"] == "completed"
    assert evidence["valuation_use"] == "excluded_from_arv_and_offer_math"
    assert len(evidence["sale_listings"]) == 1
    assert evidence["sale_listings"][0]["asking_price_cents"] == 32500000
    assert evidence["market_context"]["median_list_price_cents"] == 31000000
    assert evidence["market_context"]["median_price_per_square_foot_cents"] == 18550
    assert evidence["market_context"]["median_list_price_change_percentage"] == 5.1
