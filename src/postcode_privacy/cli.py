"""Command line interface.

Two rules here are stricter than convenience would suggest, and both exist
because the failure they prevent is unrecoverable.

Key material never appears in an argument value. A command line is recorded in
shell history and is visible in the process table to every other user on the
machine, and a leaked key makes every perturbation in a release exactly
invertible. ``--key`` is therefore *defined* rather than merely absent, so that
using it produces an explanation instead of "no such option".

Diagnostics identify failing records by row number, never by postcode. The
alternative writes real postcodes out of the dataset and into pipeline logs,
which are usually less well protected than the data they describe.
"""

from __future__ import annotations

import csv
import json
import os
import secrets
import stat
from dataclasses import asdict
from pathlib import Path

import click

from postcode_privacy.graph.artefact import load_graph
from postcode_privacy.mechanism.mechanism import ON_ERROR_POLICIES, HopMechanism
from postcode_privacy.mechanism.prf import KEY_BYTES, Key

# Distinguishable so a pipeline can branch without parsing stderr.
EXIT_USAGE = 2
EXIT_ROWS_FAILED = 3


def _refuse_inline_key(
    ctx: click.Context,  # noqa: ARG001
    param: click.Parameter,  # noqa: ARG001
    value: str | None,
) -> None:
    """Refuse a key supplied as an argument value, without echoing it."""
    if value is None:
        return
    raise click.UsageError(
        "refusing a key given on the command line: it would be recorded in "
        "shell history and visible in the process table to anyone else on this "
        "machine. Use --key-file, or set POSTCODE_PRIVACY_KEY."
    )


inline_key_option = click.option(
    "--key",
    callback=_refuse_inline_key,
    expose_value=False,
    # Hidden from --help so it cannot be mistaken for the supported way in.
    hidden=True,
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="postcode-privacy")
def main() -> None:
    """Differential privacy for UK postcodes, measured in graph hops."""


@main.command()
@inline_key_option
@click.option(
    "--out",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Where to write the key.",
)
def keygen(out: Path) -> None:
    """Generate a new secret key.

    The key is as sensitive as the dataset it protects: anyone holding it and
    the graph can recover every true postcode.
    """
    if out.exists():
        raise click.UsageError(
            f"{out} already exists, refusing to overwrite it. Replacing a key "
            "orphans every release made with the old one: those outputs can "
            "never be reproduced or explained again."
        )

    # Created with restrictive permissions rather than chmod-ed afterwards, so
    # the material is never briefly world-readable on a shared machine.
    descriptor = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR)
    with os.fdopen(descriptor, "wb") as handle:
        # Generated here rather than via Key, which deliberately offers no way
        # to read its material back out.
        handle.write(secrets.token_bytes(KEY_BYTES))

    click.echo(f"wrote {out} (mode 0400). Treat it as you would the raw data.")


KEY_ENVIRONMENT_VARIABLE = "POSTCODE_PRIVACY_KEY"


def _load_key(key_file: Path | None) -> Key:
    if key_file is not None:
        return Key.from_file(key_file)
    if KEY_ENVIRONMENT_VARIABLE in os.environ:
        return Key.from_env(KEY_ENVIRONMENT_VARIABLE)
    raise click.UsageError(
        "no key supplied. Pass --key-file PATH, or set "
        f"{KEY_ENVIRONMENT_VARIABLE} to the key as hex. A key is never accepted "
        "as an argument value, because command lines are recorded."
    )


