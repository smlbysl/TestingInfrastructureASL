"""Shared test settings: the project under test and the UTS used by the tests.

Change PROJECTS to test another project. ASL_UTS=http selects the real UTS
(HttpUtsClient, not implemented yet); anything else uses the simulated FakeUtsClient.
"""
import os

from asl_testing import FakeUtsClient
from projects.example_project.buses import CanBase, Mil1553Base
from projects.example_project.header import ProjectBase

PROJECTS = [ProjectBase, Mil1553Base, CanBase]

SRC, DEST = 0x0001, 0x0002


def make_uts():
    if os.environ.get("ASL_UTS") == "http":
        from asl_testing import HttpUtsClient
        return HttpUtsClient(os.environ["ASL_UTS_URL"])
    return FakeUtsClient()
