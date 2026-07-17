"""Entry point — uvicorn runs this module."""

from app.interfaces.api.app import create_app

app = create_app()
