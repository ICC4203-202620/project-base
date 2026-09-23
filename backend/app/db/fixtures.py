"""Deterministic teaching data used only by the explicitly enabled local seed."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class CuisineStyleFixture:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True)
class UserFixture:
    """A teaching account.

    The handle is stored without its at sign and the nationality as an ISO
    3166-1 alpha-2 code, which is the form the registration endpoint writes.
    """

    id: UUID
    email: str
    handle: str
    name: str
    nationality: str
    password: str


@dataclass(frozen=True)
class RestaurantFixture:
    id: UUID
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    cuisine_styles: tuple[str, ...]


@dataclass(frozen=True)
class ReviewFixture:
    id: UUID
    photo_id: UUID
    author_id: UUID
    restaurant_id: UUID
    asset_name: str
    content_type: str
    dish_name: str
    text: str
    visibility: str
    created_at: datetime


DEMO_USERS = (
    UserFixture(
        UUID("00000000-0000-4000-8000-000000000001"),
        "demo@example.com",
        "demo",
        "Demo Foodie",
        "CL",
        "demo-password",
    ),
    UserFixture(
        UUID("00000000-0000-4000-8000-000000000002"),
        "demo2@example.com",
        "demo2",
        "Demo Foodie Dos",
        "AR",
        "demo-password",
    ),
    UserFixture(
        UUID("00000000-0000-4000-8000-000000000003"),
        "empty@example.com",
        "empty",
        "Empty Feed",
        "PE",
        "demo-password",
    ),
)

USER_FOLLOWS = (
    (
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("00000000-0000-4000-8000-000000000002"),
    ),
)
RESTAURANT_FOLLOWS = (
    (
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("20000000-0000-4000-8000-000000000001"),
    ),
)
REVIEW_FIXTURES = (
    ReviewFixture(
        UUID("30000000-0000-4000-8000-000000000001"),
        UUID("40000000-0000-4000-8000-000000000001"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "pastel-de-choclo.webp",
        "image/webp",
        "Pastel de choclo",
        "Reseña pública visible por ambos seguimientos.",
        "public",
        datetime(2026, 8, 20, 12, tzinfo=UTC),
    ),
    ReviewFixture(
        UUID("30000000-0000-4000-8000-000000000002"),
        UUID("40000000-0000-4000-8000-000000000002"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000002"),
        "ceviche.webp",
        "image/webp",
        "Ceviche",
        "Reseña pública visible por autor seguido.",
        "public",
        datetime(2026, 8, 19, 12, tzinfo=UTC),
    ),
    ReviewFixture(
        UUID("30000000-0000-4000-8000-000000000003"),
        UUID("40000000-0000-4000-8000-000000000003"),
        DEMO_USERS[0].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "Sopaipillas",
        "Reseña privada docente.",
        "private",
        datetime(2026, 8, 18, 12, tzinfo=UTC),
    ),
    ReviewFixture(
        UUID("30000000-0000-4000-8000-000000000004"),
        UUID("40000000-0000-4000-8000-000000000004"),
        DEMO_USERS[2].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "Sopaipillas con pebre",
        "Reseña pública visible sólo por restaurante seguido.",
        "public",
        datetime(2026, 8, 18, 18, tzinfo=UTC),
    ),
)


CUISINE_STYLES = (
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000001"), "chilena", "Chilena"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000002"), "peruana", "Peruana"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000003"), "italiana", "Italiana"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000004"), "japonesa", "Japonesa"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000005"), "india", "India"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000006"), "vegana", "Vegana"),
    CuisineStyleFixture(UUID("10000000-0000-4000-8000-000000000007"), "cafeteria", "Cafetería"),
    CuisineStyleFixture(
        UUID("10000000-0000-4000-8000-000000000008"), "sandwicheria", "Sandwichería"
    ),
)


# Los nombres son ficticios. Las direcciones y coordenadas sólo buscan ofrecer
# datos plausibles para ejercicios; no representan locales comerciales reales.
RESTAURANTS = (
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000001"),
        "Cocina del Barrio",
        "Av. Italia 1280, Providencia",
        Decimal("-33.439120"),
        Decimal("-70.625130"),
        ("chilena", "vegana"),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000002"),
        "Puerto Lima",
        "Manuel Montt 640, Providencia",
        Decimal("-33.430540"),
        Decimal("-70.619820"),
        ("peruana",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000003"),
        "Trattoria Nómada",
        "José Victorino Lastarria 190, Santiago",
        Decimal("-33.438360"),
        Decimal("-70.640310"),
        ("italiana",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000004"),
        "Sakura Norte",
        "Av. Pedro de Valdivia 920, Providencia",
        Decimal("-33.425620"),
        Decimal("-70.610840"),
        ("japonesa",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000005"),
        "Especias del Sur",
        "Merced 460, Santiago",
        Decimal("-33.437050"),
        Decimal("-70.644120"),
        ("india", "vegana"),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000006"),
        "Verde Urbano",
        "Antonia López de Bello 130, Recoleta",
        Decimal("-33.432180"),
        Decimal("-70.638920"),
        ("vegana",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000007"),
        "Taza Central",
        "Huérfanos 860, Santiago",
        Decimal("-33.439920"),
        Decimal("-70.649580"),
        ("cafeteria",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000008"),
        "Pan y Punto",
        "Irarrázaval 2450, Ñuñoa",
        Decimal("-33.453770"),
        Decimal("-70.600450"),
        ("sandwicheria", "cafeteria"),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000009"),
        "Mesa Cordillera",
        "Av. Apoquindo 3300, Las Condes",
        Decimal("-33.414770"),
        Decimal("-70.585240"),
        ("chilena", "peruana"),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000010"),
        "Piccola Estación",
        "Av. Providencia 1750, Providencia",
        Decimal("-33.425080"),
        Decimal("-70.611420"),
        ("italiana", "cafeteria"),
    ),
    # Los dos siguientes ejercitan la búsqueda: «cafe» debe encontrar «Café
    # Ñielol» pese a los acentos, y «cocina» debe devolver dos restaurantes.
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000011"),
        "Café Ñielol",
        "Merced 120, Santiago",
        Decimal("-33.436640"),
        Decimal("-70.646980"),
        ("cafeteria",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000012"),
        "Cocina Andina",
        "Av. Matta 980, Santiago",
        Decimal("-33.462310"),
        Decimal("-70.645510"),
        ("peruana", "chilena"),
    ),
    # Los cuatro siguientes están en Valparaíso: un rectángulo del mapa tiene
    # que poder separarlos de los de Santiago. Los dos primeros quedan a unos
    # treinta metros uno del otro, para ejercitar el agrupamiento de
    # marcadores en el cliente.
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000013"),
        "Ancla y Sal",
        "Esmeralda 940, Valparaíso",
        Decimal("-33.045000"),
        Decimal("-71.619000"),
        ("chilena",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000014"),
        "Muelle Doce",
        "Esmeralda 960, Valparaíso",
        Decimal("-33.045300"),
        Decimal("-71.619200"),
        ("sandwicheria",),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000015"),
        "Terraza Marina",
        "Av. Altamirano 1480, Valparaíso",
        Decimal("-33.031200"),
        Decimal("-71.634800"),
        ("italiana", "vegana"),
    ),
    RestaurantFixture(
        UUID("20000000-0000-4000-8000-000000000016"),
        "Ola Brava",
        "Av. San Martín 620, Viña del Mar",
        Decimal("-33.019400"),
        Decimal("-71.552300"),
        ("japonesa",),
    ),
)
