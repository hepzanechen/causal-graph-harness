import pytest
from adapters.stubs import InternalDBAdapter, ManualDocAdapter, ExperimentResultsAdapter


@pytest.mark.parametrize("cls", [InternalDBAdapter, ManualDocAdapter, ExperimentResultsAdapter])
def test_stub_adapters_raise_not_implemented(cls):
    adapter = cls()
    with pytest.raises(NotImplementedError):
        adapter.fetch("anything")
