# Matrix: LS-001, LS-002, NI-3-002, NI-3-003
Feature: AI Sanitization and Network Baseline

  Scenario: NER sanitizer detects infrastructure hosts
    # Matrix: LS-001
    Given "python3" is available
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from ner_sanitizer import HeuristicBackend, NerSanitizer; s=NerSanitizer(backend=HeuristicBackend()); r,e=s.sanitize("connecting to pro-dev on port 22"); assert "pro-dev" not in r; assert "REDACTED" in r; print("ner ok")'"
    Then exit code is 0
    And output contains "ner ok"

  Scenario: NER sanitizer ignores common English words
    # Matrix: LS-002
    Given "python3" is available
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from ner_sanitizer import HeuristicBackend; b=HeuristicBackend(); entities=b.detect("this is a read-only built-in feature"); names=[e.text.lower() for e in entities]; assert "read-only" not in names; assert "built-in" not in names; print("common words ok")'"
    Then exit code is 0
    And output contains "common words ok"

  Scenario: Network baseline detects new host anomaly
    # Matrix: NI-3-002
    Given "python3" is available
    When I run "python3 -c 'import sys; sys.path.insert(0,"scripts"); from network_baseline import *; bl=DomainBaseline(domain="pro"); bl.update(ScanResult(domain="pro",hosts=[ScanHost(ip="10.110.1.1")])); r=bl.score(ScanResult(domain="pro",hosts=[ScanHost(ip="10.110.1.1"),ScanHost(ip="10.110.1.99")])); kinds=[a.kind for a in r.anomalies]; assert "new_host" in kinds; print("baseline ok")'"
    Then exit code is 0
    And output contains "baseline ok"

  Scenario: Network baseline persistence roundtrip
    # Matrix: NI-3-003
    Given "python3" is available
    When I run "python3 -c 'import sys,tempfile; sys.path.insert(0,"scripts"); from pathlib import Path; from network_baseline import *; bl=DomainBaseline(domain="pro"); bl.update(ScanResult(domain="pro",hosts=[ScanHost(ip="10.110.1.1",ports=[ScanPort(22,"tcp","ssh")])])); p=Path(tempfile.mktemp(suffix=".json")); save_baseline(bl,p); loaded=load_baseline(p,"pro"); assert loaded.scan_count==1; assert "10.110.1.1" in loaded.hosts; p.unlink(); print("roundtrip ok")'"
    Then exit code is 0
    And output contains "roundtrip ok"
