import pytest

from celofast.sdk import Capture, Source
from celofast.sdk.loading import SDKCompatibilityError, capture_digest, load_capture


def test_import_requires_matching_runtime_and_capture(tmp_path):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"), {}
    )
    path = tmp_path / "capture.json"
    path.write_text(capture.model_dump_json())
    digest = capture_digest(capture)
    assert load_capture(path, runtime_api=6, digest=digest) == capture
    with pytest.raises(SDKCompatibilityError, match="runtime"):
        load_capture(path, runtime_api=99, digest=digest)
    path.write_text(capture.model_dump_json().replace('"draft"', '"published"'))
    with pytest.raises(SDKCompatibilityError, match="differ"):
        load_capture(path, runtime_api=6, digest=digest)
    path.write_text('{"format_version": 99}')
    with pytest.raises(SDKCompatibilityError, match="format"):
        load_capture(path, runtime_api=6, digest=digest)


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 99])
def test_old_runtime_requires_regeneration(tmp_path, version):
    with pytest.raises(SDKCompatibilityError, match="rerun celofast km pull"):
        load_capture(tmp_path / "capture.json", runtime_api=version, digest="unused")
