"""anklume — framework déclaratif de compartimentalisation d'infrastructure."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anklume")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
