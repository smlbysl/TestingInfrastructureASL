"""Shared test settings: the project under test and the backend used by the tests.

Change PROJECTS to test another project. make_backend() returns the simulated FakeBackend;
for the real UTS return UtsBackend(WrapperUtsApi(...)) here.
"""

__author__ = "İsmail Baysal"

from asl_testing import FakeBackend
from projects.example_project.header import ProjectBase

PROJECTS = [ProjectBase]

SRC, DEST = 0x0001, 0x0002


def make_backend():
    return FakeBackend()
