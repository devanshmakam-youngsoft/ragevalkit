"""The defaults the recommendation uses when serve() does not override them."""


DEFAULT_ANSWER_WEIGHT = 0.6


DEFAULT_MATERIAL_WEIGHT = 0.4


DEFAULT_TOLERANCE = 0.25


# A version is only recommended when its overall score (0-10) reaches this: a version that mostly gets answers
# wrong is "the best so far", not something to ship.
DEFAULT_MIN_QUALITY = 5.0


# A comparison must rest on at least this share of a typical (median) version's test cases.
MIN_SHARED_SHARE = 0.5
