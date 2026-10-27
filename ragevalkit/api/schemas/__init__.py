"""The shapes of what the API accepts."""
from ragevalkit.api.schemas.auth import LoginBody
from ragevalkit.api.schemas.generation import Approval, ItemEdit, TurnText
from ragevalkit.api.schemas.groups import GroupName
from ragevalkit.api.schemas.runs import SelectionBody
from ragevalkit.api.schemas.test_cases import (
    BulkStatusUpdate,
    CreateTestCase,
    TestCaseGroups,
    TestCaseIds,
    TestCaseStatusUpdate,
    TestCaseUpdate,
)

__all__ = [
    "Approval", "BulkStatusUpdate", "CreateTestCase", "GroupName", "ItemEdit", "LoginBody", "SelectionBody",
    "TestCaseGroups", "TestCaseIds", "TestCaseStatusUpdate", "TestCaseUpdate", "TurnText",
]