@main.command()
@inline_key_option
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "-o", required=True, type=click.Path(path_type=Path))
@click.option(
    "--graph",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Graph artefact built by `postcode-privacy build`.",
)
@click.option("--epsilon", required=True, type=float, help="Privacy budget per hop.")
@click.option("--postcode-col", required=True, help="Column holding the true postcode.")
@click.option(
    "--subject-col", required=True, help="Column holding a stable subject id."
)
@click.option(
    "--out-col",
    default="postcode_dp",
    show_default=True,
    help="Column to write. Named so it cannot be mistaken for the true value.",
)
@click.option("--radius", type=int, default=None, help="Hop cap. Derived if omitted.")
@click.option(
    "--on-error",
    type=click.Choice(ON_ERROR_POLICIES),
    default="error",
    show_default=True,
    help="What to do with a row that cannot be perturbed.",
)
@click.option(
    "--key-file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def perturb(
    source: Path,
    out: Path,
    graph: Path,
    epsilon: float,
    postcode_col: str,
    subject_col: str,
    out_col: str,
    radius: int | None,
    on_error: str,
    key_file: Path | None,
) -> None:
    """Replace the postcode column of SOURCE with perturbed postcodes."""
    if out.resolve() == source.resolve():
        raise click.UsageError(
            "refusing to write over the input file. Perturbation is not "
            "invertible without the key, so the original would be lost."
        )
    key = _load_key(key_file)

    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise click.UsageError(f"{source} has no rows")
    for column in (postcode_col, subject_col):
        if column not in rows[0]:
            raise click.UsageError(f"column {column!r} is not in {source}")

    loaded = load_graph(graph)
    mechanism = HopMechanism(loaded, epsilon=epsilon, radius=radius)

    # Always resolved with "null" so that every failing row is found in one
    # pass. Stopping at the first would report one row number when the operator
    # needs all of them, and a second run would be needed to find the next.
    outputs = mechanism.perturb_many(
        [row[postcode_col] for row in rows],
        [row[subject_col] for row in rows],
        key=key,
        on_error="null",
    )
    failed = [index for index, value in enumerate(outputs) if value is None]

    if failed and on_error == "error":
        # Row numbers only. Naming the postcodes would copy real values out of
        # the dataset and into pipeline logs.
        raise click.ClickException(
            f"{len(failed)} row(s) could not be perturbed: "
            f"{_summarise_rows(failed)}. Postcodes are not shown, so that source "
            "data does not reach the logs; look the rows up in the input. Use "
            "--on-error drop or --on-error null to continue instead."
        )

    written = [
        {**row, out_col: value if value is not None else ""}
        for row, value in zip(rows, outputs, strict=True)
        if not (value is None and on_error == "drop")
    ]
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(written[0]))
        writer.writeheader()
        writer.writerows(written)

    distributions = [
        mechanism.distribution(row[postcode_col])
        for index, row in enumerate(rows)
        if outputs[index] is not None
    ]
    teleports = [d.teleport_probability for d in distributions] or [0.0]
    provenance = asdict(loaded.provenance) if loaded.provenance else {}

    manifest = {
        "epsilon": epsilon,
        "radius": mechanism.radius,
        "max_teleport_probability": max(teleports),
        "prior": "population",
        "on_error": on_error,
        "rows_in": len(rows),
        "rows_written": len(written),
        "rows_failed": len(failed),
        "distinct_postcodes": len({row[postcode_col] for row in rows}),
        "out_col": out_col,
        "graph": provenance,
    }
    manifest_path = out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    click.echo(
        f"graph: {provenance.get('source', graph.name)}\n"
        f"epsilon: {epsilon} per hop   radius: {mechanism.radius} hops\n"
        f"max teleport probability: {max(teleports):.2g}\n"
        f"rows: {len(rows)} in, {len(written)} written, {len(failed)} failed\n"
        f"wrote {out} and {manifest_path}",
        err=True,
    )
    if failed:
        raise SystemExit(EXIT_ROWS_FAILED)


def _summarise_rows(indices: list[int], limit: int = 10) -> str:
    """Row numbers, one-based and counting the header as row 0."""
    shown = ", ".join(str(index + 1) for index in indices[:limit])
    extra = len(indices) - limit
    return f"row {shown}" + (f" and {extra} more" if extra > 0 else "")
