import prospector


def test_package_imports_with_version():
    assert prospector.__version__ == "0.1.0"
