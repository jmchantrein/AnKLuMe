"""Tests du module engine/nesting.py — nesting Incus.

Couvre :
- Détection du contexte de nesting (NestingContext)
- Préfixe de nesting sur les noms de ressources
- Configuration de sécurité par niveau
- Fichiers de contexte pour les instances enfants
- Intégration avec le réconciliateur (préfixes + sécurité)
"""

from __future__ import annotations

from pathlib import Path

from anklume.engine.models import NestingConfig
from anklume.engine.nesting import (
    NestingContext,
    context_files_for_instance,
    detect_nesting_context,
    nesting_security_config,
    prefix_name,
)

from .conftest import make_domain, make_infra, make_machine, mock_driver

# ================================================================
# NestingContext
# ================================================================


class TestNestingContext:
    """Valeurs par défaut et propriétés de NestingContext."""

    def test_defaults(self):
        ctx = NestingContext()
        assert ctx.absolute_level == 0
        assert ctx.relative_level == 0
        assert ctx.vm_nested is False
        assert ctx.yolo is False

    def test_custom_values(self):
        ctx = NestingContext(absolute_level=3, relative_level=1, vm_nested=True, yolo=True)
        assert ctx.absolute_level == 3
        assert ctx.relative_level == 1
        assert ctx.vm_nested is True
        assert ctx.yolo is True


# ================================================================
# detect_nesting_context
# ================================================================


class TestDetectNestingContext:
    """Détection du contexte via /etc/anklume/."""

    def test_no_directory(self, tmp_path: Path):
        """Sans /etc/anklume/ → niveau 0 (hôte)."""
        ctx = detect_nesting_context(tmp_path / "etc" / "anklume")
        assert ctx.absolute_level == 0
        assert ctx.relative_level == 0
        assert ctx.vm_nested is False
        assert ctx.yolo is False

    def test_level_1(self, tmp_path: Path):
        """Fichiers de contexte L1."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("false")
        (etc / "yolo").write_text("false")

        ctx = detect_nesting_context(etc)
        assert ctx.absolute_level == 1
        assert ctx.relative_level == 1
        assert ctx.vm_nested is False
        assert ctx.yolo is False

    def test_level_3_vm_nested(self, tmp_path: Path):
        """Contexte L3 avec VM dans la chaîne."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("3")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("true")
        (etc / "yolo").write_text("false")

        ctx = detect_nesting_context(etc)
        assert ctx.absolute_level == 3
        assert ctx.relative_level == 1
        assert ctx.vm_nested is True

    def test_yolo_mode(self, tmp_path: Path):
        """Mode yolo activé."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("2")
        (etc / "relative_level").write_text("2")
        (etc / "vm_nested").write_text("false")
        (etc / "yolo").write_text("true")

        ctx = detect_nesting_context(etc)
        assert ctx.yolo is True

    def test_partial_files(self, tmp_path: Path):
        """Seul absolute_level présent → les autres à défaut."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("2")

        ctx = detect_nesting_context(etc)
        assert ctx.absolute_level == 2
        assert ctx.relative_level == 0
        assert ctx.vm_nested is False
        assert ctx.yolo is False

    def test_empty_file(self, tmp_path: Path):
        """Fichier vide → valeur par défaut."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("")

        ctx = detect_nesting_context(etc)
        assert ctx.absolute_level == 0

    def test_invalid_integer(self, tmp_path: Path):
        """Valeur non-entière → valeur par défaut."""
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("abc")

        ctx = detect_nesting_context(etc)
        assert ctx.absolute_level == 0


# ================================================================
# prefix_name
# ================================================================


class TestPrefixName:
    """Préfixage des noms de ressources Incus."""

    def test_level_0_no_prefix(self):
        """L0 (hôte) → pas de préfixe."""
        ctx = NestingContext(absolute_level=0)
        assert prefix_name("pro", ctx, NestingConfig(prefix=True)) == "pro"

    def test_level_1_prefix(self):
        """L1 → préfixe 001-."""
        ctx = NestingContext(absolute_level=1)
        assert prefix_name("pro", ctx, NestingConfig(prefix=True)) == "001-pro"

    def test_level_2_prefix(self):
        """L2 → préfixe 002-."""
        ctx = NestingContext(absolute_level=2)
        assert prefix_name("pro", ctx, NestingConfig(prefix=True)) == "002-pro"

    def test_level_99_prefix(self):
        """L99 → préfixe 099-."""
        ctx = NestingContext(absolute_level=99)
        assert prefix_name("pro", ctx, NestingConfig(prefix=True)) == "099-pro"

    def test_prefix_disabled(self):
        """nesting.prefix=false → pas de préfixe, quel que soit le niveau."""
        ctx = NestingContext(absolute_level=3)
        assert prefix_name("pro", ctx, NestingConfig(prefix=False)) == "pro"

    def test_prefix_network_name(self):
        """Préfixage d'un nom de réseau."""
        ctx = NestingContext(absolute_level=1)
        assert prefix_name("net-pro", ctx, NestingConfig(prefix=True)) == "001-net-pro"

    def test_prefix_instance_name(self):
        """Préfixage d'un nom d'instance."""
        ctx = NestingContext(absolute_level=2)
        assert prefix_name("pro-dev", ctx, NestingConfig(prefix=True)) == "002-pro-dev"

    def test_prefix_format_3_digits(self):
        """Le préfixe fait toujours 3 chiffres."""
        ctx = NestingContext(absolute_level=5)
        result = prefix_name("x", ctx, NestingConfig(prefix=True))
        assert result == "005-x"
        assert result[:3].isdigit()


