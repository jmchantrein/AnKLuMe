"""anklume web platform — shared components for guide, labs, and dashboard."""


def create_app(title: str = "anklume"):
    """Create a FastAPI application with standard config."""
    from fastapi import FastAPI

    return FastAPI(title=title)
