"""Tests for network baseline learning module (Phase 40 Level 4)."""

from network_baseline import (
    Anomaly,
    AnomalyReport,
    DomainBaseline,
    HostRecord,
    ScanHost,
    ScanPort,
    ScanResult,
    load_baseline,
    save_baseline,
)


class TestScanDataclasses:
    def test_scan_port_fields(self):
        p = ScanPort(port=22, protocol="tcp", service="ssh")
        assert p.port == 22
        assert p.protocol == "tcp"
        assert p.service == "ssh"

    def test_scan_host_with_ports(self):
        h = ScanHost(ip="10.120.1.1", ports=[
            ScanPort(22, "tcp", "ssh"),
            ScanPort(80, "tcp", "http"),
        ])
        assert len(h.ports) == 2

    def test_scan_result(self):
        s = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.120.1.1"),
        ])
        assert s.domain == "pro"
        assert len(s.hosts) == 1


class TestAnomalyReport:
    def test_empty_report(self):
        r = AnomalyReport(domain="pro")
        assert r.score == 0
        assert "no anomalies" in r.summary()

    def test_score_calculation(self):
        r = AnomalyReport(domain="pro", anomalies=[
            Anomaly("new_host", "10.1.1.1", "new", "suspect"),
            Anomaly("service_change", "10.1.1.2:80/tcp", "changed", "normal"),
        ])
        assert r.score == 6  # 5 (suspect) + 1 (normal)

    def test_summary_format(self):
        r = AnomalyReport(domain="pro", anomalies=[
            Anomaly("new_host", "10.1.1.1", "Host new", "suspect"),
        ])
        summary = r.summary()
        assert "1 anomalies" in summary
        assert "[suspect]" in summary


class TestHostRecord:
    def test_add_new_port(self):
        h = HostRecord(ip="10.1.1.1")
        h.add_port(22, "tcp", "ssh")
        assert "22/tcp" in h.ports
        assert h.ports["22/tcp"].seen_count == 1

    def test_add_existing_port(self):
        h = HostRecord(ip="10.1.1.1")
        h.add_port(22, "tcp", "ssh")
        h.add_port(22, "tcp", "ssh")
        assert h.ports["22/tcp"].seen_count == 2

    def test_service_update(self):
        h = HostRecord(ip="10.1.1.1")
        h.add_port(80, "tcp", "http")
        h.add_port(80, "tcp", "nginx")
        assert h.ports["80/tcp"].last_service == "nginx"


class TestDomainBaseline:
    def test_update_new_host(self):
        bl = DomainBaseline(domain="pro")
        scan = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(22, "tcp", "ssh")]),
        ])
        bl.update(scan)
        assert bl.scan_count == 1
        assert "10.1.1.1" in bl.hosts

    def test_update_increments_counts(self):
        bl = DomainBaseline(domain="pro")
        scan = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(22, "tcp", "ssh")]),
        ])
        bl.update(scan)
        bl.update(scan)
        assert bl.scan_count == 2
        assert bl.hosts["10.1.1.1"].seen_count == 2
        assert bl.hosts["10.1.1.1"].ports["22/tcp"].seen_count == 2

    def test_score_empty_baseline(self):
        bl = DomainBaseline(domain="pro")
        scan = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1"),
        ])
        report = bl.score(scan)
        assert len(report.anomalies) == 0

    def test_score_new_host(self):
        bl = DomainBaseline(domain="pro")
        bl.update(ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1"),
        ]))
        scan2 = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1"),
            ScanHost(ip="10.1.1.99"),
        ])
        report = bl.score(scan2)
        kinds = [a.kind for a in report.anomalies]
        assert "new_host" in kinds

    def test_score_new_port(self):
        bl = DomainBaseline(domain="pro")
        bl.update(ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(22, "tcp", "ssh")]),
        ]))
        scan2 = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[
                ScanPort(22, "tcp", "ssh"),
                ScanPort(8080, "tcp", "http"),
            ]),
        ])
        report = bl.score(scan2)
        kinds = [a.kind for a in report.anomalies]
        assert "new_port" in kinds

    def test_score_missing_host(self):
        bl = DomainBaseline(domain="pro")
        full_scan = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1"),
            ScanHost(ip="10.1.1.2"),
        ])
        bl.update(full_scan)
        bl.update(full_scan)
        bl.update(full_scan)
        partial = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1"),
        ])
        report = bl.score(partial)
        kinds = [a.kind for a in report.anomalies]
        assert "missing_host" in kinds

    def test_score_service_change(self):
        bl = DomainBaseline(domain="pro")
        bl.update(ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(80, "tcp", "apache")]),
        ]))
        scan2 = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(80, "tcp", "nginx")]),
        ])
        report = bl.score(scan2)
        kinds = [a.kind for a in report.anomalies]
        assert "service_change" in kinds

    def test_score_no_anomalies(self):
        bl = DomainBaseline(domain="pro")
        scan = ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(22, "tcp", "ssh")]),
        ])
        bl.update(scan)
        report = bl.score(scan)
        assert len(report.anomalies) == 0


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        bl = DomainBaseline(domain="pro")
        bl.update(ScanResult(domain="pro", hosts=[
            ScanHost(ip="10.1.1.1", ports=[ScanPort(22, "tcp", "ssh")]),
        ]))
        path = tmp_path / "baseline.json"
        save_baseline(bl, path)
        assert path.exists()
        loaded = load_baseline(path, "pro")
        assert loaded.domain == "pro"
        assert loaded.scan_count == 1
        assert "10.1.1.1" in loaded.hosts
        assert "22/tcp" in loaded.hosts["10.1.1.1"].ports

    def test_load_nonexistent(self, tmp_path):
        path = tmp_path / "missing.json"
        loaded = load_baseline(path, "pro")
        assert loaded.domain == "pro"
        assert loaded.scan_count == 0

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "baseline.json"
        bl = DomainBaseline(domain="test")
        save_baseline(bl, path)
        assert path.exists()

    def test_roundtrip_preserves_data(self, tmp_path):
        bl = DomainBaseline(domain="pro")
        for _i in range(5):
            bl.update(ScanResult(domain="pro", hosts=[
                ScanHost(ip="10.1.1.1", ports=[
                    ScanPort(22, "tcp", "ssh"),
                    ScanPort(80, "tcp", "http"),
                ]),
                ScanHost(ip="10.1.1.2", ports=[
                    ScanPort(443, "tcp", "https"),
                ]),
            ]))
        path = tmp_path / "bl.json"
        save_baseline(bl, path)
        loaded = load_baseline(path, "pro")
        assert loaded.scan_count == 5
        assert loaded.hosts["10.1.1.1"].seen_count == 5
        assert loaded.hosts["10.1.1.1"].ports["22/tcp"].seen_count == 5
        assert loaded.hosts["10.1.1.2"].ports["443/tcp"].service == "https"