# ================================================================
# nesting_security_config
# ================================================================


class TestNestingSecurityConfig:
    """Configuration de sécurité des instances créées."""

    def test_level_0_nesting_enabled(self):
        """L0 crée L1 : nesting + syscalls intercept."""
        config = nesting_security_config(0)
        assert config["security.nesting"] == "true"
        assert config["security.syscalls.intercept.mknod"] == "true"
        assert config["security.syscalls.intercept.setxattr"] == "true"

    def test_level_0_not_privileged(self):
        """L0 crée L1 : pas privilegié (unprivileged)."""
        config = nesting_security_config(0)
        assert "security.privileged" not in config

    def test_level_1_privileged(self):
        """L1 crée L2 : privilegié + nesting."""
        config = nesting_security_config(1)
        assert config["security.nesting"] == "true"
        assert config["security.privileged"] == "true"

    def test_level_1_no_syscalls_intercept(self):
        """L1 crée L2 : pas de syscalls intercept (privilegié suffit)."""
        config = nesting_security_config(1)
        assert "security.syscalls.intercept.mknod" not in config
        assert "security.syscalls.intercept.setxattr" not in config

    def test_level_5_same_as_level_1(self):
        """L5 crée L6 : même config que L1→L2."""
        config = nesting_security_config(5)
        assert config == nesting_security_config(1)

    def test_level_1_logs_privileged_warning(self, caplog):
        """L1+ émet un warning sur le mode privilégié."""
        import logging

        with caplog.at_level(logging.WARNING, logger="anklume.engine.nesting"):
            nesting_security_config(1)
        assert "privilegié" in caplog.text or "privileged" in caplog.text

    def test_level_0_no_warning(self, caplog):
        """L0 n'émet aucun warning."""
        import logging

        with caplog.at_level(logging.WARNING, logger="anklume.engine.nesting"):
            nesting_security_config(0)
        assert caplog.text == ""


# ================================================================
# context_files_for_instance
# ================================================================


