"""Network baseline learning for continuous anomaly detection (Phase 40 L4).

Maintains a statistical baseline per domain. Each scan updates the baseline.
New scans are scored against it to detect anomalies: new/missing hosts,
new ports, service changes. Baseline stored as JSON, no external deps.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ScanPort:
    """A port from a scan result."""

    port: int
    protocol: str
    service: str


@dataclass
class ScanHost:
    """A host from a scan result."""

    ip: str
    ports: list[ScanPort] = field(default_factory=list)


@dataclass
class ScanResult:
    """Parsed scan result."""

    domain: str
    hosts: list[ScanHost] = field(default_factory=list)


@dataclass
class Anomaly:
    """A detected anomaly."""

    kind: str  # new_host, new_port, missing_host, service_change
    target: str
    detail: str
    severity: str  # normal, suspect, critical


@dataclass
class AnomalyReport:
    """Report of anomalies for a scan."""

    domain: str
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def score(self) -> int:
        weights = {"normal": 1, "suspect": 5, "critical": 10}
        return sum(weights.get(a.severity, 1) for a in self.anomalies)

    def summary(self) -> str:
        if not self.anomalies:
            return f"Domain {self.domain}: no anomalies (score: 0)"
        lines = [f"Domain {self.domain}: {len(self.anomalies)} "
                 f"anomalies (score: {self.score})"]
        for a in self.anomalies:
            lines.append(f"  [{a.severity}] {a.kind}: {a.detail}")
        return "\n".join(lines)


@dataclass
class PortRecord:
    """Tracks a port's observation history."""

    port: int
    protocol: str
    service: str
    seen_count: int = 0
    last_service: str = ""


@dataclass
class HostRecord:
    """Tracks a host's observation history."""

    ip: str
    seen_count: int = 0
    ports: dict[str, PortRecord] = field(default_factory=dict)

    def add_port(self, port: int, protocol: str, service: str) -> None:
        key = f"{port}/{protocol}"
        if key in self.ports:
            self.ports[key].seen_count += 1
            self.ports[key].last_service = service
        else:
            self.ports[key] = PortRecord(
                port=port, protocol=protocol, service=service,
                seen_count=1, last_service=service,
            )


@dataclass
class DomainBaseline:
    """Statistical baseline for a domain's network state."""

    domain: str
    scan_count: int = 0
    hosts: dict[str, HostRecord] = field(default_factory=dict)

    def update(self, scan: ScanResult) -> None:
        self.scan_count += 1
        for host in scan.hosts:
            if host.ip not in self.hosts:
                self.hosts[host.ip] = HostRecord(ip=host.ip)
            rec = self.hosts[host.ip]
            rec.seen_count += 1
            for p in host.ports:
                rec.add_port(p.port, p.protocol, p.service)

    def score(self, scan: ScanResult) -> AnomalyReport:
        anomalies: list[Anomaly] = []
        if self.scan_count == 0:
            return AnomalyReport(domain=self.domain)
        for host in scan.hosts:
            if host.ip not in self.hosts:
                anomalies.append(Anomaly(
                    "new_host", host.ip,
                    f"Host {host.ip} not in baseline", "suspect"))
                continue
            rec = self.hosts[host.ip]
            for p in host.ports:
                key = f"{p.port}/{p.protocol}"
                if key not in rec.ports:
                    anomalies.append(Anomaly(
                        "new_port", f"{host.ip}:{key}",
                        f"New port {key} ({p.service})", "suspect"))
                elif (rec.ports[key].last_service and p.service
                      and rec.ports[key].last_service != p.service):
                    anomalies.append(Anomaly(
                        "service_change", f"{host.ip}:{key}",
                        f"{rec.ports[key].last_service} -> {p.service}",
                        "normal"))
        threshold = self.scan_count * 0.5
        scan_ips = {h.ip for h in scan.hosts}
        for ip, rec in self.hosts.items():
            if ip not in scan_ips and rec.seen_count > threshold:
                anomalies.append(Anomaly(
                    "missing_host", ip,
                    f"Missing (seen {rec.seen_count}/{self.scan_count})",
                    "suspect"))
        return AnomalyReport(domain=self.domain, anomalies=anomalies)


def save_baseline(baseline: DomainBaseline, path: Path) -> None:
    """Save baseline to JSON file."""
    data = {
        "domain": baseline.domain,
        "scan_count": baseline.scan_count,
        "hosts": {
            ip: {
                "seen_count": h.seen_count,
                "ports": {k: asdict(p) for k, p in h.ports.items()},
            }
            for ip, h in baseline.hosts.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_baseline(path: Path, domain: str) -> DomainBaseline:
    """Load baseline from JSON file, or return empty baseline."""
    if not path.exists():
        return DomainBaseline(domain=domain)
    data = json.loads(path.read_text())
    baseline = DomainBaseline(
        domain=data.get("domain", domain),
        scan_count=data.get("scan_count", 0),
    )
    for ip, hdata in data.get("hosts", {}).items():
        host = HostRecord(ip=ip, seen_count=hdata.get("seen_count", 0))
        for key, pdata in hdata.get("ports", {}).items():
            host.ports[key] = PortRecord(**pdata)
        baseline.hosts[ip] = host
    return baseline
