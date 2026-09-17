from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import yaml

SCHEMA_URL = "https://render.com/schema/render.yaml.json"

RESOURCE_KEYS = {"services", "databases", "envVarGroups"}
TOP_LEVEL_KEYS = {
    *RESOURCE_KEYS,
    "previews",
    "previewsEnabled",
    "previewsExpireAfterDays",
    "projects",
    "ungrouped",
    "version",
}
SERVICE_KEYS = {
    "autoDeploy",
    "autoDeployTrigger",
    "branch",
    "buildCommand",
    "buildFilter",
    "disk",
    "dockerCommand",
    "dockerContext",
    "dockerfilePath",
    "domain",
    "domains",
    "envVars",
    "headers",
    "healthCheckPath",
    "image",
    "initialDeployHook",
    "ipAllowList",
    "maintenanceMode",
    "maxShutdownDelaySeconds",
    "maxmemoryPolicy",
    "name",
    "numInstances",
    "persistenceMode",
    "plan",
    "preDeployCommand",
    "previewPlan",
    "previews",
    "pullRequestPreviewsEnabled",
    "region",
    "registryCredential",
    "renderSubdomainPolicy",
    "repo",
    "rootDir",
    "routes",
    "runtime",
    "scaling",
    "schedule",
    "startCommand",
    "staticPublishPath",
    "type",
}
SERVICE_TYPES = {"cron", "keyvalue", "pserv", "redis", "web", "worker", "workflow"}
AUTO_DEPLOY_TRIGGERS = {"checksPass", "commit", "off"}
DATABASE_KEYS = {
    "connectionPool",
    "databaseName",
    "diskSizeGB",
    "highAvailability",
    "ipAllowList",
    "name",
    "plan",
    "postgresMajorVersion",
    "previewDiskSizeGB",
    "previewPlan",
    "readReplicas",
    "region",
    "storageAutoscalingEnabled",
    "user",
}
ENV_VAR_KEYS = {
    "fromDatabase",
    "fromGroup",
    "fromService",
    "generateValue",
    "key",
    "previewValue",
    "sync",
    "value",
}
ENV_VAR_GROUP_KEYS = {"envVars", "name"}
FROM_DATABASE_KEYS = {"name", "property"}
FROM_SERVICE_KEYS = {"envVarKey", "name", "property", "type"}
PROJECT_KEYS = {"environments", "name"}
ENVIRONMENT_KEYS = {*RESOURCE_KEYS, "name", "networking", "permissions"}


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _unknown_key_message(path: str, key: object, allowed: set[str]) -> str:
    rendered_key = str(key)
    match = get_close_matches(rendered_key, allowed, n=1, cutoff=0.72)
    suggestion = f"; did you mean '{match[0]}'?" if match else ""
    return f"{path}.{rendered_key}: unsupported key{suggestion}"


def _check_keys(
    value: Mapping[object, object], allowed: set[str], path: str, errors: list[str]
) -> None:
    for key in value:
        if key not in allowed:
            errors.append(_unknown_key_message(path, key, allowed))


def _require_string(
    value: Mapping[object, object], key: str, path: str, errors: list[str]
) -> None:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        errors.append(f"{path}.{key}: must be a non-empty string")


