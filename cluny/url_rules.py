"""Configurable rules for which URLs Cluny may fetch."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from cluny.extract import ExtractionError


def _parse_host_rules(raw: str) -> frozenset[str]:
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def _host_matches_rule(host: str, rule: str) -> bool:
    host = host.lower().rstrip(".")
    rule = rule.lower().strip()
    if not rule:
        return False
    if rule.startswith("*."):
        base = rule[2:]
        return host == base or host.endswith("." + base)
    return host == rule or host.endswith("." + rule)


@dataclass(frozen=True)
class UrlRules:
    """open = allow by default (blocklist only). restricted = allowlist only."""

    mode: str  # "open" | "restricted"
    allow_hosts: frozenset[str]
    block_hosts: frozenset[str]

    def check(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ExtractionError(f"Only http(s) URLs are allowed, got {parsed.scheme!r}")

        host = parsed.hostname
        if not host:
            raise ExtractionError("URL has no hostname")

        # Optional block numeric LAN ranges if desired later — skip for now

        for blocked in self.block_hosts:
            if _host_matches_rule(host, blocked):
                raise ExtractionError(f"Host {host!r} is blocked by CLUNY_URL_BLOCKLIST")

        if self.mode == "restricted":
            if not self.allow_hosts:
                raise ExtractionError(
                    "CLUNY_URL_MODE=restricted requires a non-empty CLUNY_URL_ALLOWLIST"
                )
            if not any(_host_matches_rule(host, a) for a in self.allow_hosts):
                raise ExtractionError(
                    f"Host {host!r} is not allowed by CLUNY_URL_ALLOWLIST (restricted mode)"
                )


def host_from_url(url: str) -> str:
    h = urlparse(url).hostname
    return h or ""
