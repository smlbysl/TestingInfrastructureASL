"""pytest fixtures: the same clean start as tests/base.py, for function-style tests.

    def test_answer(comm):                     # opened Comm, closed after the test
        ...

    @pytest.mark.hardware                      # skipped unless ASL_HARDWARE=1
    def test_on_target(comm):
        ...

unittest-style classes (CommTestCase, HardwareTestCase) also run under pytest as they are.
"""

__author__ = "İsmail Baysal"

import pytest

from tests.base import HARDWARE, TIMEOUT, open_comm
from tests.settings import make_backend


def pytest_collection_modifyitems(config, items):
    if HARDWARE:
        return
    skip = pytest.mark.skip(reason="hardware tests: set ASL_HARDWARE=1")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def backend():
    """New backend (tests/settings.make_backend)."""
    return make_backend()


@pytest.fixture
def comm(backend):
    """Clean registry, opened Comm on the backend fixture; closed after the test."""
    c = open_comm(backend)
    yield c
    c.close()


@pytest.fixture
def timeout() -> float:
    """Default wait time (ASL_TIMEOUT)."""
    return TIMEOUT