class TestContextFilesForInstance:
    """Génération des fichiers de contexte pour les instances enfants."""

    def test_host_creates_lxc(self):
        """L0 crée un conteneur LXC → L1."""
        parent = NestingContext(absolute_level=0)
        files = context_files_for_instance(parent, "lxc")
        assert files["absolute_level"] == "1"
        assert files["relative_level"] == "1"
        assert files["vm_nested"] == "false"
        assert files["yolo"] == "false"

    def test_l1_creates_lxc(self):
        """L1 crée un conteneur LXC → L2."""
        parent = NestingContext(absolute_level=1, relative_level=1)
        files = context_files_for_instance(parent, "lxc")
        assert files["absolute_level"] == "2"
        assert files["relative_level"] == "2"

    def test_vm_resets_relative_level(self):
        """L0 crée une VM → relative_level reset à 0."""
        parent = NestingContext(absolute_level=0)
        files = context_files_for_instance(parent, "vm")
        assert files["absolute_level"] == "1"
        assert files["relative_level"] == "0"

    def test_vm_sets_vm_nested(self):
        """Créer une VM → vm_nested = true."""
        parent = NestingContext(absolute_level=0)
        files = context_files_for_instance(parent, "vm")
        assert files["vm_nested"] == "true"

    def test_vm_nested_propagated(self):
        """vm_nested hérité du parent même pour LXC."""
        parent = NestingContext(absolute_level=2, relative_level=0, vm_nested=True)
        files = context_files_for_instance(parent, "lxc")
        assert files["vm_nested"] == "true"

    def test_yolo_inherited(self):
        """yolo hérité du parent."""
        parent = NestingContext(absolute_level=1, yolo=True)
        files = context_files_for_instance(parent, "lxc")
        assert files["yolo"] == "true"

    def test_yolo_false_by_default(self):
        parent = NestingContext(absolute_level=0)
        files = context_files_for_instance(parent, "lxc")
        assert files["yolo"] == "false"

    def test_all_four_files_present(self):
        """Toujours exactement 4 fichiers de contexte."""
        parent = NestingContext()
        files = context_files_for_instance(parent, "lxc")
        assert set(files.keys()) == {"absolute_level", "relative_level", "vm_nested", "yolo"}

    def test_deep_nesting_lxc(self):
        """L4 crée L5 (LXC dans LXC)."""
        parent = NestingContext(absolute_level=4, relative_level=4)
        files = context_files_for_instance(parent, "lxc")
        assert files["absolute_level"] == "5"
        assert files["relative_level"] == "5"

    def test_vm_after_vm(self):
        """VM dans VM : absolute_level incrémenté, relative reset."""
        parent = NestingContext(absolute_level=2, relative_level=0, vm_nested=True)
        files = context_files_for_instance(parent, "vm")
        assert files["absolute_level"] == "3"
        assert files["relative_level"] == "0"
        assert files["vm_nested"] == "true"


# ================================================================
# Intégration : préfixes dans le réconciliateur
# ================================================================


class TestReconcilerNestingPrefix:
    """Le réconciliateur applique les préfixes de nesting."""

    def test_l1_project_prefixed(self):
        """En L1, le projet Incus est préfixé 001-."""
        from anklume.engine.reconciler import reconcile

        infra = make_infra(domains={"pro": make_domain("pro")})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=1)
        result = reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        project_actions = [a for a in result.actions if a.resource == "project"]
        assert len(project_actions) == 1
        assert project_actions[0].target == "001-pro"

    def test_l1_network_prefixed(self):
        """En L1, le réseau est préfixé 001-."""
        from anklume.engine.reconciler import reconcile

        infra = make_infra(domains={"pro": make_domain("pro")})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=1)
        result = reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        net_actions = [a for a in result.actions if a.resource == "network"]
        assert len(net_actions) == 1
        assert net_actions[0].target == "001-net-pro"

    def test_l1_instance_prefixed(self):
        """En L1, les instances sont préfixées 001-."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=1)
        result = reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        inst_actions = [
            a for a in result.actions if a.resource == "instance" and a.verb == "create"
        ]
        assert len(inst_actions) == 1
        assert inst_actions[0].target == "001-pro-dev"

    def test_l0_no_prefix(self):
        """En L0, aucun préfixe."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        result = reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        names = [a.target for a in result.actions]
        assert "pro" in names
        assert "net-pro" in names
        assert "pro-dev" in names

    def test_prefix_disabled_no_prefix(self):
        """nesting.prefix=false → pas de préfixe en L1."""
        from anklume.engine.models import NestingConfig
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        infra.config.nesting = NestingConfig(prefix=False)
        driver = mock_driver()

        ctx = NestingContext(absolute_level=1)
        result = reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        names = [a.target for a in result.actions]
        assert "pro" in names
        assert "net-pro" in names
        assert "pro-dev" in names


