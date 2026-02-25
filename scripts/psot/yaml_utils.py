"""YAML serialization helpers for the PSOT generator."""

import yaml


class _Dumper(yaml.SafeDumper):
    """YAML dumper: None as empty, preserves insertion order, proper list indent."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


_Dumper.add_representer(
    type(None),
    lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""),
)


def _yaml(data):
    return yaml.dump(
        data,
        Dumper=_Dumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
