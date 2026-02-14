"""Tests for scripts/import-infra.sh — reverse-generate infra.yml from Incus."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

IMPORT_SH = Path(__file__).resolve().parent.parent / "scripts" / "import-infra.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment for import-infra testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Mock incus with 2 projects (admin, work) and instances
    # Build JSON responses in separate files to avoid long lines
    proj_json = tmp_path / "proj.json"
    proj_json.write_text(
        '[{"name":"default"},{"name":"admin"},{"name":"work"}]',
    )
    admin_json = tmp_path / "admin.json"
    admin_json.write_text(
        '[{"name":"admin-ctrl","type":"container",'
        '"state":{"network":{"eth0":{"addresses":'
        '[{"family":"inet","address":"10.100.0.10"}]}}}}]',
    )
    work_json = tmp_path / "work.json"
    work_json.write_text(
        '[{"name":"work-dev","type":"container",'
        '"state":{"network":{"eth0":{"addresses":'
        '[{"family":"inet","address":"10.100.1.10"}]}}}},'
        '{"name":"work-vm","type":"virtual-machine",'
        '"state":{"network":{"enp5s0":{"addresses":'
        '[{"family":"inet","address":"10.100.1.20"}]}}}}]',
    )
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"

# project list --format json
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi

# list instances --project admin --format json
if [[ "$1" == "list" && "$*" == *"--project admin"* && "$*" == *"--format json"* ]]; then
    cat "{admin_json}"
    exit 0
fi

# list instances --project work --format json
if [[ "$1" == "list" && "$*" == *"--project work"* && "$*" == *"--format json"* ]]; then
    cat "{work_json}"
    exit 0
fi

exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path


def run_import(args, env, cwd=None):
    """Run import-infra.sh with given args."""
    result = subprocess.run(
        ["bash", str(IMPORT_SH)] + args,
        capture_output=True, text=True, env=env, cwd=cwd, timeout=15,
    )
    return result


class TestImportArgs:
    def test_help_flag(self, mock_env):
        """--help shows usage."""
        env, _, _ = mock_env
        result = run_import(["--help"], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_default_output(self, mock_env):
        """Default output is infra.imported.yml."""
        env, _, cwd = mock_env
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0
        assert (cwd / "infra.imported.yml").exists()

    def test_custom_output(self, mock_env):
        """-o flag changes output file."""
        env, _, cwd = mock_env
        result = run_import(["-o", "custom.yml"], env, cwd=cwd)
        assert result.returncode == 0
        assert (cwd / "custom.yml").exists()


class TestImportContent:
    def test_generates_valid_yaml(self, mock_env):
        """Import generates valid YAML."""
        import yaml
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        output = cwd / "infra.imported.yml"
        content = output.read_text()
        # Remove the header comment block
        yaml_content = "\n".join(
            line for line in content.splitlines()
            if not line.startswith("#") and not line.startswith("WARNING")
        )
        data = yaml.safe_load(yaml_content)
        assert data is not None
        assert "project_name" in data
        assert "domains" in data

    def test_imports_projects_as_domains(self, mock_env):
        """Non-default projects become domains."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        assert "admin:" in content
        assert "work:" in content
        # default project should not appear as a domain
        assert "  default:" not in content

    def test_imports_instances_with_types(self, mock_env):
        """Instances are imported with correct types (lxc/vm)."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        assert "admin-ctrl:" in content
        assert "work-dev:" in content
        assert "work-vm:" in content
        # Check types
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "work-vm:" in line:
                # Next few lines should have type: vm
                block = "\n".join(lines[i:i + 5])
                assert "type: vm" in block

    def test_imports_ip_addresses(self, mock_env):
        """Instance IPs are captured."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        assert "10.100.0.10" in content
        assert "10.100.1.10" in content
        assert "10.100.1.20" in content

    def test_subnet_ids_incremented(self, mock_env):
        """Each domain gets an incrementing subnet_id."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        assert "subnet_id: 0" in content
        assert "subnet_id: 1" in content


class TestImportNoIncus:
    def test_no_incus_fails(self, tmp_path):
        """Import fails when Incus is not accessible."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr


