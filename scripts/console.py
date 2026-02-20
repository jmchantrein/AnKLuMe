#!/usr/bin/env python3
"""anklume tmux console — domain-colored panes from infra.yml."""

import argparse
import sys
from pathlib import Path

# Add scripts/ to path for imports (same pattern as tests/conftest.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate import load_infra  # noqa: E402

TRUST_COLORS = {
    "admin": "colour17",
    "trusted": "colour22",
    "semi-trusted": "colour58",
    "untrusted": "colour52",
    "disposable": "colour53",
}

TRUST_LABELS = {
    "admin": "dark blue",
    "trusted": "dark green",
    "semi-trusted": "dark yellow",
    "untrusted": "dark red",
    "disposable": "dark magenta",
}

# Default prefix for the anklume session. Standard Ctrl-b is kept as default.
# When running tmux inside containers (nested tmux), use Ctrl-a on the inner
# session to avoid prefix collision.
DEFAULT_PREFIX = "C-b"


def infer_trust_level(domain_name, domain_config):
    """Infer trust level from domain name and config if not explicitly set.

    Heuristic:
    - domain name contains "admin" or "anklume" → admin
    - ephemeral: true → disposable
    - default → trusted
    """
    if "admin" in domain_name.lower() or "anklume" in domain_name.lower():
        return "admin"
    if domain_config.get("ephemeral", False):
        return "disposable"
    return "trusted"


def build_session_config(infra):
    """Build tmux session configuration from infra dict.

    Returns a list of window configs:
    [
        {
            "name": "admin",
            "trust": "admin",
            "color": "dark blue",
            "panes": [
                {"machine": "sa-admin", "command": "incus exec sa-admin --project admin -- bash"},
            ]
        },
        ...
    ]
    """
    windows = []
    domains = infra.get("domains", {})

    # Window 0: anklume-instance (the controller) — always present
    windows.append({
        "name": "anklume",
        "subnet_id": 0,
        "trust": "admin",
        "color": TRUST_LABELS["admin"],
        "panes": [{
            "machine": "anklume-instance",
            "command": "bash",  # Already inside anklume-instance
        }],
    })

    # Remaining windows sorted by subnet_id
    sorted_domains = sorted(
        domains.items(),
        key=lambda item: item[1].get("subnet_id", 0),
    )

    for domain_name, domain_config in sorted_domains:
        machines = domain_config.get("machines", {})

        if not machines:
            continue  # Skip domains with no machines

        # Determine trust level (explicit or inferred)
        trust_level = domain_config.get("trust_level")
        if trust_level is None:
            trust_level = infer_trust_level(domain_name, domain_config)

        color_label = TRUST_LABELS.get(trust_level, "unknown")
        subnet_id = domain_config.get("subnet_id", 0)

        panes = []
        for machine_name in sorted(machines.keys()):
            panes.append({
                "machine": machine_name,
                "command": f"incus exec {machine_name} --project {domain_name} -- bash",
            })

        windows.append({
            "name": domain_name,
            "subnet_id": subnet_id,
            "trust": trust_level,
            "color": color_label,
            "panes": panes,
        })

    return windows


def print_dry_run(config, session_name="anklume", prefix=DEFAULT_PREFIX):
    """Print dry-run summary of the session configuration."""
    print(f"Session: {session_name} (prefix: {prefix})")
    for idx, window in enumerate(config):
        sid = window.get("subnet_id", "?")
        print(f"  Window [{idx}] {window['name']} (subnet: {sid}, trust: {window['trust']}, color: {window['color']})")
        for pane in window["panes"]:
            print(f"    Pane: {pane['machine']} → {pane['command']}")


