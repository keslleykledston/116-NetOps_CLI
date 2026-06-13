from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.services import diagnostics
from app.services.ssh_policy import SecurityPolicyError, validate_ssh_command


def _duration_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def _validate_oid(oid: str) -> None:
    if not oid or not all(part.isdigit() for part in oid.strip().split(".")):
        raise ValueError("Invalid SNMP OID")


def _ssh_remote_command(command: str, vendor: str | None) -> str:
    trimmed = command.strip()
    lower = trimmed.lower()
    vendor_lower = (vendor or "").lower()
    if "huawei" in vendor_lower and (lower.startswith("display ") or lower.startswith("show ")):
        if not lower.startswith("screen-length") and not lower.startswith("terminal length"):
            return f"screen-length 0 temporary\n{trimmed}"
    return trimmed


def _ssh_command_timeout(command: str) -> int:
    lower = command.lower()
    if "current-configuration" in lower:
        return min(180, settings.ssh_command_timeout + settings.ssh_connect_timeout)
    return min(90, settings.ssh_command_timeout + settings.ssh_connect_timeout)


def _run_ssh_command(
    *,
    target_ip: str,
    port: int,
    username: str,
    password: str,
    command: str,
    vendor: str,
) -> dict[str, Any]:
    from app.services.shell import run

    remote_command = _ssh_remote_command(command, vendor)
    ssh_timeout = _ssh_command_timeout(command)
    result = run(
        [
            "timeout",
            str(ssh_timeout),
            "sshpass",
            "-p",
            password,
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"ConnectTimeout={settings.ssh_connect_timeout}",
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(port),
            f"{username}@{target_ip}",
            remote_command,
        ],
        timeout=ssh_timeout + 5,
        sensitive_values=[password] if password else None,
    )
    return {
        "ok": result.ok,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    job_type = str(job.get("job_type", "")).upper()
    target_ip = str(job.get("target_ip") or "").strip()
    target_port = job.get("target_port")
    payload = job.get("payload_json") or {}
    if not isinstance(payload, dict):
        payload = {}

    if not target_ip and isinstance(payload.get("target_ip"), str):
        target_ip = payload["target_ip"].strip()

    try:
        if job_type == "PING":
            count = int(payload.get("count", 4))
            result = diagnostics.ping(target_ip, count)
            return {
                "success": result.ok,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "result_json": {"executor": "netops-cli", "duration_ms": _duration_ms(time.time())},
            }

        if job_type == "TRACEROUTE":
            result = diagnostics.traceroute(target_ip)
            return {
                "success": result.ok,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "result_json": {"executor": "netops-cli"},
            }

        if job_type == "TCP_CHECK":
            port = int(target_port or payload.get("port") or payload.get("target_port") or 22)
            check = diagnostics.tcp_check(target_ip, port, timeout=settings.ssh_connect_timeout)
            return {
                "success": bool(check.get("ok")),
                "stdout": str(check.get("message", "")),
                "stderr": "" if check.get("ok") else str(check.get("message", "")),
                "exit_code": 0 if check.get("ok") else 1,
                "result_json": {"executor": "netops-cli", "open": bool(check.get("ok"))},
            }

        if job_type == "ROUTE_CHECK":
            from app.services.shell import run

            result = run(["ip", "route", "get", target_ip], timeout=settings.job_timeout_seconds)
            return {
                "success": result.ok,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "result_json": {"executor": "netops-cli"},
            }

        if job_type == "SNMP_GET":
            oid = str(payload.get("oid", "")).strip()
            _validate_oid(oid)
            community = str(payload.get("community", "public"))
            from app.services.shell import run

            result = run(
                ["snmpget", "-v2c", "-c", community, target_ip, oid],
                timeout=settings.job_timeout_seconds,
                sensitive_values=[community],
            )
            return {
                "success": result.ok,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "result_json": {"executor": "netops-cli"},
            }

        if job_type == "SNMP_WALK":
            oid = str(payload.get("oid", "")).strip()
            _validate_oid(oid)
            community = str(payload.get("community", "public"))
            result = diagnostics.snmpwalk(target_ip, community, oid)
            lines = result.stdout.splitlines()
            truncated = len(lines) > settings.snmp_max_lines
            stdout = "\n".join(lines[: settings.snmp_max_lines])
            if truncated:
                stdout += f"\n... truncated ({len(lines)} lines)"
            return {
                "success": result.ok,
                "stdout": stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "result_json": {"executor": "netops-cli", "truncated": truncated, "line_count": len(lines)},
            }

        if job_type == "SSH_COMMAND":
            command = str(payload.get("command", "")).strip()
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            port = int(payload.get("port") or target_port or 22)
            vendor = str(payload.get("vendor", "") or "")
            validate_ssh_command(command)
            if not username:
                raise ValueError("SSH payload requires username")

            start = time.time()
            ssh_result = _run_ssh_command(
                target_ip=target_ip,
                port=port,
                username=username,
                password=password,
                command=command,
                vendor=vendor,
            )
            huawei_version_ok = (
                "huawei" in vendor.lower()
                and command.lower().startswith("display version")
                and "vrp" in ssh_result["stdout"].lower()
            )
            success = ssh_result["ok"] or huawei_version_ok
            return {
                "success": success,
                "stdout": ssh_result["stdout"],
                "stderr": ssh_result["stderr"],
                "exit_code": 0 if success else ssh_result["returncode"],
                "result_json": {"executor": "netops-cli", "duration_ms": _duration_ms(start)},
            }

        if job_type == "SSH_CONFIG_BUNDLE":
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            port = int(payload.get("port") or target_port or 22)
            vendor = str(payload.get("vendor", "") or "")
            commands_raw = payload.get("commands")
            if not username:
                raise ValueError("SSH_CONFIG_BUNDLE requires username")
            if not isinstance(commands_raw, list) or not commands_raw:
                raise ValueError("SSH_CONFIG_BUNDLE requires commands[]")

            commands = [str(item).strip() for item in commands_raw if str(item).strip()]
            for command in commands:
                validate_ssh_command(command)

            start = time.time()
            sections: list[str] = []
            errors: list[str] = []
            command_stats: list[dict[str, Any]] = []
            for command in commands:
                cmd_start = time.time()
                ssh_result = _run_ssh_command(
                    target_ip=target_ip,
                    port=port,
                    username=username,
                    password=password,
                    command=command,
                    vendor=vendor,
                )
                body = ssh_result["stdout"] or ssh_result["stderr"]
                sections.append(f"! === {command} ===\n{body}".strip())
                command_stats.append(
                    {
                        "command": command,
                        "success": ssh_result["ok"],
                        "duration_ms": _duration_ms(cmd_start),
                    }
                )
                if not ssh_result["ok"]:
                    errors.append(f"{command}: {ssh_result['stderr'] or 'failed'}")

            raw_bundle = "\n\n".join(sections)
            has_running_config = any(
                cmd.lower().startswith("display current-configuration") or cmd.lower().startswith("show running")
                for cmd in commands
            )
            config_section_ok = False
            if has_running_config:
                for section in sections:
                    if "current-configuration" in section.lower() or "running-config" in section.lower():
                        if len(section) > 200:
                            config_section_ok = True
                            break
            else:
                config_section_ok = bool(raw_bundle.strip())

            success = config_section_ok and len(raw_bundle.strip()) > 0
            return {
                "success": success,
                "stdout": raw_bundle,
                "stderr": "\n".join(errors) if errors else "",
                "exit_code": 0 if success else 1,
                "result_json": {
                    "executor": "netops-cli",
                    "duration_ms": _duration_ms(start),
                    "command_count": len(commands),
                    "commands": command_stats,
                },
            }

        if job_type == "WG_STATUS":
            from app.services import wireguard

            wg = wireguard.stats()
            active = bool(wg.get("interfaces"))
            return {
                "success": True,
                "stdout": str(wg),
                "stderr": "",
                "exit_code": 0,
                "result_json": {"executor": "netops-cli", "wireguard_status": "UP" if active else "DOWN"},
            }

        raise ValueError(f"Unsupported job_type: {job_type}")
    except SecurityPolicyError as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": exc.exit_code,
            "result_json": {"executor": "netops-cli", "blocked": True},
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": 1,
            "result_json": {"executor": "netops-cli", "error": type(exc).__name__},
        }