class TestImportEmpty:
    def test_empty_incus(self, tmp_path):
        """Import handles empty Incus (only default project)."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{"name":"default"}]'
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        # Should create file but with no domains
        assert result.returncode == 0
        output = tmp_path / "infra.imported.yml"
        assert output.exists()


# ── instance with no network info ───────────────────────


class TestImportInstanceNoNetwork:
    """Test importing an instance that has empty/null network info."""

    def test_instance_no_network_gets_no_ip(self, tmp_path):
        """Instance with null network state is imported without an IP."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"nonet"}]')

        nonet_json = tmp_path / "nonet.json"
        nonet_json.write_text(
            '[{"name":"nonet-box","type":"container",'
            '"state":{"network":null}}]',
        )

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project nonet"* && "$*" == *"--format json"* ]]; then
    cat "{nonet_json}"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        assert "nonet-box:" in content
        # No ip: line should be present for this instance
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "nonet-box:" in line:
                block = "\n".join(lines[i:i + 5])
                assert "ip:" not in block
                break

    def test_instance_empty_network_dict(self, tmp_path):
        """Instance with empty network dict is imported without an IP."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"emptynet"}]')

        emptynet_json = tmp_path / "emptynet.json"
        emptynet_json.write_text(
            '[{"name":"emptynet-box","type":"container",'
            '"state":{"network":{}}}]',
        )

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project emptynet"* && "$*" == *"--format json"* ]]; then
    cat "{emptynet_json}"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        assert "emptynet-box:" in content


# ── instance with no type field ─────────────────────────


class TestImportInstanceNoType:
    """Test importing an instance that has no 'type' field (should default to container)."""

    def test_instance_no_type_defaults_to_lxc(self, tmp_path):
        """Instance without type field defaults to lxc."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"notype"}]')

        notype_json = tmp_path / "notype.json"
        notype_json.write_text(
            '[{"name":"notype-box",'
            '"state":{"network":{"eth0":{"addresses":'
            '[{"family":"inet","address":"10.100.5.10"}]}}}}]',
        )

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project notype"* && "$*" == *"--format json"* ]]; then
    cat "{notype_json}"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        assert "notype-box:" in content
        # Should default to lxc (not vm)
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "notype-box:" in line:
                block = "\n".join(lines[i:i + 5])
                assert "type: lxc" in block
                break


# ── project with zero instances ─────────────────────────


class TestImportEmptyProject:
    """Test importing a project that exists but has zero instances."""

    def test_empty_project_skipped(self, tmp_path):
        """Project with no instances produces no domain entry."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"empty-proj"}]')

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project empty-proj"* && "$*" == *"--format json"* ]]; then
    echo '[]'
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        # The project should not appear as a domain since it has no instances
        assert "empty-proj:" not in content

    def test_empty_project_does_not_crash(self, tmp_path):
        """Project returning null instances list does not crash the script."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"null-proj"}]')

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project null-proj"* && "$*" == *"--format json"* ]]; then
    echo 'null'
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0


# ── IPv6 addresses are ignored ─────────────────────────


class TestImportIPv6Filtering:
    """Test that IPv6 addresses are filtered out and only IPv4 is captured."""

    def test_ipv6_only_instance_has_no_ip(self, tmp_path):
        """Instance with only IPv6 addresses is imported without an IP."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"v6only"}]')

        v6_json = tmp_path / "v6.json"
        v6_json.write_text(
            '[{"name":"v6-box","type":"container",'
            '"state":{"network":{"eth0":{"addresses":'
            '[{"family":"inet6","address":"fd42::10"}]}}}}]',
        )

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project v6only"* && "$*" == *"--format json"* ]]; then
    cat "{v6_json}"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        assert "v6-box:" in content
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "v6-box:" in line:
                block = "\n".join(lines[i:i + 5])
                assert "ip:" not in block
                break


class TestImportMultipleInterfaces:
    """Test that import picks the first non-lo IPv4 address."""

    def test_multi_nic_picks_first_ipv4(self, tmp_path):
        """Instance with multiple NICs picks the first non-lo IPv4."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        proj_json = tmp_path / "proj.json"
        proj_json.write_text('[{"name":"default"},{"name":"multi"}]')

        multi_json = tmp_path / "multi.json"
        multi_json.write_text(
            '[{"name":"multi-nic","type":"container",'
            '"state":{"network":{'
            '"lo":{"addresses":[{"family":"inet","address":"127.0.0.1"}]},'
            '"eth0":{"addresses":[{"family":"inet","address":"10.100.5.10"}]},'
            '"eth1":{"addresses":[{"family":"inet","address":"10.100.6.20"}]}'
            '}}}]',
        )

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    cat "{proj_json}"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--project multi"* && "$*" == *"--format json"* ]]; then
    cat "{multi_json}"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_import([], env, cwd=tmp_path)
        assert result.returncode == 0

        content = (tmp_path / "infra.imported.yml").read_text()
        assert "10.100.5.10" in content
        assert "127.0.0.1" not in content


