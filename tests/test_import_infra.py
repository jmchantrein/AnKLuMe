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
