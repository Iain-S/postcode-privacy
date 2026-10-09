"""The build command: ONSPD in, graph artefact out."""

import json
from pathlib import Path

from click.testing import CliRunner, Result

from postcode_privacy import load_graph
from postcode_privacy.cli import main

HEADER = "pcds,doterm,east1m,north1m,usrtypind,oa21cd,lat,long"


def _with_coords(row: str) -> str:
    """Append latitude and longitude consistent with the row's grid reference.

    Derived rather than written by hand, so a fixture cannot drift from the
    invariant the reader now enforces: a grid reference must agree with its own
    coordinates. Fixtures encoding a wrong assumption is the failure mode this
    repository watches for.
    """
    from pyproj import Transformer

    fields = row.split(",")
    easting, northing = fields[2].strip(), fields[3].strip()
    if not easting or not northing:
        return row + ",,"
    to_wgs84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    longitude, latitude = to_wgs84.transform(float(easting), float(northing))
    return f"{row},{latitude:.6f},{longitude:.6f}"


# Nine postcodes spread out enough to triangulate, one terminated, one large
# user, so the build exercises every exclusion path at once.
ROWS = [
    "AA1 1AA,,100,100,0,E00000001",
    "AA1 1AB,,200,140,0,E00000001",
    "AA1 1AC,,160,260,0,E00000002",
    "AA1 1AD,,320,120,0,E00000002",
    "AA1 1AE,,280,300,0,E00000003",
    "AA1 1AF,,420,220,0,E00000003",
    "AA1 1AG,,380,400,0,E00000003",
    "AA1 1AH,,520,160,1,E00000003",
    "AA1 1AJ,201907,540,480,0,E00000003",
    "BT1 1AA,,600,600,0,N00000001",
]


def onspd(tmp_path: Path) -> Path:
    path = tmp_path / "onspd.csv"
    path.write_text("\n".join([HEADER, *(_with_coords(r) for r in ROWS)]) + "\n")
    return path


def areas(tmp_path: Path) -> Path:
    path = tmp_path / "areas.csv"
    path.write_text(
        "code,population\nE00000001,200\nE00000002,300\nE00000003,400\nN00000001,150\n"
    )
    return path


def run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