class TestImportOutputFileOverwrite:
    """Test import output file behavior."""

    def test_overwrites_existing_output(self, mock_env):
        """Import overwrites existing output file."""
        env, _, cwd = mock_env
        output = cwd / "infra.imported.yml"
        output.write_text("# old content\n")
        run_import([], env, cwd=cwd)
        content = output.read_text()
        assert "# old content" not in content
        assert "project_name" in content

    def test_output_starts_with_header_comment(self, mock_env):
        """Import output starts with informative header comments."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        assert content.startswith("#")
        assert "WARNING" in content or "Review" in content


# ── Helper for building custom mock environments ────────


def _build_mock_env(tmp_path, projects_json, instance_map):
    """Build a custom mock environment.

    Args:
        tmp_path: pytest tmp_path fixture value
        projects_json: JSON string for project list response
        instance_map: dict mapping project name -> JSON string for instances

    Returns:
        (env, tmp_path) tuple
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    proj_json = tmp_path / "proj.json"
    proj_json.write_text(projects_json)

    # Write instance JSON files
    json_files = {}
    for proj_name, inst_json in instance_map.items():
        f = tmp_path / f"{proj_name}.json"
        f.write_text(inst_json)
        json_files[proj_name] = f

    # Build incus mock script
    script_parts = [
        '#!/usr/bin/env bash',
        'if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then',
        f'    cat "{proj_json}"',
        '    exit 0',
        'fi',
    ]
    for proj_name, json_file in json_files.items():
        script_parts.extend([
            f'if [[ "$1" == "list" && "$*" == *"--project {proj_name}"*'
            f' && "$*" == *"--format json"* ]]; then',
            f'    cat "{json_file}"',
            '    exit 0',
            'fi',
        ])
    script_parts.append('exit 0')

    mock_incus = mock_bin / "incus"
    mock_incus.write_text("\n".join(script_parts) + "\n")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, tmp_path


def _load_output_yaml(cwd):
    """Load import output as YAML, filtering comments and WARNING lines."""
    import yaml

    content = (cwd / "infra.imported.yml").read_text()
    yaml_content = "\n".join(
        line for line in content.splitlines()
        if not line.startswith("#") and not line.startswith("WARNING")
    )
    return yaml.safe_load(yaml_content)


def _make_instance_json(name, itype="container", ip=None):
    """Build a single instance JSON dict as a string-friendly dict."""
    inst = {"name": name, "type": itype}
    if ip:
        inst["state"] = {
            "network": {
                "eth0": {
                    "addresses": [{"family": "inet", "address": ip}],
                },
            },
        }
    else:
        inst["state"] = {"network": None}
    return inst


def _make_instances_json(instances):
    """Build a JSON string for a list of instance dicts."""
    import json as _json

    return _json.dumps(instances)


# ── TestImportManyProjects ──────────────────────────────


class TestImportManyProjects:
    """Test with many projects and many instances."""

    def test_five_projects_all_imported(self, tmp_path):
        """5 projects with instances produce 5 domains in output."""
        projects = [{"name": "default"}]
        instance_map = {}
        for i in range(5):
            pname = f"proj{i}"
            projects.append({"name": pname})
            instance_map[pname] = _make_instances_json(
                [_make_instance_json(f"{pname}-box", ip=f"10.100.{i}.10")]
            )

        import json as _json
        env, cwd = _build_mock_env(tmp_path, _json.dumps(projects), instance_map)
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0

        content = (cwd / "infra.imported.yml").read_text()
        for i in range(5):
            assert f"proj{i}:" in content
            assert f"proj{i}-box:" in content

    def test_subnet_ids_sequential_for_many(self, tmp_path):
        """With 5 projects, subnet_ids go 0,1,2,3,4."""
        projects = [{"name": "default"}]
        instance_map = {}
        for i in range(5):
            pname = f"dom{i}"
            projects.append({"name": pname})
            instance_map[pname] = _make_instances_json(
                [_make_instance_json(f"{pname}-srv", ip=f"10.100.{i}.10")]
            )

        import json as _json
        env, cwd = _build_mock_env(tmp_path, _json.dumps(projects), instance_map)
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0

        content = (cwd / "infra.imported.yml").read_text()
        for i in range(5):
            assert f"subnet_id: {i}" in content

    def test_many_instances_per_project(self, tmp_path):
        """Project with 5 instances produces all 5 machines in output."""
        instances = []
        for i in range(5):
            instances.append(
                _make_instance_json(f"box{i}", ip=f"10.100.0.{10 + i}")
            )

        import json as _json
        projects = _json.dumps([{"name": "default"}, {"name": "bigproj"}])
        instance_map = {"bigproj": _make_instances_json(instances)}
        env, cwd = _build_mock_env(tmp_path, projects, instance_map)
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0

        content = (cwd / "infra.imported.yml").read_text()
        for i in range(5):
            assert f"box{i}:" in content
            assert f"10.100.0.{10 + i}" in content


