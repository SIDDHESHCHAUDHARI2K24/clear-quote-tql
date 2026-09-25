"""Static major-metro catalog merged into the provider metro list (CQ-028
plan.md #17). The seeded `provider_listings` only cover the persona
markets, so a buy-box picker built from them alone would miss common
metros (the spec's AC6 picks "Tampa and Orlando"; the seed has no Orlando
listing). Keys are 2-letter state codes.
"""

STATIC_METROS: dict[str, tuple[str, ...]] = {
    "AZ": ("Phoenix", "Scottsdale", "Tucson"),
    "CO": ("Colorado Springs", "Denver"),
    "FL": ("Jacksonville", "Miami", "Orlando", "Tampa"),
    "GA": ("Atlanta", "Savannah"),
    "IN": ("Fort Wayne", "Indianapolis"),
    "NC": ("Asheville", "Charlotte", "Raleigh"),
    "OH": ("Cincinnati", "Cleveland", "Columbus"),
    "SC": ("Charleston", "Greenville"),
    "TN": ("Knoxville", "Memphis", "Nashville"),
    "TX": ("Austin", "Dallas", "Houston", "San Antonio"),
}
