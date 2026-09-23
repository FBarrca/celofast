import pytest

from celofast.sdk.loading import RUNTIME_API_VERSION, SDKCompatibilityError, require_runtime


def test_current_runtime_is_accepted():
    require_runtime(RUNTIME_API_VERSION)


@pytest.mark.parametrize("version", [RUNTIME_API_VERSION - 1, RUNTIME_API_VERSION + 1])
def test_other_runtimes_require_regeneration(version):
    with pytest.raises(SDKCompatibilityError, match="rerun celofast km pull"):
        require_runtime(version)
