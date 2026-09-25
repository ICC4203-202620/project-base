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
class PhotoFixture:
    """A photograph published with no review on it.

    `upload_group` relates the ones published in a single act, which the feed
    shows as one entry.
    """

    id: UUID
    author_id: UUID
    restaurant_id: UUID
    asset_name: str
    content_type: str
    kind: str
    dish_name: str | None
    caption: str | None
    visibility: str
    created_at: datetime
    upload_group: UUID | None = None


@dataclass(frozen=True)
class EvaluationFixture:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    ratings: tuple[tuple[str, int], ...]
    comment: str
    visibility: str
    created_at: datetime
    photo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class VisitFixture:
    """A check-in.

    `occurred_at` is when the person was there and `published_at` when they
    recorded it. They differ in one fixture on purpose, because that is the
    difference the profile and the feed order by.
    """

    id: UUID
    author_id: UUID
    restaurant_id: UUID
    occurred_at: datetime
    published_at: datetime
    visibility: str


@dataclass(frozen=True)
class ReviewFixture:
    id: UUID
    photo_id: UUID
    author_id: UUID
    restaurant_id: UUID
    asset_name: str
    content_type: str
    dish_name: str
    rating: int
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
    # Los dos siguientes ejercitan la búsqueda de personas: «demo» comparte
    # prefijo con las cuentas de arriba, y «sibarita» aparece dentro de un
    # handle que no empieza con esa palabra.
    UserFixture(
        UUID("00000000-0000-4000-8000-000000000004"),
        "demo_viajera@example.com",
        "demo_viajera",
        "Demo Viajera",
        "MX",
        "demo-password",
    ),
    UserFixture(
        UUID("00000000-0000-4000-8000-000000000005"),
        "sibarita@example.com",
        "la_sibarita",
        "La Sibarita",
        "ES",
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
        5,
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
        4,
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
        2,
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
        3,
        "Reseña pública visible sólo por restaurante seguido.",
        "public",
        datetime(2026, 8, 18, 18, tzinfo=UTC),
    ),
)


VISIT_FIXTURES = (
    VisitFixture(
        UUID("50000000-0000-4000-8000-000000000001"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        datetime(2026, 8, 19, 20, tzinfo=UTC),
        datetime(2026, 8, 19, 20, tzinfo=UTC),
        "public",
    ),
    VisitFixture(
        UUID("50000000-0000-4000-8000-000000000002"),
        DEMO_USERS[0].id,
        UUID("20000000-0000-4000-8000-000000000002"),
        datetime(2026, 8, 17, 13, tzinfo=UTC),
        datetime(2026, 8, 17, 13, tzinfo=UTC),
        "private",
    ),
    VisitFixture(
        UUID("50000000-0000-4000-8000-000000000003"),
        DEMO_USERS[2].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        datetime(2026, 8, 20, 9, tzinfo=UTC),
        datetime(2026, 8, 20, 9, tzinfo=UTC),
        "public",
    ),
    # Recorded well after it happened: it is the oldest in its author's
    # profile and the most recent in the feed of whoever follows them.
    VisitFixture(
        UUID("50000000-0000-4000-8000-000000000004"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000003"),
        datetime(2026, 7, 10, 21, tzinfo=UTC),
        datetime(2026, 8, 21, 10, tzinfo=UTC),
        "public",
    ),
)


# Published without a review, which is what épica 8 makes possible. The first
# two show the same dish as photographed by two different people, so grouping
# by dish has something to group.
PHOTO_FIXTURES = (
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000001"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "dish",
        "Sopaipillas",
        "Recién salidas, con pebre al lado.",
        "public",
        datetime(2026, 8, 22, 13, tzinfo=UTC),
    ),
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000002"),
        DEMO_USERS[2].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "dish",
        "sopaipillas",
        None,
        "public",
        datetime(2026, 8, 22, 14, tzinfo=UTC),
    ),
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000003"),
        DEMO_USERS[0].id,
        UUID("20000000-0000-4000-8000-000000000002"),
        "ceviche.webp",
        "image/webp",
        "dish",
        "Ceviche",
        None,
        "private",
        datetime(2026, 8, 23, 20, tzinfo=UTC),
    ),
    # Tres fotografías del menú publicadas en un mismo acto: el feed las
    # muestra como una sola entrada.
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000004"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "pastel-de-choclo.webp",
        "image/webp",
        "menu",
        None,
        "Carta de fondos.",
        "public",
        datetime(2026, 8, 24, 11, tzinfo=UTC),
        UUID("70000000-0000-4000-8000-000000000001"),
    ),
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000005"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "ceviche.webp",
        "image/webp",
        "menu",
        None,
        "Carta de entradas.",
        "public",
        datetime(2026, 8, 24, 11, 1, tzinfo=UTC),
        UUID("70000000-0000-4000-8000-000000000001"),
    ),
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000006"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "menu",
        None,
        None,
        "public",
        datetime(2026, 8, 24, 11, 2, tzinfo=UTC),
        UUID("70000000-0000-4000-8000-000000000001"),
    ),
    PhotoFixture(
        UUID("60000000-0000-4000-8000-000000000007"),
        DEMO_USERS[2].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        "sopaipillas.webp",
        "image/webp",
        "venue",
        None,
        "La terraza al atardecer.",
        "public",
        datetime(2026, 8, 25, 19, tzinfo=UTC),
    ),
)


# Dos públicas sobre el mismo restaurante con calificaciones distintas, una
# privada que no mueve ningún promedio, y una con fotografías asociadas.
EVALUATION_FIXTURES = (
    EvaluationFixture(
        UUID("80000000-0000-4000-8000-000000000001"),
        DEMO_USERS[1].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        (("comida", 5), ("servicio", 4), ("ambiente", 5), ("precio-calidad", 4)),
        "Volvería sin dudarlo.",
        "public",
        datetime(2026, 8, 26, 13, tzinfo=UTC),
        (UUID("60000000-0000-4000-8000-000000000004"),),
    ),
    EvaluationFixture(
        UUID("80000000-0000-4000-8000-000000000002"),
        DEMO_USERS[2].id,
        UUID("20000000-0000-4000-8000-000000000001"),
        (("comida", 3), ("servicio", 2), ("ambiente", 4), ("precio-calidad", 3)),
        "Buena comida, servicio lento.",
        "public",
        datetime(2026, 8, 26, 18, tzinfo=UTC),
    ),
    EvaluationFixture(
        UUID("80000000-0000-4000-8000-000000000003"),
        DEMO_USERS[0].id,
        UUID("20000000-0000-4000-8000-000000000002"),
        (("comida", 4), ("servicio", 5), ("ambiente", 3), ("precio-calidad", 4)),
        "Evaluación privada docente.",
        "private",
        datetime(2026, 8, 27, 20, tzinfo=UTC),
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
