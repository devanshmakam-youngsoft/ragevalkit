"""Shapes that services and data access hand to one another (a run's selection, a run's plan, grades, documents), not part of the HTTP API."""

from ragevalkit.schemas.internal.run_selection import RunSelection, cases_to_dataframe

__all__ = ["RunSelection", "cases_to_dataframe"]
