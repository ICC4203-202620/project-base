"""Despliegue local de la base: preparación, CloudFormation, datos y frontend.

No utiliza AWS CLI ni ejecuta cambios al importar este módulo. Todas las
operaciones remotas parten de una cuenta verificada y de un despliegue identificado.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid

import boto3
from botocore.exceptions import ClientError, WaiterError

from package import PackageError, build_packages

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ("accounts", "domain", "photos", "notifications")
TAG = "icc4203:deployment"
PROTECTED_TYPES = {
    "AWS::DSQL::Cluster",
    "AWS::S3::Bucket",
    "AWS::CloudFront::Distribution",
}


class DeploymentError(RuntimeError):
    pass


def load_config(filename: Path) -> dict:
    data = json.loads(filename.read_text(encoding="utf-8"))
    allowed = {
        "deployment_name",
        "region",
        "expected_account_id",
        "profile",
        "frontend_dir",
        "frontend_build_dir",
        "package_manager",
        "frontend_environment",
        "notifications_enabled",
        "vapid_public_key",
        "vapid_subject",
        "service_worker_files",
    }
    if not isinstance(data, dict) or set(data) - allowed:
        raise DeploymentError(
            "La configuración contiene campos desconocidos. No se deben guardar secretos en este archivo."
        )
    for key in allowed - {
        "frontend_environment",
        "notifications_enabled",
        "profile",
        "service_worker_files",
    }:
        if key in data and not isinstance(data[key], str):
            raise DeploymentError(f"{key} debe ser texto.")
    if data.get("profile") is not None and not isinstance(data["profile"], str):
        raise DeploymentError("profile debe ser texto o null.")
    if not isinstance(data.get("frontend_environment", {}), dict):
        raise DeploymentError(
            "frontend_environment debe ser un objeto de configuración pública."
        )
    workers = data.get("service_worker_files", ["sw.js", "service-worker.js"])
    if not isinstance(workers, list) or any(
        not isinstance(item, str)
        or not item
        or item.startswith("/")
        or "\\" in item
        or any(part in {"", ".", ".."} for part in item.split("/"))
        for item in workers
    ):
        raise DeploymentError(
            "service_worker_files debe contener rutas relativas del build, sin '..'."
        )
    if not re.fullmatch(
        r"[a-z][a-z0-9-]{1,22}[a-z0-9]", data.get("deployment_name", "")
    ):
        raise DeploymentError(
            "deployment_name debe tener entre 3 y 24 letras minúsculas, números o guiones, comenzar con una letra y terminar con letra o número."
        )
    if data.get("region") != "sa-east-1":
        raise DeploymentError("Esta base debe desplegarse en sa-east-1.")
    if data.get("package_manager", "npm") not in {"npm", "pnpm", "yarn"}:
        raise DeploymentError("package_manager debe ser npm, pnpm o yarn.")
    if not isinstance(data.get("notifications_enabled", False), bool):
        raise DeploymentError("notifications_enabled debe ser true o false.")
    for key, value in data.get("frontend_environment", {}).items():
        if not key.startswith("VITE_") or any(
            word in key.upper()
            for word in ("PRIVATE", "SECRET", "PASSWORD", "AWS_ACCESS", "SESSION_TOKEN")
        ):
            raise DeploymentError(
                "frontend_environment solo admite variables VITE_ públicas."
            )
        if not isinstance(value, str):
            raise DeploymentError(
                "Los valores de frontend_environment deben ser texto."
            )
    frontend = (
        filename.resolve().parent / data.get("frontend_dir", "../frontend")
    ).resolve()
    output = (frontend / data.get("frontend_build_dir", "dist")).resolve()
    if output == frontend or not output.is_relative_to(frontend):
        raise DeploymentError(
            "frontend_build_dir debe ser una subcarpeta del frontend."
        )
    data["frontend_path"] = frontend
    data["frontend_output"] = output
    return data


def verify_account(session, config: dict, *, required: bool = True) -> str:
    identity = session.client("sts").get_caller_identity()
    account = identity["Account"]
    if identity["Arn"].endswith(":root"):
        raise DeploymentError("No se deben utilizar credenciales de la cuenta root.")
    expected = config.get("expected_account_id", "")
    if expected and expected != account:
        raise DeploymentError(
            f"La cuenta autenticada ({account}) no corresponde a expected_account_id."
        )
    if required and not re.fullmatch(r"\d{12}", expected):
        raise DeploymentError(
            f"Configurar expected_account_id con la cuenta de destino. La identidad actual corresponde a {account}."
        )
    return account


def find_stack(cf, name: str) -> dict | None:
    try:
        return cf.describe_stacks(StackName=name)["Stacks"][0]
    except ClientError as error:
        info = error.response["Error"]
        if info["Code"] == "ValidationError" and "does not exist" in info.get(
            "Message", ""
        ):
            return None
        raise


def check_owned_stack(
    stack: dict, name: str, *, allow_in_progress: bool = False
) -> None:
    tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
    if tags.get(TAG) != name:
        raise DeploymentError(
            "El stack existente no está identificado como parte de este despliegue. No se modificará."
        )
    if not allow_in_progress and stack["StackStatus"].endswith("_IN_PROGRESS"):
        raise DeploymentError(
            "El stack tiene una operación en curso. Revisar CloudFormation antes de continuar."
        )


def stack_outputs(stack: dict) -> dict[str, str]:
    return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}


def artifact_bucket_name(config: dict, account: str) -> str:
    return f"{config['deployment_name']}-{account}-{config['region']}-code"


def check_bucket_owner(s3, bucket: str, account: str, name: str) -> None:
    s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
    tags = s3.get_bucket_tagging(Bucket=bucket, ExpectedBucketOwner=account)["TagSet"]
    if {item["Key"]: item["Value"] for item in tags}.get(TAG) != name:
        raise DeploymentError(
            f"El bucket {bucket} no pertenece al despliegue indicado."
        )


def ensure_artifact_bucket(s3, bucket: str, account: str, config: dict) -> None:
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": config["region"]},
        )
        s3.put_bucket_tagging(
            Bucket=bucket,
            ExpectedBucketOwner=account,
            Tagging={"TagSet": [{"Key": TAG, "Value": config["deployment_name"]}]},
        )
    check_bucket_owner(s3, bucket, account, config["deployment_name"])
    s3.put_public_access_block(
        Bucket=bucket,
        ExpectedBucketOwner=account,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=bucket,
        ExpectedBucketOwner=account,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ],
        },
    )


def build_frontend(config: dict) -> Path:
    directory = config["frontend_path"]
    manager = config.get("package_manager", "npm")
    executable = shutil.which(manager)
    if not executable or not (directory / "package.json").is_file():
        raise DeploymentError(
            "No se encontró el gestor de paquetes o el package.json del frontend."
        )
    lockfiles = {
        "npm": "package-lock.json",
        "pnpm": "pnpm-lock.yaml",
        "yarn": "yarn.lock",
    }
    if not (directory / lockfiles[manager]).is_file():
        raise DeploymentError(
            f"Falta {lockfiles[manager]} para reproducir el build del frontend."
        )
    sensitive = ("PRIVATE", "SECRET", "PASSWORD", "AWS_ACCESS", "SESSION_TOKEN")
    for key in os.environ:
        if key.startswith("VITE_") and any(word in key.upper() for word in sensitive):
            raise DeploymentError(
                "El entorno contiene una variable VITE_ que parece contener un secreto."
            )
    # Vite lee estos archivos por su cuenta, aunque se filtre el entorno del proceso.
    for envfile in directory.glob(".env*"):
        if not envfile.is_file():
            continue
        for line in envfile.read_text(encoding="utf-8").splitlines():
            key = line.strip().removeprefix("export ").split("=", 1)[0].strip()
            if key.startswith("VITE_") and any(
                word in key.upper() for word in sensitive
            ):
                raise DeploymentError(
                    "Un archivo de entorno del frontend contiene una variable VITE_ que parece contener un secreto."
                )
    # El build del cliente no necesita las credenciales utilizadas para desplegar.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AWS_") and key not in {"JWT_SECRET", "VAPID_PRIVATE_KEY"}
    }
    env.update(config.get("frontend_environment", {}))
    if config.get("vapid_public_key"):
        env["VITE_VAPID_PUBLIC_KEY"] = config["vapid_public_key"]
    install = {
        "npm": ["ci"],
        "pnpm": ["install", "--frozen-lockfile"],
        "yarn": ["install", "--frozen-lockfile"],
    }[manager]
    subprocess.run([executable, *install], cwd=directory, env=env, check=True)
    subprocess.run([executable, "run", "build"], cwd=directory, env=env, check=True)
    output = config["frontend_output"]
    if not (output / "index.html").is_file():
        raise DeploymentError("El build no generó index.html en frontend_build_dir.")
    frontend_files(output)  # Validar antes de modificar recursos AWS.
    return output


def frontend_files(directory: Path) -> list[Path]:
    files = []
    known_secrets = [
        value.encode()
        for key in (
            "JWT_SECRET",
            "VAPID_PRIVATE_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        )
        if len(value := os.environ.get(key, "")) >= 12
    ]
    for item in sorted(directory.rglob("*")):
        if item.is_symlink():
            raise DeploymentError(
                "El build del frontend no debe contener enlaces simbólicos."
            )
        if not item.is_file():
            continue
        relative = item.relative_to(directory)
        if any(
            part.startswith(".env")
            or part in {".git", "node_modules", "credentials.json"}
            for part in relative.parts
        ) or item.suffix.lower() in {".pem", ".key", ".p12"}:
            raise DeploymentError("El build contiene archivos que no deben publicarse.")
        if known_secrets and any(value in item.read_bytes() for value in known_secrets):
            raise DeploymentError(
                "El build contiene un secreto del entorno local y no se publicará."
            )
        files.append(item)
    return files


def publish_frontend(
    s3,
    bucket: str,
    directory: Path,
    account: str,
    service_worker_files=("sw.js", "service-worker.js"),
) -> None:
    # Recursos primero, index.html después y service workers al final. No se eliminan recursos
    # antiguos que una pestaña o un service worker todavía podrían necesitar.
    def order(item):
        key = item.relative_to(directory).as_posix()
        return 2 if key in service_worker_files else 1 if key == "index.html" else 0

    files = sorted(frontend_files(directory), key=order)
    for item in files:
        key = item.relative_to(directory).as_posix()
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        if item.suffix == ".js":
            content_type = "text/javascript"
        elif item.suffix == ".webmanifest":
            content_type = "application/manifest+json"
        with item.open("rb") as body:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl="no-cache",
                ExpectedBucketOwner=account,
            )


def parameters_for(
    config: dict,
    bucket: str,
    code_keys: dict[str, str],
    *,
    updating: bool,
    previous: dict | None = None,
) -> list[dict]:
    values = {
        "DeploymentName": config["deployment_name"],
        "ArtifactBucketName": bucket,
        **{f"{function.title()}CodeKey": key for function, key in code_keys.items()},
        "NotificationsEnabled": str(config.get("notifications_enabled", False)).lower(),
    }
    result = [
        {"ParameterKey": key, "ParameterValue": value} for key, value in values.items()
    ]
    result.append(
        {
            "ParameterKey": "JwtSecret",
            **(
                {"UsePreviousValue": True}
                if updating
                else {"ParameterValue": secrets.token_urlsafe(48)}
            ),
        }
    )
    initializing_vapid = config.get("notifications_enabled", False) and not (
        previous or {}
    ).get("VapidPublicKey")
    for key, value in {
        "VapidPrivateKey": os.environ.get("VAPID_PRIVATE_KEY", ""),
        "VapidPublicKey": config.get("vapid_public_key", ""),
        "VapidSubject": config.get("vapid_subject", ""),
    }.items():
        if updating and not initializing_vapid:
            result.append({"ParameterKey": key, "UsePreviousValue": True})
        else:
            result.append(
                {
                    "ParameterKey": key,
                    "ParameterValue": value if initializing_vapid else "",
                }
            )
    return result


def reject_destructive_changes(changes: list[dict]) -> None:
    for change in changes:
        resource = change.get("ResourceChange", {})
        if resource.get("ResourceType") not in PROTECTED_TYPES:
            continue
        if resource.get("Action") == "Remove" or resource.get("Replacement") in {
            "True",
            "Conditional",
        }:
            raise DeploymentError(
                f"La actualización eliminaría o reemplazaría {resource['LogicalResourceId']}. Se detuvo para conservar datos y dirección pública."
            )


def apply_stack(cf, config: dict, parameters: list[dict], *, updating: bool) -> None:
    name = config["deployment_name"]
    change_name = f"local-{uuid.uuid4().hex}"
    template = (ROOT / "template.yaml").read_text(encoding="utf-8")
    cf.create_change_set(
        StackName=name,
        ChangeSetName=change_name,
        ChangeSetType="UPDATE" if updating else "CREATE",
        TemplateBody=template,
        Parameters=parameters,
        Capabilities=["CAPABILITY_NAMED_IAM"],
        Tags=[{"Key": TAG, "Value": name}],
    )
    try:
        cf.get_waiter("change_set_create_complete").wait(
            StackName=name,
            ChangeSetName=change_name,
            WaiterConfig={"Delay": 5, "MaxAttempts": 120},
        )
    except WaiterError:
        description = cf.describe_change_set(StackName=name, ChangeSetName=change_name)
        reason = description.get("StatusReason", "")
        if updating and (
            "didn't contain changes" in reason
            or "No updates are to be performed" in reason
        ):
            cf.delete_change_set(StackName=name, ChangeSetName=change_name)
            print("CloudFormation: no hay cambios de infraestructura.")
            return
        raise DeploymentError(
            "No se pudo preparar el cambio. Revisar el change set en CloudFormation."
        ) from None
    changes = []
    for page in cf.get_paginator("describe_change_set").paginate(
        StackName=name, ChangeSetName=change_name
    ):
        changes.extend(page.get("Changes", []))
    try:
        reject_destructive_changes(changes)
    except DeploymentError:
        cf.delete_change_set(StackName=name, ChangeSetName=change_name)
        raise
    cf.execute_change_set(StackName=name, ChangeSetName=change_name)
    cf.get_waiter(
        "stack_update_complete" if updating else "stack_create_complete"
    ).wait(StackName=name, WaiterConfig={"Delay": 10, "MaxAttempts": 240})


def prepare_database(config: dict, outputs: dict, *, seed: bool) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "backend"),
            "ENVIRONMENT": "development",
            "AWS_DEFAULT_REGION": config["region"],
            "AWS_REGION": config["region"],
            "DATABASE_BACKEND": "aurora-dsql",
            "AURORA_DSQL_ENDPOINT": outputs["DsqlEndpoint"],
            "AURORA_DSQL_USER": "admin",
            "AURORA_DSQL_DATABASE": "postgres",
            "NOTIFICATIONS_ENABLED": "false",
            "MEDIA_STORAGE_BACKEND": "s3",
            "MEDIA_S3_BUCKET": outputs["MediaBucketName"],
            "MEDIA_S3_REGION": config["region"],
            "MEDIA_S3_PREFIX": "foodie",
            "SEED_DEMO_DATA": "true" if seed else "false",
        }
    )
    if config.get("profile"):
        # Una Session(profile_name=...) ignora credenciales directas del entorno.
        # Mantener la misma precedencia en el proceso de mantenimiento local.
        for key in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_SECURITY_TOKEN",
        ):
            env.pop(key, None)
        env["AWS_PROFILE"] = config["profile"]
    command = [sys.executable, "-m", "app.maintenance"]
    for function in FUNCTIONS:
        command.extend(["--role-arn", outputs[f"{function.title()}RoleArn"]])
    if seed:
        command.append("--seed")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def save_state(config: dict, account: str, stack: dict) -> None:
    path = ROOT / ".deployment" / f"{config['deployment_name']}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "account": account,
                "region": config["region"],
                "stack_id": stack["StackId"],
                "outputs": stack_outputs(stack),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def empty_bucket(s3, bucket: str, account: str) -> None:
    # Incluye versiones y delete markers; nunca recibe nombres por glob/prefijo.
    for page in s3.get_paginator("list_object_versions").paginate(
        Bucket=bucket, ExpectedBucketOwner=account
    ):
        objects = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in page.get("Versions", []) + page.get("DeleteMarkers", [])
        ]
        if objects:
            result = s3.delete_objects(
                Bucket=bucket,
                ExpectedBucketOwner=account,
                Delete={"Objects": objects, "Quiet": True},
            )
            if result.get("Errors"):
                raise DeploymentError(
                    f"No se pudieron eliminar todos los objetos de {bucket}."
                )
    for page in s3.get_paginator("list_multipart_uploads").paginate(
        Bucket=bucket, ExpectedBucketOwner=account
    ):
        for upload in page.get("Uploads", []):
            s3.abort_multipart_upload(
                Bucket=bucket,
                Key=upload["Key"],
                UploadId=upload["UploadId"],
                ExpectedBucketOwner=account,
            )


def delete_deployment(
    session, config: dict, account: str, stack: dict | None, confirmation: str | None
) -> None:
    name = config["deployment_name"]
    phrase = f"{account}/{name}"
    print(
        f"Se eliminarán los recursos, datos y fotografías de {phrase} en {config['region']}."
    )
    if confirmation is None:
        confirmation = input(f"Escribir {phrase} para confirmar: ")
    if confirmation != phrase:
        raise DeploymentError("Eliminación cancelada: la confirmación no coincide.")
    cf, s3 = session.client("cloudformation"), session.client("s3")
    buckets = []
    if stack:
        # Un change set CREATE fallido o no ejecutado deja un encabezado sin
        # recursos en REVIEW_IN_PROGRESS; no equivale a una operación en curso.
        check_owned_stack(
            stack, name, allow_in_progress=stack["StackStatus"] == "REVIEW_IN_PROGRESS"
        )
        for page in cf.get_paginator("list_stack_resources").paginate(
            StackName=stack["StackId"]
        ):
            for resource in page["StackResourceSummaries"]:
                if (
                    resource["ResourceType"] == "AWS::S3::Bucket"
                    and resource.get("PhysicalResourceId")
                    and resource["ResourceStatus"] != "DELETE_COMPLETE"
                ):
                    buckets.append(resource["PhysicalResourceId"])
        existing_buckets = []
        for bucket in buckets:
            try:
                s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
            except ClientError as error:
                # La consola u otra limpieza pueden haber eliminado el bucket.
                # Un error de permisos o de propietario no demuestra ausencia.
                if error.response["Error"]["Code"] not in {
                    "404",
                    "NoSuchBucket",
                    "NotFound",
                }:
                    raise
            else:
                existing_buckets.append(bucket)
        # Validar todos los propietarios antes de vaciar el primer bucket.
        for bucket in existing_buckets:
            empty_bucket(s3, bucket, account)
        cf.delete_stack(StackName=stack["StackId"])
        cf.get_waiter("stack_delete_complete").wait(
            StackName=stack["StackId"], WaiterConfig={"Delay": 10, "MaxAttempts": 240}
        )
    bucket = artifact_bucket_name(config, account)
    try:
        check_bucket_owner(s3, bucket, account, name)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    else:
        empty_bucket(s3, bucket, account)
        s3.delete_bucket(Bucket=bucket, ExpectedBucketOwner=account)
    state = ROOT / ".deployment" / f"{name}.json"
    state.unlink(missing_ok=True)
    print(
        "Despliegue y archivos de publicación eliminados. Los datos eliminados no pueden recuperarse con estos scripts."
    )


def run(args) -> None:
    config = load_config(args.config)
    session = boto3.Session(
        profile_name=config.get("profile"), region_name=config["region"]
    )
    account = verify_account(session, config, required=args.command != "check")
    name = config["deployment_name"]
    print(
        f"Cuenta: {account} | Región: {config['region']} | Despliegue: {name}",
        flush=True,
    )
    if args.command == "check":
        print(
            f"Frontend: {config['frontend_path']}\nSalida del build: {config['frontend_output']}"
        )
        print("Credenciales verificadas. No se crearon ni modificaron recursos.")
        return
    cf = session.client("cloudformation")
    stack = find_stack(cf, name)
    if stack:
        check_owned_stack(
            stack,
            name,
            allow_in_progress=args.command == "status"
            or (
                args.command == "delete"
                and stack["StackStatus"] == "REVIEW_IN_PROGRESS"
            ),
        )
    if args.command == "status":
        print(
            "No existe el despliegue."
            if not stack
            else json.dumps(
                {"status": stack["StackStatus"], "outputs": stack_outputs(stack)},
                indent=2,
            )
        )
        return
    if args.command == "delete":
        delete_deployment(session, config, account, stack, args.confirm)
        return
    if args.command == "database":
        if not stack or stack["StackStatus"] not in {
            "CREATE_COMPLETE",
            "UPDATE_COMPLETE",
            "UPDATE_ROLLBACK_COMPLETE",
        }:
            raise DeploymentError(
                "La preparación de datos requiere un stack existente y estable."
            )
        prepare_database(config, stack_outputs(stack), seed=args.seed)
        return
    updating = args.command == "update"
    if updating and not stack:
        raise DeploymentError(
            "No existe el despliegue. Primero se debe ejecutar deploy."
        )
    if not updating and stack:
        raise DeploymentError(
            "El despliegue ya existe. Utilizar update; deploy no reemplaza un stack existente."
        )
    if updating and stack["StackStatus"] not in {
        "CREATE_COMPLETE",
        "UPDATE_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
    }:
        raise DeploymentError(
            "El stack no está en un estado actualizable. Revisar CloudFormation; no se eliminará automáticamente."
        )
    previous = {
        p["ParameterKey"]: p.get("ParameterValue", "")
        for p in (stack or {}).get("Parameters", [])
    }
    if previous.get("VapidPublicKey") and config.get("vapid_public_key") not in {
        None,
        "",
        previous["VapidPublicKey"],
    }:
        raise DeploymentError(
            "La actualización debe conservar las claves VAPID existentes. No se realizará una rotación implícita."
        )
    if config.get("notifications_enabled"):
        if not config.get("vapid_public_key") or not config.get("vapid_subject"):
            raise DeploymentError(
                "Para habilitar notificaciones se requieren vapid_public_key y vapid_subject."
            )
        if not os.environ.get("VAPID_PRIVATE_KEY") and not previous.get(
            "VapidPublicKey"
        ):
            raise DeploymentError(
                "Para habilitar el emisor por primera vez se debe definir VAPID_PRIVATE_KEY en el entorno local."
            )
    s3 = session.client("s3")
    bucket = artifact_bucket_name(config, account)
    if updating and previous.get("ArtifactBucketName") != bucket:
        raise DeploymentError(
            "El bucket de código no corresponde al del despliegue existente."
        )
    output = build_frontend(config)
    with tempfile.TemporaryDirectory(prefix="icc4203-serverless-") as temporary:
        packages = build_packages(
            ROOT / "backend",
            Path(temporary),
            python_version="3.14",
            architecture="x86_64",
        )
        ensure_artifact_bucket(s3, bucket, account, config)
        keys = {}
        for function in FUNCTIONS:
            package = packages[function]
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            keys[function] = f"lambda/{function}/{digest}.zip"
            with package.open("rb") as body:
                s3.put_object(
                    Bucket=bucket,
                    Key=keys[function],
                    Body=body,
                    ExpectedBucketOwner=account,
                )
        print(
            "Creando el cambio de CloudFormation; la distribución puede tardar varios minutos.",
            flush=True,
        )
        apply_stack(
            cf,
            config,
            parameters_for(config, bucket, keys, updating=updating, previous=previous),
            updating=updating,
        )
    stack = find_stack(cf, name)
    if not stack:
        raise DeploymentError(
            "CloudFormation no devolvió el stack después del despliegue."
        )
    save_state(config, account, stack)
    outputs = stack_outputs(stack)
    print(
        "Preparando el esquema"
        + (
            " y los datos docentes."
            if not updating
            else " sin recargar los datos docentes."
        ),
        flush=True,
    )
    prepare_database(config, outputs, seed=not updating)
    publish_frontend(
        s3,
        outputs["FrontendBucketName"],
        output,
        account,
        config.get("service_worker_files", ["sw.js", "service-worker.js"]),
    )
    distribution = session.client("cloudfront")
    invalidation = distribution.create_invalidation(
        DistributionId=outputs["DistributionId"],
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": uuid.uuid4().hex,
        },
    )
    distribution.get_waiter("invalidation_completed").wait(
        DistributionId=outputs["DistributionId"],
        Id=invalidation["Invalidation"]["Id"],
        WaiterConfig={"Delay": 10, "MaxAttempts": 180},
    )
    print(f"Aplicación publicada: {outputs['CloudFrontUrl']}")
    print(
        "Se debe verificar la aplicación y revisar sus registros antes de considerar finalizada la publicación."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("check", "deploy", "update", "database", "status", "delete")
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.local.json")
    parser.add_argument(
        "--confirm",
        help="Solo delete: cuenta/nombre-del-despliegue; confirma eliminación irreversible.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Solo database: insertar datos docentes faltantes, sin sobrescribir registros.",
    )
    args = parser.parse_args()
    if args.seed and args.command != "database":
        parser.error("--seed solo se utiliza con database")
    if args.confirm is not None and args.command != "delete":
        parser.error("--confirm solo se utiliza con delete")
    if sys.version_info[:2] != (3, 14):
        parser.error("Se debe ejecutar este procedimiento con Python 3.14.")
    try:
        run(args)
    except (
        DeploymentError,
        PackageError,
        ClientError,
        WaiterError,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        if isinstance(error, ClientError):
            print(
                f"AWS rechazó la operación ({error.response['Error']['Code']}). Revisar permisos y eventos en la consola.",
                file=sys.stderr,
            )
        elif isinstance(error, WaiterError):
            print(
                "La operación no terminó correctamente o agotó la espera. Revisar el estado en AWS antes de reintentar; no se eliminaron recursos automáticamente.",
                file=sys.stderr,
            )
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
