"""Category -> department / SLA table. This is configuration, not mock data.
Only the 24h solid-waste SLA is given in the PRD; the others are ASSUMPTIONS to
confirm against GCC / CMWSSB citizen charters before presenting."""

CATEGORIES = {
    "solid_waste": {"label": "Garbage / solid waste", "department": "GCC - Solid Waste Management", "sla_hours": 24, "body": "GCC"},
    "roads": {"label": "Potholes / roads", "department": "GCC - Roads (Bus Route Roads)", "sla_hours": 72, "body": "GCC"},
    "storm_water_drain": {"label": "Storm water drain / flooding", "department": "GCC - Storm Water Drains", "sla_hours": 48, "body": "GCC"},
    "streetlight": {"label": "Streetlight", "department": "GCC - Electrical", "sla_hours": 48, "body": "GCC"},
    "water_supply": {"label": "Drinking water supply", "department": "CMWSSB - Water Supply", "sla_hours": 24, "body": "CMWSSB"},
    "sewerage": {"label": "Sewage / sewer overflow", "department": "CMWSSB - Sewerage", "sla_hours": 48, "body": "CMWSSB"},
}

ORANGE_FRACTION = 0.75  # flag orange when 75% of the SLA window has elapsed
