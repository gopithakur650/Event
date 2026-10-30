import pytest

from app import create_app
from app.models import Category
from extensions import db


@pytest.fixture
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "JWT_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
        "JWT_COOKIE_SECURE": False,
    })
    with application.app_context():
        db.create_all()
        db.session.add(Category(name="Workshops"))
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