def test_it_builds_an_artefact_that_loads(tmp_path: Path) -> None:
    out = tmp_path / "test.ppg"

    result = run(
        ["build", "--onspd", str(onspd(tmp_path)), "--oa-populations",
         str(areas(tmp_path)), "-o", str(out)]
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    graph = load_graph(out)
    # Nine live rows, minus the large user, minus the terminated one.
    assert graph.n_nodes == 8
    assert "AA1 1AJ" not in graph  # terminated
    assert "AA1 1AH" not in graph  # large user


def test_the_source_hash_is_recorded_so_a_release_can_be_traced(
    tmp_path: Path,
) -> None:
    import hashlib

    source = onspd(tmp_path)
    out = tmp_path / "test.ppg"

    run(["build", "--onspd", str(source), "--oa-populations",
         str(areas(tmp_path)), "-o", str(out)])  # fmt: skip

    provenance = load_graph(out).provenance
    assert provenance is not None
    assert provenance.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert provenance.source == source.name


def test_gb_only_excludes_northern_ireland(tmp_path: Path) -> None:
    # ONSPD's Northern Ireland records may not be redistributed, so an artefact
    # intended for sharing must be buildable without them.
    out = tmp_path / "gb.ppg"

    run(["build", "--onspd", str(onspd(tmp_path)), "--oa-populations",
         str(areas(tmp_path)), "--gb-only", "-o", str(out)])  # fmt: skip

    graph = load_graph(out)
    assert "BT1 1AA" not in graph
    assert graph.provenance is not None
    assert graph.provenance.gb_only is True


def test_it_reports_what_was_dropped_and_where_the_prior_came_from(
    tmp_path: Path,
) -> None:
    # Coverage must be visible. A prior that silently fell back to the floor
    # across a whole nation looks exactly like a working one.
    result = run(
        ["build", "--onspd", str(onspd(tmp_path)), "--oa-populations",
         str(areas(tmp_path)), "-o", str(tmp_path / "t.ppg")]
    )  # fmt: skip

    for expected in ["terminated", "large user", "prior", "coverage"]:
        assert expected in result.output.lower(), result.output


def test_a_build_manifest_is_written_beside_the_artefact(tmp_path: Path) -> None:
    out = tmp_path / "test.ppg"

    run(["build", "--onspd", str(onspd(tmp_path)), "--oa-populations",
         str(areas(tmp_path)), "-o", str(out)])  # fmt: skip

    manifest = json.loads((tmp_path / "test.manifest.json").read_text())
    assert manifest["nodes"] == 8
    assert manifest["edges"] > 0
    assert manifest["dropped"]["terminated"] == 1
    assert manifest["large_user_excluded"] == 1
    assert manifest["prior"]["from_area"] == 8
    assert manifest["prior"]["unmatched"] == 0


def test_without_population_sources_it_refuses_unless_uniform_is_asked_for(
    tmp_path: Path,
) -> None:
    # Falling back silently would ship a uniform prior that looks population
    # weighted, so the fallback has to be requested.
    args = ["build", "--onspd", str(onspd(tmp_path)), "-o", str(tmp_path / "t.ppg")]

    refused = run(args)

    # Asserting only on a non-zero exit was not enough: with the CLI's own
    # guard removed, the library raised its own error and the test still
    # passed, so the actionable message could have vanished unnoticed. A
    # mutant survived on exactly that.
    assert refused.exit_code != 0
    assert "--uniform-prior" in refused.output
    assert refused.exception is None or isinstance(refused.exception, SystemExit)
    assert run([*args, "--uniform-prior"]).exit_code == 0


def test_it_refuses_to_overwrite_an_existing_artefact(tmp_path: Path) -> None:
    out = tmp_path / "test.ppg"
    out.write_bytes(b"existing")

    result = run(["build", "--onspd", str(onspd(tmp_path)), "--uniform-prior",
                  "-o", str(out)])  # fmt: skip

    assert result.exit_code != 0
    assert out.read_bytes() == b"existing"


def test_fetch_and_onspd_are_mutually_exclusive(tmp_path: Path) -> None:
    result = run(["build", "--onspd", str(onspd(tmp_path)), "--fetch",
                  "--uniform-prior", "-o", str(tmp_path / "t.ppg")])  # fmt: skip

    assert result.exit_code != 0
    assert "--fetch" in result.output


def test_one_of_fetch_or_onspd_is_required(tmp_path: Path) -> None:
    result = run(["build", "--uniform-prior", "-o", str(tmp_path / "t.ppg")])

    assert result.exit_code != 0
    assert "--onspd" in result.output


def test_the_manifest_carries_the_required_attributions(tmp_path: Path) -> None:
    # Not decoration: the ONSPD User Guide requires these statements to be
    # displayed whenever the data is used, so they travel with any artefact
    # rather than depending on someone remembering to copy them.
    out = tmp_path / "test.ppg"

    run(["build", "--onspd", str(onspd(tmp_path)), "--uniform-prior",
         "-o", str(out)])  # fmt: skip

    manifest = json.loads((tmp_path / "test.manifest.json").read_text())
    attribution = " ".join(manifest["attribution"])
    assert "Crown copyright" in attribution
    assert "Royal Mail" in attribution
    assert "Open Government Licence" in attribution


def test_the_manifest_hashes_every_population_input(tmp_path: Path) -> None:
    """Name, role and hash, because none of the three is implied by the others.

    Two census releases can share a filename, and the same file read per area
    rather than per postcode gives a different prior. Either difference changes
    every subject's output, so either has to be visible in the manifest.
    """
    out = tmp_path / "test.ppg"

    run(
        [
            "build",
            "--onspd",
            str(onspd(tmp_path)),
            "--oa-populations",
            str(areas(tmp_path)),
            "-o",
            str(out),
        ]
    )
    manifest = json.loads((tmp_path / "test.manifest.json").read_text())

    sources = manifest["graph"]["population_sources"]
    assert len(sources) == 1
    assert sources[0]["name"] == "areas.csv"
    assert sources[0]["role"] == "area"
    assert len(sources[0]["sha256"]) == 64
    assert manifest["graph"]["prior_kind"] == "population"
    assert set(manifest["graph"]["build_dependencies"]) == {
        "numpy",
        "scipy",
        "pyproj",
    }
    assert len(manifest["artefact_sha256"]) == 64


def test_two_priors_over_one_onspd_produce_distinguishable_manifests(
    tmp_path: Path,
) -> None:
    """The failure this all exists for, end to end.

    The two artefacts share an ONSPD hash and every build flag, and they give
    every subject a different output. If their manifests matched, a release made
    from one could not be told from a release made from the other.
    """
    source = onspd(tmp_path)
    populated = tmp_path / "populated.ppg"
    uniform = tmp_path / "uniform.ppg"

    run(
        [
            "build",
            "--onspd",
            str(source),
            "--oa-populations",
            str(areas(tmp_path)),
            "-o",
            str(populated),
        ]
    )
    run(["build", "--onspd", str(source), "--uniform-prior", "-o", str(uniform)])

    first = json.loads((tmp_path / "populated.manifest.json").read_text())["graph"]
    second = json.loads((tmp_path / "uniform.manifest.json").read_text())["graph"]

    assert first["source_sha256"] == second["source_sha256"]
    assert first != second
    assert (first["prior_kind"], second["prior_kind"]) == ("population", "uniform")
