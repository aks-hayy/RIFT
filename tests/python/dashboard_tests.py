import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from rift import dashboard


def test_dashboard_source_discovery_and_launch_plan():
    root = dashboard.find_dashboard_root(ROOT)
    assert root == (ROOT / "ui").resolve()
    assert dashboard.find_dashboard_root(ROOT / "docs" / "guides") == root
    plan = dashboard.dashboard_launch_plan(
        host="127.0.0.1",
        port=8765,
        control_port=8777,
        dashboard_root=root,
    )
    assert plan.dashboard_url == "http://127.0.0.1:8765"
    assert plan.control_api_url == "http://127.0.0.1:8777"
    assert plan.command[-3:] == ["--control-port", "8777", "--no-browser"]
    assert plan.dashboard_root.endswith("python\\rift\\web\\static") or plan.dashboard_root.endswith(
        "python/rift/web/static"
    )
    assert plan.dependencies_ready is True


def test_bundled_dashboard_has_rift_favicon():
    bundled = ROOT / "python" / "rift" / "web" / "static"
    html = (bundled / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon"' in html
    assert 'href="/rift-mark.svg"' in html
    assert (bundled / "rift-mark.svg").is_file()


def test_rich_dashboard_build_plan_is_detected():
    plan = dashboard.rich_dashboard_plan(ROOT / "ui", port=8766, control_port=8778)
    assert plan is not None
    assert plan["server_script"].endswith("ui\\scripts\\serve-dist.mjs") or plan[
        "server_script"
    ].endswith("ui/scripts/serve-dist.mjs")
    assert plan["client_root"].endswith("ui\\dist\\client") or plan["client_root"].endswith(
        "ui/dist/client"
    )


def test_dashboard_root_environment_override():
    previous = os.environ.get("RIFT_DASHBOARD_ROOT")
    try:
        os.environ["RIFT_DASHBOARD_ROOT"] = str(ROOT / "ui")
        assert dashboard.find_dashboard_root(Path(tempfile.gettempdir())) == (
            ROOT / "ui"
        ).resolve()
    finally:
        if previous is None:
            os.environ.pop("RIFT_DASHBOARD_ROOT", None)
        else:
            os.environ["RIFT_DASHBOARD_ROOT"] = previous


def test_dashboard_validation_errors_are_actionable():
    try:
        dashboard.dashboard_launch_plan(
            port=0, dashboard_root=ROOT / "ui"
        )
    except ValueError as exc:
        assert "between 1 and 65535" in str(exc)
    else:
        raise AssertionError("expected invalid port failure")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            dashboard.dashboard_launch_plan(dashboard_root=tmp)
        except RuntimeError as exc:
            assert "dashboard assets were not found" in str(exc)
        else:
            raise AssertionError("expected missing dashboard failure")


def main():
    test_dashboard_source_discovery_and_launch_plan()
    test_bundled_dashboard_has_rift_favicon()
    test_rich_dashboard_build_plan_is_detected()
    test_dashboard_root_environment_override()
    test_dashboard_validation_errors_are_actionable()
    print("RIFT dashboard launcher tests passed")


if __name__ == "__main__":
    main()
