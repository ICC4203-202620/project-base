"""The documented contract and the one `/docs` exposes have to be the same.

This suite exists because they drifted. The README grew one épica at a time and
ended up asserting things that had stopped being true, and seven operations
reached OpenAPI with the summary FastAPI derives from the function name. None
of it broke a test, because no test looked.

These are cheap checks over the generated OpenAPI. They do not verify that the
prose is right — nothing can — but they do catch the two ways it goes stale:
an endpoint nobody documented, and a document describing one that no longer
exists.
"""

import re
from pathlib import Path

from app.main import app

API_REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "api.md"
BACKEND_README = Path(__file__).resolve().parents[1] / "README.md"

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def operations():
    """Every operation the application exposes, as (method, path)."""
    return {
        (method.upper(), re.sub(r"\{[^}]+\}", "{}", path))
        for path, methods in app.openapi()["paths"].items()
        for method in methods
    }


def documented_operations():
    return {
        (match.group(1), re.sub(r"\{[^}]+\}", "{}", match.group(2).rstrip(".,")))
        for match in re.finditer(
            rf"\b({'|'.join(METHODS)})\s+`?(/[\w/{{}}.-]+)", API_REFERENCE.read_text()
        )
    }


def test_every_exposed_operation_is_documented():
    missing = sorted(operations() - documented_operations())

    assert not missing, f"sin documentar en docs/api.md: {missing}"


def test_no_documented_operation_has_disappeared():
    invented = sorted(documented_operations() - operations())

    assert not invented, f"documentadas en docs/api.md pero inexistentes: {invented}"


def test_every_operation_carries_a_summary_somebody_wrote():
    anonymous = [
        f"{method.upper()} {path}"
        for path, methods in app.openapi()["paths"].items()
        for method, operation in methods.items()
        # FastAPI derives one from the function name — "Create", "Healthz" —
        # which is a placeholder and not a description.
        if len(operation.get("summary", "").split()) < 2
    ]

    assert not anonymous, f"resumen autogenerado: {anonymous}"


def test_no_successful_response_is_left_with_the_generic_description():
    generic = [
        f"{method.upper()} {path} {code}"
        for path, methods in app.openapi()["paths"].items()
        for method, operation in methods.items()
        for code, response in operation.get("responses", {}).items()
        if code.startswith("2") and response.get("description") == "Successful Response"
    ]

    assert not generic, f"respuesta 2xx sin describir: {generic}"


def test_the_map_of_the_readme_reaches_every_épica():
    readme = BACKEND_README.read_text()

    # One row per épica of the statement, each linking into the reference.
    links = re.findall(r"\]\(docs/api\.md#(\d{1,2})-", readme)

    assert sorted(int(number) for number in links) == list(range(1, 18))


def test_the_links_of_the_readme_into_the_reference_resolve():
    reference = API_REFERENCE.read_text()
    anchors = set()
    for heading in re.finditer(r"^#{1,6}\s+(.*)$", reference, re.MULTILINE):
        slug = re.sub(r"[^\w\s-]", "", heading.group(1).strip().lower(), flags=re.UNICODE)
        anchors.add(re.sub(r"\s+", "-", slug))

    broken = [
        anchor
        for anchor in re.findall(r"\]\(docs/api\.md#([^)]+)\)", BACKEND_README.read_text())
        if anchor not in anchors
    ]

    assert not broken, f"anclas rotas hacia docs/api.md: {broken}"