# ── TestImportGlobalSection ─────────────────────────────


class TestImportGlobalSection:
    """Verify the global section of import output."""

    def test_global_has_base_subnet(self, mock_env):
        """Output includes base_subnet: "10.100"."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        assert data["global"]["base_subnet"] == "10.100"

    def test_global_has_default_os_image(self, mock_env):
        """Output includes default_os_image: "images:debian/13"."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        assert data["global"]["default_os_image"] == "images:debian/13"

    def test_project_name_is_imported(self, mock_env):
        """Output includes project_name: imported-infra."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        assert data["project_name"] == "imported-infra"


# ── TestImportDescriptions ──────────────────────────────


class TestImportDescriptions:
    """Verify description fields in import output."""

    def test_domain_description_includes_project_name(self, mock_env):
        """Domain description mentions 'Imported from Incus project X'."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        for domain_name, domain_conf in data["domains"].items():
            assert f"Imported from Incus project {domain_name}" in domain_conf["description"]

    def test_instance_description_is_imported(self, mock_env):
        """Instance description is 'Imported instance'."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        for domain_conf in data["domains"].values():
            for machine_conf in domain_conf["machines"].values():
                assert machine_conf["description"] == "Imported instance"


# ── TestImportRoles ─────────────────────────────────────


class TestImportRoles:
    """Verify roles assignment on imported instances."""

    def test_all_instances_get_base_system_role(self, mock_env):
        """Every imported instance has roles: [base_system]."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        for domain_conf in data["domains"].values():
            for machine_name, machine_conf in domain_conf["machines"].items():
                assert machine_conf["roles"] == ["base_system"], (
                    f"Machine {machine_name} should have roles [base_system]"
                )


# ── TestImportSpecialCharacters ─────────────────────────


class TestImportSpecialCharacters:
    """Edge cases with special names."""

    def test_project_name_with_hyphens(self, tmp_path):
        """Project 'my-project' imports correctly."""
        import json as _json

        projects = _json.dumps([{"name": "default"}, {"name": "my-project"}])
        instance_map = {
            "my-project": _make_instances_json(
                [_make_instance_json("my-project-srv", ip="10.100.0.10")]
            ),
        }
        env, cwd = _build_mock_env(tmp_path, projects, instance_map)
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0

        data = _load_output_yaml(cwd)
        assert "my-project" in data["domains"]
        assert "my-project-srv" in data["domains"]["my-project"]["machines"]

    def test_instance_with_long_name(self, tmp_path):
        """Instance with 30+ char name imported correctly."""
        import json as _json

        long_name = "a-very-long-instance-name-that-exceeds-thirty-characters"
        assert len(long_name) > 30
        projects = _json.dumps([{"name": "default"}, {"name": "longnames"}])
        instance_map = {
            "longnames": _make_instances_json(
                [_make_instance_json(long_name, ip="10.100.0.10")]
            ),
        }
        env, cwd = _build_mock_env(tmp_path, projects, instance_map)
        result = run_import([], env, cwd=cwd)
        assert result.returncode == 0

        data = _load_output_yaml(cwd)
        assert long_name in data["domains"]["longnames"]["machines"]


# ── TestImportOutputFormat ──────────────────────────────


class TestImportOutputFormat:
    """Verify output formatting."""

    def test_output_is_valid_yaml_loadable(self, mock_env):
        """Output can be loaded as YAML (filtering out comments/WARNING)."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        assert data is not None
        assert isinstance(data, dict)

    def test_output_contains_domains_key(self, mock_env):
        """Output YAML has 'domains' key."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        data = _load_output_yaml(cwd)
        assert "domains" in data

    def test_output_indentation_consistent(self, mock_env):
        """Domains are indented with 2 spaces, machines with 6 spaces."""
        env, _, cwd = mock_env
        run_import([], env, cwd=cwd)
        content = (cwd / "infra.imported.yml").read_text()
        lines = content.splitlines()

        found_domain = False
        found_machine = False
        for line in lines:
            # Domain lines: exactly 2 spaces then name + colon (e.g. "  admin:")
            if line.startswith("  admin:"):
                found_domain = True
                # Verify exactly 2 spaces of indentation
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                assert indent == 2
            # Machine lines: exactly 6 spaces then name + colon (e.g. "      admin-ctrl:")
            if line.startswith("      admin-ctrl:"):
                found_machine = True
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                assert indent == 6

        assert found_domain, "Should find domain 'admin' at 2-space indent"
        assert found_machine, "Should find machine 'admin-ctrl' at 6-space indent"
