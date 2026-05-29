from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.shell import run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "routes.json"


def configured_routes() -> list[dict[str, Any]]:
    return read_json(CONFIG_PATH, [])


def save_routes(routes: list[dict[str, Any]]) -> None:
    write_json_secure(CONFIG_PATH, routes)


def system_routes():
    return run(["ip", "route", "show"], timeout=10)


def add_route(route: dict[str, str]):
    routes = configured_routes()
    routes = [item for item in routes if item.get("destination") != route.get("destination")]
    routes.append(route)
    save_routes(routes)
    return apply_route(route)


def delete_route(destination: str):
    routes = [item for item in configured_routes() if item.get("destination") != destination]
    save_routes(routes)
    return run(["ip", "route", "del", destination], timeout=10)


def apply_route(route: dict[str, str]):
    args = ["ip", "route", "replace", route["destination"]]
    if route.get("gateway"):
        args += ["via", route["gateway"]]
    if route.get("interface"):
        args += ["dev", route["interface"]]
    if route.get("metric"):
        args += ["metric", route["metric"]]
    return run(args, timeout=10)


def apply_all():
    results = []
    for route in configured_routes():
        results.append(apply_route(route))
    return results
