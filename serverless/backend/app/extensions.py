"""Extensiones del grupo: mantener vacías en el primer despliegue docente.

Registrar tablas no crea endpoints ni implementa un emisor. Evitar importar
Pillow o bibliotecas Web Push aquí: este módulo lo usan las funciones HTTP.
"""


def register_tables(metadata) -> None:
    """Agregar Table(..., metadata, ...) de suscripciones y extensiones propias.

    Se llama al construir los modelos compartidos, sin conectarse a la BD.
    No existe un esquema docente de suscripciones que haya que adoptar.
    """


def migrate_schema(engine) -> None:
    """Aplicar cambios aditivos explícitos, sólo desde mantenimiento local.

    Una DDL por transacción y cambios idempotentes. Este hook NO interpreta
    diferencias de columnas ni las aplica automáticamente. No borrar tablas,
    reinicializar registros o sobrescribir las suscripciones existentes.
    """
