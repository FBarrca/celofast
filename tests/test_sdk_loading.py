import pytest

from celofast.sdk.loading import (
    RUNTIME_API_VERSION,
    SDKCompatibilityError,
    load_capture,
    require_runtime,
)


def test_current_runtime_is_accepted():
    require_runtime(RUNTIME_API_VERSION)


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6, 99])
def test_other_runtimes_require_regeneration(version):
    with pytest.raises(SDKCompatibilityError, match="rerun celofast km pull"):
        require_runtime(version)


def test_packages_with_capture_sidecars_require_regeneration(tmp_path):
    # Packages from runtime API 6 and earlier call load_capture at import.
    with pytest.raises(SDKCompatibilityError, match="capture.json.*Rerun celofast km pull"):
        load_capture(tmp_path / "capture.json", runtime_api=6, digest="unused")
