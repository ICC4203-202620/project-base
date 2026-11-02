"""Preparación LOCAL y explícita; este módulo nunca se empaqueta en Lambda.

No ejecuta migraciones destructivas ni modifica filas existentes. Agregar nuevas
tablas a metadata es aditivo; cambiar columnas existentes exige una migración
explícita del grupo. No se infiere ni se aplica un ALTER a partir de los modelos.
"""

import argparse
import re
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.config import DatabaseBackend, settings
from app.db.schema import metadata
from app.db.session import engine
from app.extensions import migrate_schema

ROLE_ARN = re.compile(r"arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+\Z")


def _scalar(database, statement, parameters=None):
    with database.begin() as connection:
        return connection.execute(text(statement), parameters or {}).scalar()


def prepare_schema(database, *, before_indexes: Callable | None = None) -> None:
    """Una DDL por transacción; esperar y comprobar los índices asíncronos."""
    for table in metadata.sorted_tables:
        with database.begin() as connection:
            connection.execute(CreateTable(table, if_not_exists=True))
    print(f"Tablas verificadas: {len(metadata.tables)}.", flush=True)

    # Los cambios explícitos en columnas existentes preceden a los nuevos
    # índices que puedan referenciarlas. No se deducen ALTER automáticos.
    if before_indexes is not None:
        before_indexes(database)

    total_indexes = sum(len(table.indexes) for table in metadata.sorted_tables)
    ordinal = 0
    for table in metadata.sorted_tables:
        for index in sorted(table.indexes, key=lambda item: item.name):
            ordinal += 1
            validity = _scalar(
                database,
                """
                SELECT i.indisvalid FROM pg_index AS i
                JOIN pg_class AS c ON c.oid = i.indexrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = :name
            """,
                {"name": index.name},
            )
            if validity is True:
                continue
            if validity is False:
                raise RuntimeError(
                    f"Index {index.name} is not valid; inspect its DSQL job before retrying"
                )
            with database.begin() as connection:
                # El dialecto oficial compila CREATE [UNIQUE] INDEX ASYNC.
                job_id = connection.execute(CreateIndex(index)).scalar_one()
            print(
                f"Índice {ordinal}/{total_indexes}: esperando la creación de {index.name}.",
                flush=True,
            )
            # DSQL no permite esperar el trabajo dentro de un bloque transaccional.
            # Solo esta llamada usa autocommit; DDL y permisos mantienen sus transacciones.
            with database.connect() as connection:
                connection = connection.execution_options(isolation_level="AUTOCOMMIT")
                finished = connection.execute(
                    text("CALL sys.wait_for_job(:job_id)"), {"job_id": job_id}
                ).scalar()
            if not finished:
                raise RuntimeError(f"Index {index.name} did not finish successfully")
            print(f"Índice {ordinal}/{total_indexes}: {index.name} listo.", flush=True)
    print(f"Índices verificados: {total_indexes}.", flush=True)


def grant_application_access(database, role_arns: list[str]) -> None:
    """Rol SQL sin DDL, enlazado a los roles de ejecución identificados por CF."""
    for arn in role_arns:
        if not ROLE_ARN.fullmatch(arn):
            raise ValueError("Expected an AWS IAM role ARN, not a user or STS session ARN")
    exists = _scalar(database, "SELECT 1 FROM pg_roles WHERE rolname = 'app_user'")
    if not exists:
        with database.begin() as connection:
            connection.execute(text("CREATE ROLE app_user WITH LOGIN"))
    for arn in dict.fromkeys(role_arns):
        mapped = _scalar(
            database,
            """
            SELECT 1 FROM sys.iam_pg_role_mappings
            WHERE pg_role_name = 'app_user' AND arn = :arn
        """,
            {"arn": arn},
        )
        if not mapped:
            # ARN validado estrictamente arriba; AWS IAM GRANT no permite
            # un parámetro en la posición del literal de identidad.
            with database.begin() as connection:
                connection.execute(text(f"AWS IAM GRANT app_user TO '{arn}'"))
    # public es un esquema de sistema en DSQL; no se modifica su ACL.
    # El permiso de uso debe existir antes de conceder acceso a nuestras tablas.
    if not _scalar(database, "SELECT has_schema_privilege('app_user', 'public', 'USAGE')"):
        raise RuntimeError(
            "app_user no tiene permiso USAGE sobre public; se debe revisar la configuración "
            "del esquema antes de continuar"
        )
    # El rol compartido conserva el contrato docente. IAM limita además los
    # recursos AWS accesibles por cada función; no se concede CREATE/DROP.
    with database.begin() as connection:
        connection.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
        )


def prepare_database(role_arns: list[str], *, seed: bool = False) -> dict:
    if settings.database_backend is not DatabaseBackend.AURORA_DSQL:
        raise ValueError("Maintenance requires DATABASE_BACKEND=aurora-dsql")
    if settings.aurora_dsql_user != "admin":
        raise ValueError("Local maintenance requires AURORA_DSQL_USER=admin")
    if not role_arns:
        raise ValueError("Supply the execution role ARNs from CloudFormation outputs")
    # Validar todas las identidades antes de la primera modificación.
    if any(not ROLE_ARN.fullmatch(arn) for arn in role_arns):
        raise ValueError("Invalid execution role ARN")
    prepare_schema(engine, before_indexes=migrate_schema)
    grant_application_access(engine, role_arns)
    print("Permisos de las funciones preparados.", flush=True)
    changed = False
    if seed:
        from app.db.seed import seed as insert_demo_data

        print("Preparando los datos docentes faltantes.", flush=True)
        changed = insert_demo_data(enabled=True)
        detail = "se incorporaron registros" if changed else "no había registros faltantes"
        print(f"Preparación de datos docentes finalizada: {detail}.", flush=True)
    return {"schema": "ready", "seed_changed": changed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-arn", action="append", required=True)
    parser.add_argument("--seed", action="store_true", help="Insert only missing demo fixtures")
    args = parser.parse_args()
    prepare_database(args.role_arn, seed=args.seed)
    print("Mantenimiento de la base de datos finalizado.", flush=True)


if __name__ == "__main__":
    main()
