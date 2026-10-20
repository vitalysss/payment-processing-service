import ast
from pathlib import Path

APP_ROOT = Path(__file__).parents[1] / "src" / "app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def assert_layer_has_no_forbidden_imports(layer: str, forbidden: tuple[str, ...]) -> None:
    violations: list[str] = []
    for path in (APP_ROOT / layer).rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(forbidden):
                violations.append(f"{path.relative_to(APP_ROOT)} imports {module}")
    assert not violations, "Layer dependency violations:\n" + "\n".join(violations)


def test_domain_is_framework_independent() -> None:
    assert_layer_has_no_forbidden_imports(
        "domain",
        ("app.application", "app.infrastructure", "app.presentation", "fastapi", "faststream", "sqlalchemy", "httpx", "pydantic"),
    )


def test_application_does_not_depend_on_infrastructure_or_delivery_frameworks() -> None:
    assert_layer_has_no_forbidden_imports(
        "application",
        ("app.infrastructure", "app.presentation", "fastapi", "faststream", "sqlalchemy", "httpx"),
    )
