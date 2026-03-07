"""Plugin de connexion Ansible pour Incus (via incus exec/file)."""

from __future__ import annotations

import subprocess

from ansible.plugins.connection import ConnectionBase

DOCUMENTATION = """
    name: anklume_incus
    short_description: Connexion aux instances Incus via incus exec
    description:
        - Execute des commandes dans les instances Incus via incus exec.
        - Transfert de fichiers via incus file push/pull.
    options:
        remote_addr:
            description: Nom de l'instance Incus
            default: inventory_hostname
            vars:
                - name: ansible_host
        incus_project:
            description: Projet Incus
            default: default
            vars:
                - name: anklume_incus_project
"""


class Connection(ConnectionBase):
    transport = "anklume_incus"
    has_pipelining = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instance = None
        self._project = None

    def _connect(self):
        self._instance = self.get_option("remote_addr") or self._play_context.remote_addr
        self._project = self.get_option("incus_project") or "default"
        self._connected = True
        return self

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)

        incus_cmd = [
            "incus",
            "exec",
            self._instance,
            "--project",
            self._project,
            "--",
            "sh",
            "-c",
            cmd,
        ]

        result = subprocess.run(
            incus_cmd,
            input=in_data,
            capture_output=True,
        )

        return result.returncode, result.stdout, result.stderr

    def put_file(self, in_path, out_path):
        incus_cmd = [
            "incus",
            "file",
            "push",
            in_path,
            f"{self._instance}/{out_path.lstrip('/')}",
            "--project",
            self._project,
        ]
        subprocess.run(incus_cmd, check=True, capture_output=True)

    def fetch_file(self, in_path, out_path):
        incus_cmd = [
            "incus",
            "file",
            "pull",
            f"{self._instance}/{in_path.lstrip('/')}",
            out_path,
            "--project",
            self._project,
        ]
        subprocess.run(incus_cmd, check=True, capture_output=True)

    def close(self):
        self._connected = False
