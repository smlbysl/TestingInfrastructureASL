"""Shared test settings: the project under test and the adapter used by the tests.

Change PROJECTS to test another project. make_adapter() returns the simulated FakeUtsAdapter;
for the real UTS return your UtsAdapter subclass (post / get written with the ApiWrapper) here.
"""

__author__ = "İsmail Baysal"

from asl_testing import FakeUtsAdapter
from projects.example_project.header import ProjectBase

PROJECTS = [ProjectBase]

SRC, DEST = 0x0001, 0x0002


def make_adapter():
    return FakeUtsAdapter()
