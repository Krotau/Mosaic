"""Package installation smoke tests."""

from mosaic import __version__


def test_installed_package_is_importable() -> None:
    """The source-layout package is available through its installation metadata."""
    assert __version__ == "0.1.0"
