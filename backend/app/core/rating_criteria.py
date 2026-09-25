"""The criteria a restaurant is evaluated on.

Base-code data and not a table, for the same reason as the country catalogue:
a row nobody may edit adds a migration and a seed without adding a capability,
and a criterion that appears or disappears invalidates the averages already
computed. Changing this list is editing it and deploying.

The four are the ones the general statement names.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RatingCriterion:
    slug: str
    name: str


RATING_CRITERIA: tuple[RatingCriterion, ...] = (
    RatingCriterion("comida", "Comida"),
    RatingCriterion("servicio", "Servicio"),
    RatingCriterion("ambiente", "Ambiente"),
    RatingCriterion("precio-calidad", "Relación precio/calidad"),
)

RATING_CRITERION_SLUGS: tuple[str, ...] = tuple(criterion.slug for criterion in RATING_CRITERIA)
