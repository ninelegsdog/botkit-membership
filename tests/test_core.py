from src.core.auth import AdminGate
from src.core.navigation import NavRegistry


def test_auth_gate():
    gate = AdminGate("secret")
    assert gate.is_admin(123) is False
    assert gate.authorize(123, "secret") is True
    assert gate.is_admin(123) is True


def test_nav_registry():
    from src.core.navigation import NavSection

    nav = NavRegistry()
    nav.register(NavSection(slug="test", title="Test"))
    assert nav.title("test") == "Test"
    assert nav.title("missing") == "missing"
