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
import hashlib
import json
import os
import secrets
import stat
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import click
import numpy as np

from postcode_privacy.fetch import fetch_onspd
from postcode_privacy.graph.artefact import load_graph, save_graph
from postcode_privacy.graph.build import assemble
from postcode_privacy.graph.onspd import read_onspd
from postcode_privacy.graph.postcode_graph import PostcodeGraph
from postcode_privacy.graph.prior import population_prior
from postcode_privacy.graph.provenance import Provenance
from postcode_privacy.mechanism.calibrate import (
    UnknownTargetError,
    calibrate,
    displacement_summary,
    sample_postcodes,
)
from postcode_privacy.mechanism.mechanism import ON_ERROR_POLICIES, HopMechanism
from postcode_privacy.mechanism.prf import KEY_BYTES, Key
from postcode_privacy.postcodes import (
    LargeUserPostcodeError,
    UnknownPostcodeError,
)

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


PARQUET_SUFFIXES = {".parquet", ".pq"}


def _require_frames(path: Path) -> object:
    """Import pandas, or explain which extra provides it."""
    try:
        import pandas
    except ImportError as error:  # pragma: no cover - exercised by install shape
        raise click.UsageError(
            f"reading or writing {path.suffix} needs pandas and pyarrow, which "
            'are not installed. Install them with: pip install "postcode-privacy'
            '[frames]". CSV needs no extra.'
        ) from error
    return pandas


