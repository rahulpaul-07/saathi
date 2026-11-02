"""Public-hosting guards, all off unless SAATHI_PUBLIC=1: proxy-aware client IP, a persisted daily
Gnani call budget and a kill switch. Nothing here runs in local development."""

import ipaddress
import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request

from saathi.gnani import LiveSpeechUnavailable

log = logging.getLogger(__name__)

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
Address = ipaddress.IPv4Address | ipaddress.IPv6Address

REASON_KILL_SWITCH = "kill_switch"
REASON_BUDGET = "budget"


def parse_trusted_proxies(raw: str) -> tuple[Network, ...]:
    """Comma-separated IPs or CIDRs. A bad entry fails startup: a typo must not silently turn
    the proxy trust off (every user would share the proxy's rate-limit bucket) or on."""
    networks = [
        ipaddress.ip_network(item.strip(), strict=False) for item in raw.split(",") if item.strip()
    ]
    return tuple(networks)


def _parse_ip(text: str) -> Address | None:
    try:
        return ipaddress.ip_address(text.strip())
    except ValueError:
        return None


def _is_trusted(address: Address, trusted: tuple[Network, ...]) -> bool:
    return any(address in network for network in trusted)


def client_ip(peer: str | None, forwarded_for: str | None, trusted: tuple[Network, ...]) -> str:
    """The address to rate-limit on.

    X-Forwarded-For is attacker-controlled unless a proxy we run appended to it, so it is read
    only when the immediate socket peer is a trusted proxy. The list is then walked from the right
    (the entries our own proxies added) and the first address that is not itself a trusted proxy
    is the client. Anything unparseable falls back to the peer: a shared bucket is safe, a
    spoofed one is not.
    """
    if peer is None:
        return "unknown"
    peer_ip = _parse_ip(peer)
    if peer_ip is None or not trusted or not _is_trusted(peer_ip, trusted) or not forwarded_for:
        return peer
    for entry in reversed(forwarded_for.split(",")):
        address = _parse_ip(entry)
        if address is None:
            return peer
        if not _is_trusted(address, trusted):
            return str(address)
    return peer


def ip_resolver(trusted: tuple[Network, ...]) -> Callable[[Request], str]:
    def resolve(request: Request) -> str:
        peer = request.client.host if request.client else None
        return client_ip(peer, request.headers.get("x-forwarded-for"), trusted)

    return resolve


class GnaniBudget:
    """Calls allowed per UTC day, persisted so a restart cannot reset it.

    Fail closed: an unreadable counter file or a failed write counts as exhausted, because the
    point of the budget is a ceiling on spend. Every HTTP attempt is counted, retries included.
    """

    def __init__(self, path: Path, daily_limit: int, now: Callable[[], datetime] | None = None):
        self._path = path
        self._limit = daily_limit
        self._now = now or (lambda: datetime.now(UTC))

    def _today(self) -> str:
        return self._now().astimezone(UTC).date().isoformat()

    def _used_today(self) -> int:
        try:
            raw = json.loads(self._path.read_text("utf-8"))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError):
            log.error("Gnani budget file is unreadable; treating today's budget as spent")
            return self._limit
        if not isinstance(raw, dict) or not isinstance(raw.get("used"), int):
            return self._limit
        return raw["used"] if raw.get("day") == self._today() else 0

    def remaining(self) -> int:
        return max(self._limit - self._used_today(), 0)

    def spend(self) -> None:
        used = self._used_today()
        if used >= self._limit:
            raise LiveSpeechUnavailable(REASON_BUDGET)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"day": self._today(), "used": used + 1}), "utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:
            log.error("Gnani budget file is not writable: %s", type(exc).__name__)
            raise LiveSpeechUnavailable(REASON_BUDGET) from exc


class LiveGate:
    """Checked before every Gnani HTTP attempt. The kill file is looked up on each call, so
    creating it stops live calls at once without a restart; the env switch needs a restart."""

    def __init__(self, budget: GnaniBudget, kill_env: bool, kill_file: Path | None):
        self._budget = budget
        self._kill_env = kill_env
        self._kill_file = kill_file

    def killed(self) -> bool:
        return self._kill_env or (self._kill_file is not None and self._kill_file.exists())

    def __call__(self) -> None:
        if self.killed():
            raise LiveSpeechUnavailable(REASON_KILL_SWITCH)
        self._budget.spend()

    def live(self) -> bool:
        return not self.killed() and self._budget.remaining() > 0
