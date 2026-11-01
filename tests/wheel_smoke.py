"""Run with a fresh wheel[ui] installation: python -I tests/wheel_smoke.py."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import sysconfig
from importlib.resources import files
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import intextum_cli
from intextum_cli.view import Library, build_app


def main() -> None:
    package = Path(intextum_cli.__file__).resolve()
    assert package.is_relative_to(Path(sys.prefix).resolve()), (
        f"Expected a wheel installed in this environment, got {package}"
    )
    executable = "intextum.exe" if sys.platform == "win32" else "intextum"
    cli = Path(sysconfig.get_path("scripts")) / executable
    env = dict(os.environ)
    for name in (
        "INTEXTUM_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "PYTHONPATH",
        "PYTHONHOME",
    ):
        env.pop(name, None)

    with TemporaryDirectory(prefix="intextum-wheel-smoke-") as temporary:
        root = Path(temporary)

        def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [str(cli), *args],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result

        assert run_cli("--version").stdout.strip() == intextum_cli.__version__
        assert "extract" in run_cli("--help").stdout
        inbox = root / "inbox"
        inbox.mkdir()
        content = "Dear customer, this business letter confirms your order."
        (inbox / "letter.txt").write_text(content, encoding="utf-8")
        schema = root / "letter.yaml"
        schema.write_text("class: Letter\n", encoding="utf-8")
        settings = root / ".env"
        settings.write_text("", encoding="utf-8")
        run_cli("check-schemas", str(schema))
        args = (
            "extract",
            str(inbox),
            "-s",
            str(schema),
            "--class",
            "Letter",
            "--env-file",
            str(settings),
        )
        database = root / "inbox-results.sqlite"
        assert "letter.txt" in run_cli(*args, "--dry-run").stdout
        assert not database.exists()
        assert "1 processed, 0 unchanged" in run_cli(*args).stderr
        assert "0 processed, 1 unchanged" in run_cli(*args).stderr

        exported = root / "export"
        run_cli("export", str(database), "-o", str(exported))
        result = json.loads((exported / "letter.txt.json").read_text(encoding="utf-8"))
        assert result["class"]["name"] == "Letter"
        assert result["status"] == "completed" and result["needs_review"] is False
        assert result["files"] == ["letter.txt"]
        with (exported / "_summary.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1 and rows[0]["class"] == "Letter"

        # Review the copied workspace using its cache after originals are moved.
        portable = root / "portable.sqlite"
        copy2(database, portable)
        inbox.rename(root / "originals-moved")
        library = Library(portable)
        assert library.input_dir is None
        static = files("intextum_cli").joinpath("static")
        notices = static.joinpath("vendor/LICENSES.txt").read_text(encoding="utf-8")
        assert "@docling/docling-components" in notices
        assert "@docling/docling-core" in notices
        with TestClient(build_app(library)) as client:
            response = client.get("/")
            assert response.status_code == 200 and "Document review" in response.text
            for asset, route in (
                ("review.css", "/review.css"),
                ("document.css", "/document.css"),
                ("document-viewer.html", "/document-viewer"),
                ("document-viewer.js", "/document-viewer.js"),
                ("vendor/docling-components.js", "/vendor/docling-components.js"),
            ):
                data = static.joinpath(asset).read_bytes()
                response = client.get(route)
                assert data and response.status_code == 200, asset
                assert response.content == data, asset
            index = client.get("/api/index").json()
            assert len(index["groups"]) == 1
            slug = index["groups"][0]["slug"]
            assert client.get(f"/api/group/{slug}").json() == result
            params = {"file": "letter.txt", "group": slug}
            text = client.get("/api/text", params=params).json()
            assert text["cached"] and text["pages"] == [content]
            status = client.get("/api/document", params=params).json()
            assert status["status"] == "ready" and not status["can_build"]
            response = client.get(
                "/api/document/html", params={**params, "key": status["key"]}
            )
            assert response.status_code == 200 and content in response.text
    print("Installed-wheel CLI, portable workspace, and viewer smoke checks passed.")


if __name__ == "__main__":
    main()