def _read_records(path: Path) -> list[dict[str, object]]:
    """Rows as dictionaries, whatever the file format."""
    if path.suffix.lower() in PARQUET_SUFFIXES:
        pandas = _require_frames(path)
        return pandas.read_parquet(path).to_dict("records")  # ty: ignore
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_records(path: Path, rows: list[dict[str, object]]) -> None:
    if path.suffix.lower() in PARQUET_SUFFIXES:
        pandas = _require_frames(path)
        pandas.DataFrame(rows).to_parquet(path, index=False)  # ty: ignore
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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

    rows = _read_records(source)
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
        [str(row[postcode_col]) for row in rows],
        [str(row[subject_col]) for row in rows],
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

    written: list[dict[str, object]] = [
        {**row, out_col: value if value is not None else ""}
        for row, value in zip(rows, outputs, strict=True)
        if not (value is None and on_error == "drop")
    ]
    _write_records(out, written)

    distributions = [
        mechanism.distribution(str(row[postcode_col]))
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
        "distinct_postcodes": len({str(row[postcode_col]) for row in rows}),
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@main.command()
@inline_key_option
@click.option(
    "--onspd",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="ONS Postcode Directory CSV.",
)
@click.option(
    "--fetch",
    is_flag=True,
    help="Download the current ONSPD release instead of supplying one.",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Where --fetch puts the download.",
)
@click.option("--out", "-o", required=True, type=click.Path(path_type=Path))
@click.option(
    "--oa-populations",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Census population by output area or data zone. Repeatable.",
)
@click.option(
    "--postcode-populations",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Census population per postcode, where a nation publishes it. Repeatable.",
)
@click.option(
    "--uniform-prior",
    is_flag=True,
    help="Weight every postcode equally. Must be asked for explicitly.",
)
@click.option(
    "--gb-only",
    is_flag=True,
    help="Exclude Northern Ireland, whose records may not be redistributed.",
)
@click.option(
    "--prune-alpha",
    type=float,
    default=None,
    help="Enable long-edge pruning and bridging. Off by default; see the docs.",
)
def build(
    onspd: Path | None,
    fetch: bool,
    cache_dir: Path,
    out: Path,
    oa_populations: tuple[Path, ...],
    postcode_populations: tuple[Path, ...],
    uniform_prior: bool,
    gb_only: bool,
    prune_alpha: float | None,
) -> None:
    """Build a postcode graph artefact from ONSPD."""
    if fetch and onspd is not None:
        raise click.UsageError("give either --onspd PATH or --fetch, not both.")
    if not fetch and onspd is None:
        raise click.UsageError("give --onspd PATH, or --fetch to download one.")
    if out.exists():
        raise click.UsageError(
            f"{out} already exists, refusing to overwrite it. A released dataset "
            "can only be explained if the graph that produced it still exists."
        )
    if not (oa_populations or postcode_populations or uniform_prior):
        raise click.UsageError(
            "no population sources given. Pass --oa-populations and/or "
            "--postcode-populations, or ask for --uniform-prior explicitly. "
            "Falling back silently would ship a uniform prior that looked "
            "population weighted."
        )

    if onspd is None:
        # Best-effort: the release identifier changes quarterly and the portal
        # search is outside our control, so every failure explains the manual
        # route rather than leaving the user stuck.
        try:
            onspd = fetch_onspd(cache_dir)
        except Exception as error:
            raise click.ClickException(
                f"could not fetch ONSPD automatically: {error}"
            ) from error
        click.echo(f"fetched {onspd}", err=True)

    table = read_onspd(onspd, gb_only=gb_only)
    click.echo(
        f"read {table.n_rows_read:,} rows -> {len(table.postcodes):,} usable nodes",
        err=True,
    )
    for reason, count in sorted(table.dropped.items()):
        click.echo(f"  dropped {reason.replace('_', ' ')}: {count:,}", err=True)
    click.echo(f"  large user excluded: {len(table.large_user):,}", err=True)

    if uniform_prior:
        prior = np.ones(len(table.postcodes), dtype=np.int64)
        coverage = None
        click.echo("prior: uniform (requested)", err=True)
    else:
        prior, coverage = population_prior(
            table.postcodes,
            table.output_areas,
            area_populations=list(oa_populations),
            postcode_populations=list(postcode_populations),
        )
        total = coverage.total or 1
        click.echo(
            f"prior: population, {int(np.sum(prior)):,} people. coverage "
            f"{(total - coverage.unmatched) / total:.2%} "
            f"(per postcode {coverage.from_postcode:,}, "
            f"per area {coverage.from_area:,}, "
            f"floored {coverage.unmatched:,})",
            err=True,
        )

    assembled = assemble(table.eastings, table.northings, prune_alpha=prune_alpha)
    graph = PostcodeGraph.from_edges(
        postcodes=table.postcodes,
        edges=assembled.edges,
        prior=prior,
        excluded=table.large_user,
        eastings=table.eastings,
        northings=table.northings,
    )
    degree = np.bincount(assembled.edges.ravel(), minlength=graph.n_nodes)
    click.echo(
        f"graph: {len(assembled.edges):,} edges, mean degree {degree.mean():.2f}",
        err=True,
    )

    provenance = Provenance(
        source=onspd.name,
        source_sha256=_sha256(onspd),
        gb_only=gb_only,
        prune_alpha=prune_alpha,
        library_version=version("postcode-privacy"),
    )
    save_graph(graph, out, provenance=provenance)

    manifest = {
        "nodes": graph.n_nodes,
        "edges": len(assembled.edges),
        "mean_degree": round(float(degree.mean()), 3),
        "rows_read": table.n_rows_read,
        "dropped": table.dropped,
        "large_user_excluded": len(table.large_user),
        "pruned_edges": len(assembled.pruned),
        "bridges": len(assembled.bridges),
        "prior": (
            {"kind": "uniform"}
            if coverage is None
            else {
                "kind": "population",
                "total_people": int(np.sum(prior)),
                "from_postcode": coverage.from_postcode,
                "from_area": coverage.from_area,
                "unmatched": coverage.unmatched,
            }
        ),
        "graph": asdict(provenance),
    }
    manifest_path = out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    click.echo(f"wrote {out} and {manifest_path}", err=True)


@main.command()
@inline_key_option
@click.option(
    "--graph",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--epsilon", required=True, type=float)
@click.option("--radius", type=int, default=None)
@click.option("--postcode", default=None, help="Report on one postcode.")
@click.option("--sample", type=int, default=None, help="Report on N random postcodes.")
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def report(
    graph: Path,
    epsilon: float,
    radius: int | None,
    postcode: str | None,
    sample: int | None,
    seed: int,
    as_json: bool,
) -> None:
    """Show what an epsilon actually does, before you release anything."""
    if (postcode is None) == (sample is None):
        raise click.UsageError("give exactly one of --postcode POSTCODE or --sample N.")

    mechanism = HopMechanism(load_graph(graph), epsilon=epsilon, radius=radius)

    if postcode is not None:
        try:
            summary = displacement_summary(mechanism, postcode)
        except (UnknownPostcodeError, LargeUserPostcodeError) as error:
            # The postcode came from this command line, not from a dataset, so
            # repeating it here leaks nothing the operator did not just type.
            raise click.ClickException(str(error)) from error
        payload = {
            "postcode": summary.postcode,
            "epsilon": epsilon,
            "radius": mechanism.radius,
            "self_probability": summary.self_probability,
            "teleport_probability": summary.teleport_probability,
            "ball_size": summary.ball_size,
            "mean_km": summary.mean_km,
            "median_km": summary.median_km,
            "p95_km": summary.p95_km,
        }
        text = (
            f"{summary.postcode} at epsilon {epsilon} per hop, "
            f"radius {mechanism.radius} hops\n"
            f"  displacement: median {summary.median_km:.2f} km, "
            f"p95 {summary.p95_km:.2f} km, mean {summary.mean_km:.2f} km\n"
            f"  self probability: {summary.self_probability:.3%} "
            "(chance the true postcode is handed back)\n"
            f"  teleport probability: {summary.teleport_probability:.2g}\n"
            f"  ball size: {summary.ball_size:,} postcodes\n"
            "  displacement excludes teleports, which are counted separately."
        )
    elif sample is not None:
        summaries = []
        for chosen in sample_postcodes(mechanism.graph, size=sample, seed=seed):
            summaries.append(displacement_summary(mechanism, chosen))
            mechanism.clear_cache()
        medians = [s.median_km for s in summaries]
        payload = {
            "epsilon": epsilon,
            "radius": mechanism.radius,
            "sample_size": len(summaries),
            "seed": seed,
            "median_km": float(np.median(medians)),
            "p95_km": float(np.quantile(medians, 0.95)),
            "max_km": float(np.max(medians)),
            "max_self_probability": max(s.self_probability for s in summaries),
            "max_teleport_probability": max(s.teleport_probability for s in summaries),
        }
        text = (
            f"{len(summaries)} postcodes sampled (seed {seed}) at epsilon "
            f"{epsilon} per hop, radius {mechanism.radius} hops\n"
            f"  median displacement: {payload['median_km']:.2f} km "
            f"(p95 {payload['p95_km']:.2f}, max {payload['max_km']:.2f})\n"
            f"  worst self probability: {payload['max_self_probability']:.3%}\n"
            f"  worst teleport probability: "
            f"{payload['max_teleport_probability']:.2g}\n"
            "  spread is reported because a national average hides exactly the\n"
            "  urban/rural disparity this design exists to address."
        )

    click.echo(json.dumps(payload, indent=2) if as_json else text)


@main.command(name="calibrate")
@inline_key_option
@click.option(
    "--graph",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--target", required=True, help="What to solve for.")
@click.option("--value", required=True, type=float, help="The value to hit.")
@click.option(
    "--sample",
    type=int,
    default=16,
    show_default=True,
    help="Postcodes to solve against. Cost scales with this; 16 takes minutes "
    "on a national graph, 64 takes well over an hour.",
)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def calibrate_command(
    graph: Path, target: str, value: float, sample: int, seed: int, as_json: bool
) -> None:
    """Solve for the epsilon that meets a utility or privacy target."""
    try:
        result = calibrate(
            load_graph(graph),
            target=target,
            value=value,
            sample_size=sample,
            seed=seed,
            progress=lambda step, total: click.echo(
                f"  solving: step {step}/{total}", err=True
            ),
        )
    except UnknownTargetError as error:
        raise click.UsageError(str(error)) from error

    payload = asdict(result)
    unreachable = (
        ""
        if result.reached
        else (
            "\n  WARNING: this target is not reachable on this graph. The epsilon\n"
            "  below is the closest the mechanism can get, not the one you asked for."
        )
    )
    text = (
        f"target: {result.target} = {result.requested}{unreachable}\n"
        f"  epsilon: {result.epsilon:.4g} per hop\n"
        f"  achieved: {result.achieved:.4g} (p95 across the sample "
        f"{result.p95:.4g})\n"
        f"  sample: {result.sample_size} postcodes, seed {seed}\n"
        "  this is a property of the sample, not of the country: protection\n"
        "  varies by location, so check --sample on your own population."
    )
    click.echo(json.dumps(payload, indent=2) if as_json else text)
