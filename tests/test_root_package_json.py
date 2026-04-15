"""仓库根 `package.json`、前端 `frontend/package.json` 与 CI/元文件契约（防误删；不执行 npm）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT_NPM_PREFIX_RUN = re.compile(
    r"npm\s+--prefix\s+frontend\s+run\s+(\S+)",
    flags=re.IGNORECASE,
)
_CI_NPM_RUN = re.compile(r"npm\s+run\s+(\S+)", flags=re.IGNORECASE)

ROOT = Path(__file__).resolve().parent.parent


def _load_frontend_package() -> dict:
    path = ROOT / "frontend" / "package.json"
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def _load_root_package() -> dict:
    path = ROOT / "package.json"
    assert path.is_file(), "expected repo-root package.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_root_package_json_verify_and_frontend_shims():
    pkg = _load_root_package()
    assert pkg.get("private") is True
    assert pkg.get("license") == "MIT"
    engines = pkg.get("engines") or {}
    assert "20" in str(engines.get("node", "")), engines

    scripts = pkg.get("scripts") or {}
    required = (
        "verify",
        "verify:pytest",
        "verify:frontend",
        "frontend:install",
        "frontend:dev",
        "frontend:build",
        "frontend:preview",
        "frontend:e2e",
        "frontend:e2e:chromium",
        "frontend:e2e:chrome",
        "frontend:e2e:smoke",
        "frontend:e2e:smoke:connected",
        "frontend:e2e:connected",
        "frontend:e2e:connected:chromium",
        "frontend:e2e:connected:chrome",
        "frontend:e2e:ui",
        "frontend:e2e:ui:chromium",
        "frontend:e2e:ui:chrome",
        "frontend:e2e:ui:connected",
        "frontend:e2e:ui:connected:chromium",
        "frontend:e2e:ui:connected:chrome",
        "frontend:e2e:preview",
        "frontend:e2e:preview:only",
        "frontend:e2e:diag-import",
    )
    req_set = frozenset(required)
    act_set = frozenset(scripts)
    assert act_set == req_set, (
        "root package.json `scripts` keys must exactly match the contract tuple "
        f"(no extras, no omissions). extra={sorted(act_set - req_set)} "
        f"missing={sorted(req_set - act_set)}"
    )

    assert "npm --prefix frontend run build" in scripts["verify:frontend"]
    assert "python -m pytest -q" in scripts["verify:pytest"]
    assert "pytest" in scripts["verify"] and "frontend" in scripts["verify"]


def test_root_scripts_that_invoke_frontend_run_target_existing_scripts():
    """根目录 `npm --prefix frontend run <name>` 中的 `<name>` 须在 frontend/package.json 存在。"""
    root_scripts = (_load_root_package().get("scripts") or {})
    fe_scripts = (_load_frontend_package().get("scripts") or {})
    for key, cmd in root_scripts.items():
        if not isinstance(cmd, str):
            continue
        for m in _ROOT_NPM_PREFIX_RUN.finditer(cmd):
            target = m.group(1)
            assert target in fe_scripts, (
                f"root scripts[{key!r}] invokes npm --prefix frontend run {target!r}, "
                f"but frontend/package.json has no scripts[{target!r}]"
            )


def test_root_frontend_install_is_npm_prefix_install():
    cmd = str((_load_root_package().get("scripts") or {}).get("frontend:install", "")).strip()
    assert re.fullmatch(
        r"npm\s+--prefix\s+frontend\s+install",
        cmd,
        flags=re.IGNORECASE,
    ), f"expected frontend:install to be `npm --prefix frontend install`, got {cmd!r}"


def test_ci_workflow_reads_python_and_node_version_files():
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python-version-file" in yml and ".python-version" in yml
    assert "node-version-file" in yml and ".nvmrc" in yml


def test_ci_playwright_job_uses_preview_and_e2e_script():
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "PLAYWRIGHT_BASE_URL" in yml
    assert "npm run test:e2e" in yml
    assert "vite preview" in yml
    assert "cache-dependency-path: frontend/package-lock.json" in yml


def test_ci_yml_npm_run_scripts_exist_in_package_json():
    """`.github/workflows/ci.yml` 中出现的 `npm run <name>` 须在 frontend 或仓库根 package.json 有对应 scripts。"""
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    fe_scripts = frozenset((_load_frontend_package().get("scripts") or {}).keys())
    root_scripts = frozenset((_load_root_package().get("scripts") or {}).keys())
    names = {m.group(1) for m in _CI_NPM_RUN.finditer(yml)}
    for name in sorted(names):
        assert name in fe_scripts or name in root_scripts, (
            f"ci.yml invokes npm run {name!r} but neither frontend nor root package.json defines scripts[{name!r}]"
        )


def test_dependabot_config_exists():
    path = ROOT / ".github" / "dependabot.yml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "package-ecosystem: \"pip\"" in text
    assert "package-ecosystem: \"npm\"" in text
    assert "directory: \"/frontend\"" in text
    assert 'package-ecosystem: "pip"\n    directory: "/"' in text.replace("\r\n", "\n")


def test_nvmrc_node_major_matches_engines():
    nvmrc = (ROOT / ".nvmrc").read_text(encoding="utf-8").strip()
    assert nvmrc.isdigit()
    assert int(nvmrc) >= 20


def test_nvmrc_major_in_root_and_frontend_engines_node():
    """`.nvmrc` 与根 / 前端 `engines.node` 一致（主版本号须在 range 字符串中出现）。"""
    nvmrc = (ROOT / ".nvmrc").read_text(encoding="utf-8").strip()
    assert nvmrc.isdigit()
    major = nvmrc
    for label, pkg in (("root", _load_root_package()), ("frontend", _load_frontend_package())):
        engines = pkg.get("engines") or {}
        node_spec = str(engines.get("node", ""))
        assert major in node_spec, f"{label} engines.node must mention .nvmrc major {major!r}: {node_spec!r}"


def test_frontend_package_json_license_and_node_engine():
    pkg = _load_frontend_package()
    assert pkg.get("license") == "MIT"
    engines = pkg.get("engines") or {}
    assert "20" in str(engines.get("node", "")), engines


def test_frontend_package_json_scripts_keys_exact():
    scripts = (_load_frontend_package().get("scripts") or {})
    required = (
        "build",
        "dev",
        "e2e:preview",
        "e2e:preview:only",
        "preview",
        "test:e2e",
        "test:e2e:chrome",
        "test:e2e:chromium",
        "test:e2e:connected",
        "test:e2e:connected:chrome",
        "test:e2e:connected:chromium",
        "test:e2e:diag-import",
        "test:e2e:smoke",
        "test:e2e:smoke:connected",
        "test:e2e:ui",
        "test:e2e:ui:chrome",
        "test:e2e:ui:chromium",
        "test:e2e:ui:connected",
        "test:e2e:ui:connected:chrome",
        "test:e2e:ui:connected:chromium",
    )
    req_set = frozenset(required)
    act_set = frozenset(scripts)
    assert act_set == req_set, (
        "frontend/package.json `scripts` keys must exactly match the contract tuple "
        f"(no extras, no omissions). extra={sorted(act_set - req_set)} "
        f"missing={sorted(req_set - act_set)}"
    )


def test_license_is_mit():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright" in text


def test_editorconfig_and_gitattributes_exist():
    ec = (ROOT / ".editorconfig").read_text(encoding="utf-8")
    assert "root = true" in ec
    ga = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "text=auto" in ga
    assert "*.sh" in ga


def test_python_version_file_is_minor_pinned():
    """CI pytest job 使用 setup-python 的 python-version-file 指向本文件。"""
    raw = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert raw.startswith("3.12"), raw