def _validate_reference(
    value: object,
    *,
    allowed: set[str],
    required: set[str],
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(value, Mapping):
        errors.append(f"{path}: must be a mapping")
        return
    _check_keys(value, allowed, path, errors)
    for key in sorted(required):
        _require_string(value, key, path, errors)


def _validate_env_vars(value: object, path: str, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append(f"{path}: must be a list")
        return

    seen_keys: set[str] = set()
    for index, env_var in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(env_var, Mapping):
            errors.append(f"{item_path}: must be a mapping")
            continue
        _check_keys(env_var, ENV_VAR_KEYS, item_path, errors)

        references = [
            key for key in ("fromDatabase", "fromService", "fromGroup") if key in env_var
        ]
        if len(references) > 1:
            errors.append(
                f"{item_path}: may reference only one of fromDatabase, fromService, or fromGroup"
            )

        if "fromGroup" in env_var:
            if set(env_var) != {"fromGroup"}:
                errors.append(f"{item_path}: fromGroup cannot be combined with other keys")
            _require_string(env_var, "fromGroup", item_path, errors)
            continue

        _require_string(env_var, "key", item_path, errors)
        env_key = env_var.get("key")
        if isinstance(env_key, str) and env_key.strip():
            if env_key in seen_keys:
                errors.append(f"{item_path}.key: duplicate environment variable '{env_key}'")
            seen_keys.add(env_key)

        if "fromDatabase" in env_var:
            if set(env_var) != {"key", "fromDatabase"}:
                errors.append(
                    f"{item_path}: fromDatabase cannot be combined with direct-value keys"
                )
            _validate_reference(
                env_var["fromDatabase"],
                allowed=FROM_DATABASE_KEYS,
                required=FROM_DATABASE_KEYS,
                path=f"{item_path}.fromDatabase",
                errors=errors,
            )
        if "fromService" in env_var:
            if set(env_var) != {"key", "fromService"}:
                errors.append(f"{item_path}: fromService cannot be combined with direct-value keys")
            _validate_reference(
                env_var["fromService"],
                allowed=FROM_SERVICE_KEYS,
                required={"name", "type"},
                path=f"{item_path}.fromService",
                errors=errors,
            )

        for boolean_key in ("generateValue", "sync"):
            if boolean_key in env_var and not isinstance(env_var[boolean_key], bool):
                errors.append(f"{item_path}.{boolean_key}: must be a boolean")


def _validate_services(value: object, path: str, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append(f"{path}: must be a list")
        return

    seen_names: set[str] = set()
    for index, service in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(service, Mapping):
            errors.append(f"{item_path}: must be a mapping")
            continue
        _check_keys(service, SERVICE_KEYS, item_path, errors)
        _require_string(service, "name", item_path, errors)
        _require_string(service, "type", item_path, errors)

        name = service.get("name")
        if isinstance(name, str) and name.strip():
            if name in seen_names:
                errors.append(f"{item_path}.name: duplicate service name '{name}'")
            seen_names.add(name)

        service_type = service.get("type")
        if isinstance(service_type, str) and service_type not in SERVICE_TYPES:
            errors.append(
                f"{item_path}.type: unsupported service type '{service_type}'"
            )
        if service_type in {"web", "worker", "pserv", "cron", "workflow"}:
            _require_string(service, "runtime", item_path, errors)
        if service_type == "cron":
            _require_string(service, "schedule", item_path, errors)
        if service_type == "workflow":
            _require_string(service, "region", item_path, errors)
            _require_string(service, "startCommand", item_path, errors)
        if service_type in {"keyvalue", "redis"} and "ipAllowList" not in service:
            errors.append(f"{item_path}.ipAllowList: required for key-value services")

        auto_deploy_trigger = service.get("autoDeployTrigger")
        if (
            auto_deploy_trigger is not None
            and (
                not isinstance(auto_deploy_trigger, str)
                or auto_deploy_trigger not in AUTO_DEPLOY_TRIGGERS
            )
        ):
            errors.append(
                f"{item_path}.autoDeployTrigger: unsupported value "
                f"'{auto_deploy_trigger}'"
            )

        if "envVars" in service:
            _validate_env_vars(service["envVars"], f"{item_path}.envVars", errors)


def _validate_databases(value: object, path: str, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append(f"{path}: must be a list")
        return

    seen_names: set[str] = set()
    for index, database in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(database, Mapping):
            errors.append(f"{item_path}: must be a mapping")
            continue
        _check_keys(database, DATABASE_KEYS, item_path, errors)
        _require_string(database, "name", item_path, errors)
        name = database.get("name")
        if isinstance(name, str) and name.strip():
            if name in seen_names:
                errors.append(f"{item_path}.name: duplicate database name '{name}'")
            seen_names.add(name)

        if "readReplicas" in database:
            replicas = database["readReplicas"]
            if not _is_sequence(replicas):
                errors.append(f"{item_path}.readReplicas: must be a list")
            else:
                for replica_index, replica in enumerate(replicas):
                    replica_path = f"{item_path}.readReplicas[{replica_index}]"
                    if not isinstance(replica, Mapping):
                        errors.append(f"{replica_path}: must be a mapping")
                        continue
                    _check_keys(replica, {"name"}, replica_path, errors)
                    _require_string(replica, "name", replica_path, errors)


def _validate_env_var_groups(value: object, path: str, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append(f"{path}: must be a list")
        return

    seen_names: set[str] = set()
    for index, group in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(group, Mapping):
            errors.append(f"{item_path}: must be a mapping")
            continue
        _check_keys(group, ENV_VAR_GROUP_KEYS, item_path, errors)
        _require_string(group, "name", item_path, errors)
        name = group.get("name")
        if isinstance(name, str) and name.strip():
            if name in seen_names:
                errors.append(f"{item_path}.name: duplicate environment group name '{name}'")
            seen_names.add(name)
        if "envVars" not in group:
            errors.append(f"{item_path}.envVars: required")
        else:
            _validate_env_vars(group["envVars"], f"{item_path}.envVars", errors)


def _validate_resources(value: Mapping[object, object], path: str, errors: list[str]) -> None:
    if "services" in value:
        _validate_services(value["services"], f"{path}.services", errors)
    if "databases" in value:
        _validate_databases(value["databases"], f"{path}.databases", errors)
    if "envVarGroups" in value:
        _validate_env_var_groups(value["envVarGroups"], f"{path}.envVarGroups", errors)


def _validate_projects(value: object, path: str, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append(f"{path}: must be a list")
        return
    for project_index, project in enumerate(value):
        project_path = f"{path}[{project_index}]"
        if not isinstance(project, Mapping):
            errors.append(f"{project_path}: must be a mapping")
            continue
        _check_keys(project, PROJECT_KEYS, project_path, errors)
        _require_string(project, "name", project_path, errors)
        environments = project.get("environments")
        if not _is_sequence(environments):
            errors.append(f"{project_path}.environments: must be a list")
            continue
        for environment_index, environment in enumerate(environments):
            environment_path = f"{project_path}.environments[{environment_index}]"
            if not isinstance(environment, Mapping):
                errors.append(f"{environment_path}: must be a mapping")
                continue
            _check_keys(environment, ENVIRONMENT_KEYS, environment_path, errors)
            _require_string(environment, "name", environment_path, errors)
            _validate_resources(environment, environment_path, errors)


def validate_blueprint(blueprint: object) -> list[str]:
    """Return deterministic, offline structural errors for a Render Blueprint."""
    errors: list[str] = []
    if not isinstance(blueprint, Mapping):
        return ["<root>: must be a mapping"]

    _check_keys(blueprint, TOP_LEVEL_KEYS, "<root>", errors)
    _validate_resources(blueprint, "<root>", errors)

    if "ungrouped" in blueprint:
        ungrouped = blueprint["ungrouped"]
        if not isinstance(ungrouped, Mapping):
            errors.append("<root>.ungrouped: must be a mapping")
        else:
            _check_keys(ungrouped, RESOURCE_KEYS, "<root>.ungrouped", errors)
            _validate_resources(ungrouped, "<root>.ungrouped", errors)
    if "projects" in blueprint:
        _validate_projects(blueprint["projects"], "<root>.projects", errors)
    if "version" in blueprint and blueprint["version"] != "1":
        errors.append("<root>.version: must be the string '1'")

    return sorted(errors)


def _load_official_schema() -> dict[str, Any]:
    with urllib.request.urlopen(SCHEMA_URL, timeout=20) as response:  # noqa: S310
        schema: dict[str, Any] = json.load(response)
    return schema


def _official_errors(blueprint: object) -> list[str]:
    try:
        from jsonschema.validators import validator_for
    except ImportError as exc:  # pragma: no cover - depends on the caller's environment
        raise RuntimeError("--official requires the 'jsonschema' package") from exc

    schema = _load_official_schema()
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)
    errors = sorted(
        validator.iter_errors(blueprint),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    rendered: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        rendered.append(f"{location}: {error.message}")
    return rendered


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint", nargs="?", default="render.yaml", type=Path)
    parser.add_argument(
        "--official",
        action="store_true",
        help="also compare with Render's live published schema (requires network access)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        with args.blueprint.open(encoding="utf-8") as handle:
            blueprint = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        print(f"{args.blueprint}: unable to load Blueprint: {exc}", file=sys.stderr)
        return 2

    local_errors = validate_blueprint(blueprint)
    if local_errors:
        for error in local_errors:
            print(f"{args.blueprint}:{error}", file=sys.stderr)
        return 1
    print(f"{args.blueprint} passed local Render Blueprint structure validation.")

    if not args.official:
        return 0

    try:
        official_errors = _official_errors(blueprint)
    except Exception as exc:  # noqa: BLE001 - advisory dependency/network diagnostics
        print(f"Official Render schema comparison could not run: {exc}", file=sys.stderr)
        return 2
    if official_errors:
        for error in official_errors:
            print(f"{args.blueprint}:{error}", file=sys.stderr)
        return 1
    print(f"{args.blueprint} also passed Render's published schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