# ================================================================
# Intégration : sécurité nesting dans le réconciliateur
# ================================================================


class TestReconcilerNestingSecurity:
    """Le réconciliateur applique la config de sécurité nesting."""

    def test_l0_nesting_config_on_create(self):
        """L0 crée des instances avec security.nesting=true."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        create_call = driver.instance_create.call_args
        config = create_call.kwargs.get("config", {})
        assert config.get("security.nesting") == "true"
        assert config.get("security.syscalls.intercept.mknod") == "true"
        assert config.get("security.syscalls.intercept.setxattr") == "true"

    def test_l1_privileged_on_create(self):
        """L1 crée des instances avec security.privileged=true."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=1)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        create_call = driver.instance_create.call_args
        config = create_call.kwargs.get("config", {})
        assert config.get("security.nesting") == "true"
        assert config.get("security.privileged") == "true"

    def test_explicit_config_overrides_nesting(self):
        """La config explicite de la machine override le nesting."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro", config={"security.nesting": "false"})
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        create_call = driver.instance_create.call_args
        config = create_call.kwargs.get("config", {})
        # La config explicite a priorité
        assert config["security.nesting"] == "false"


# ================================================================
# Intégration : fichiers de contexte injectés
# ================================================================


class TestReconcilerContextFiles:
    """Le réconciliateur injecte les fichiers de contexte après démarrage."""

    @staticmethod
    def _get_inject_script(driver) -> str:
        """Extrait le script sh -c passé à instance_exec."""
        for c in driver.instance_exec.call_args_list:
            args = c[0]  # positional args: (instance, project, command)
            cmd = args[2]
            if cmd[0] == "sh" and cmd[1] == "-c":
                return cmd[2]
        return ""

    def test_context_files_injected_as_single_call(self):
        """Injection en un seul appel instance_exec (batch)."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        # Un seul appel exec pour l'injection (batch)
        assert driver.instance_exec.call_count == 1
        script = self._get_inject_script(driver)
        assert "mkdir -p /etc/anklume" in script

    def test_context_files_correct_values_lxc(self):
        """L0 crée LXC : absolute_level=1, relative_level=1, vm_nested=false."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        script = self._get_inject_script(driver)
        assert "printf '%s' 1 > /etc/anklume/absolute_level" in script
        assert "printf '%s' 1 > /etc/anklume/relative_level" in script
        assert "printf '%s' false > /etc/anklume/vm_nested" in script
        assert "printf '%s' false > /etc/anklume/yolo" in script

    def test_dry_run_no_context_injection(self):
        """En dry-run, pas d'injection de fichiers de contexte."""
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=True, nesting_context=ctx)

        assert not driver.instance_exec.called

    def test_vm_instance_context_files(self):
        """VM : relative_level=0, vm_nested=true."""
        from anklume.engine.reconciler import reconcile

        vm = make_machine("server", "pro", type="vm")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"server": vm})})
        driver = mock_driver()

        ctx = NestingContext(absolute_level=0)
        reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        script = self._get_inject_script(driver)
        assert "printf '%s' 0 > /etc/anklume/relative_level" in script
        assert "printf '%s' true > /etc/anklume/vm_nested" in script

    def test_context_injection_failure_is_warning(self):
        """Si l'injection échoue, le pipeline continue (best-effort)."""
        from anklume.engine.incus_driver import IncusError
        from anklume.engine.reconciler import reconcile

        dev = make_machine("dev", "pro")
        infra = make_infra(domains={"pro": make_domain("pro", machines={"dev": dev})})
        driver = mock_driver()
        driver.instance_exec.side_effect = IncusError(["incus", "exec"], 1, "error")

        ctx = NestingContext(absolute_level=0)
        result = reconcile(infra, driver, dry_run=False, nesting_context=ctx)

        # Le pipeline continue malgré l'échec d'injection
        create_actions = [a for a in result.executed if a.verb == "create"]
        assert len(create_actions) > 0