def create_session(config, session_name="anklume", attach=True, prefix=DEFAULT_PREFIX):
    """Create tmux session using libtmux.

    Args:
        config: list of window dicts from build_session_config()
        session_name: tmux session name
        attach: whether to attach after creation
        prefix: tmux prefix key for this session (default: Ctrl-b)
    """
    import libtmux

    server = libtmux.Server()

    # Check if session exists
    if server.has_session(session_name):
        print(f"Session '{session_name}' already exists. Attaching...")
        if attach:
            server.cmd("attach-session", "-t", session_name)
        return

    # Create new session
    session = server.new_session(session_name=session_name, attach=False)

    # Set prefix key for this session
    session.cmd("set-option", "prefix", prefix)
    session.cmd("set-option", "prefix2", "None")

    # Enable pane border labels (server-side, containers cannot spoof)
    session.cmd("set-option", "pane-border-status", "top")
    session.cmd("set-option", "pane-border-format", " #{pane_title} ")

    # Status bar base style
    session.cmd("set-option", "status-style", "bg=black,fg=white")

    for window_idx, window_config in enumerate(config):
        if window_idx == 0:
            # Use the default first window created by tmux
            window = session.windows[0]
            window.rename_window(window_config["name"])
        else:
            window = session.new_window(window_name=window_config["name"])

        panes = window_config["panes"]
        color_code = TRUST_COLORS.get(window_config["trust"], "default")

        # Color the window tab in the status bar (server-side, cannot be spoofed)
        window.cmd("set-window-option", "window-status-style", f"bg={color_code},fg=white")
        window.cmd("set-window-option", "window-status-current-style", f"bg={color_code},fg=white,bold")

        for pane_idx, pane_config in enumerate(panes):
            if pane_idx == 0:
                pane = window.panes[0]
            else:
                try:
                    pane = window.split()
                except Exception as exc:
                    print(f"  Warning: cannot split pane for "
                          f"{pane_config['machine']} ({exc}). "
                          f"Terminal too small? Skipping.")
                    continue

            # Set pane background color (server-side, cannot be spoofed)
            pane.cmd("select-pane", "-P", f"bg={color_code}")
            pane_label = f"[{window_config['name']}] {pane_config['machine']}"
            pane.cmd("select-pane", "-T", pane_label)

            # Send the incus exec command
            pane.send_keys(pane_config["command"])

        # Set tiled layout for multi-pane windows
        if len(window.panes) > 1:
            window.select_layout("tiled")

    # Select first window
    session.windows[0].select()

    if attach:
        server.cmd("attach-session", "-t", session_name)
    else:
        print(f"Session '{session_name}' created. Attach with: tmux attach -t {session_name}")


def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate tmux console from infra.yml")
    parser.add_argument(
        "infra_file",
        nargs="?",
        help="Path to infra.yml or infra/ directory (default: auto-detect)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print configuration without creating session",
    )
    parser.add_argument(
        "--attach",
        dest="attach",
        action="store_true",
        default=True,
        help="Attach to session after creation (default)",
    )
    parser.add_argument(
        "--no-attach",
        dest="attach",
        action="store_false",
        help="Do not attach to session after creation",
    )
    parser.add_argument("--session-name", default="anklume", help="Tmux session name (default: anklume)")
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="Tmux prefix key for the session (default: C-b). "
        "Use C-a for nested tmux inside containers.",
    )
    parser.add_argument("--kill", action="store_true", help="Kill existing session before creating new one")

    args = parser.parse_args(argv)

    # Auto-detect infra file if not provided
    if args.infra_file is None:
        if Path("infra").is_dir():
            args.infra_file = "infra"
        elif Path("infra.yml").is_file():
            args.infra_file = "infra.yml"
        else:
            print("ERROR: Could not find infra.yml or infra/ in current directory.", file=sys.stderr)
            sys.exit(1)

    # Load infrastructure
    infra = load_infra(args.infra_file)

    # Build session configuration
    config = build_session_config(infra)

    if not config:
        print("No domains with machines found. Nothing to create.")
        return

    if args.dry_run:
        print_dry_run(config, args.session_name, args.prefix)
        return

    # Kill existing session if --kill
    if args.kill:
        import libtmux
        server = libtmux.Server()
        if server.has_session(args.session_name):
            server.sessions.get(session_name=args.session_name).kill()
            print(f"Killed existing session '{args.session_name}'")

    # Create session
    create_session(config, session_name=args.session_name, attach=args.attach, prefix=args.prefix)


if __name__ == "__main__":
    main()
