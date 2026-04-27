#!/usr/bin/env python3
"""
Secret 安全检测脚本 — 扫描代码库中的潜在敏感信息泄露。

检查项：
- 硬编码密码 / API Key / Token
- 默认 JWT secret 未修改
- .env 文件是否被 git 跟踪
- 数据库 URL 中是否包含明文密码

用法：
    python scripts/check_secrets.py
    python scripts/check_secrets.py --strict  # 严格模式（发现即退出码 1）
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

# 敏感模式（正则）
_SENSITIVE_PATTERNS = [
    (r'password\s*=\s*["\'][^"\']{4,}["\']', "hardcoded_password"),
    (r'api_key\s*=\s*["\'][^"\']{8,}["\']', "hardcoded_api_key"),
    (r'apikey\s*=\s*["\'][^"\']{8,}["\']', "hardcoded_api_key"),
    (r'token\s*=\s*["\'][^"\']{8,}["\']', "hardcoded_token"),
    (r'sk-[a-zA-Z0-9]{20,}', "openai_secret_key"),
    (r'AKID[a-zA-Z0-9]{16,}', "tencent_api_key"),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "private_key"),
]

# 排除路径
_EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", "venv", ".claude"}
_EXCLUDE_FILES = {"check_secrets.py", "PAPER_VS_LIVE_CONSISTENCY.md", "smoke_mysql.py"}

_DEFAULT_JWT_SECRET = "trading-buddy-dev-secret-change-in-production"


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """扫描单个文件，返回 (行号, 匹配文本, 类型) 列表。"""
    findings: list[tuple[int, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for line_no, line in enumerate(content.splitlines(), 1):
        for pattern, label in _SENSITIVE_PATTERNS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                # 排除注释行和打印行
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                if "print(" in stripped or "logger." in stripped:
                    continue
                # 排除环境变量读取
                if "os.environ" in stripped or "os.getenv" in stripped:
                    continue
                findings.append((line_no, match.group(0), label))

    return findings


def _check_env_files() -> list[str]:
    """检查 .env 文件是否被 git 跟踪。"""
    findings: list[str] = []
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return findings

    env_files = list(project_root.glob("**/.env")) + list(project_root.glob("**/.env.*"))
    for f in env_files:
        if f.name == ".env.example" or f.name == ".env.development":
            continue
        # 检查是否被 git 跟踪
        rel = f.relative_to(project_root)
        result = os.system(f'cd "{project_root}" && git check-ignore -q "{rel}" 2>/dev/null')
        if result != 0:
            findings.append(f"{rel} 被 git 跟踪 — 应将 .env 加入 .gitignore")

    return findings


def _check_jwt_secret() -> list[str]:
    """检查 JWT 默认密钥。"""
    findings: list[str] = []
    config_file = project_root / "src" / "common" / "config.py"
    if config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        if _DEFAULT_JWT_SECRET in content:
            findings.append(
                f"src/common/config.py 仍在使用默认 JWT secret — "
                f"生产环境必须设置 JWT_SECRET 环境变量"
            )
    return findings


def _check_database_url() -> list[str]:
    """检查环境变量中是否有明文数据库密码。"""
    findings: list[str] = []
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and "://" in db_url:
        # 检查 URL 中是否包含密码
        from urllib.parse import urlparse
        try:
            parsed = urlparse(db_url)
            if parsed.password and len(parsed.password) > 3:
                findings.append(
                    "DATABASE_URL 环境变量包含明文密码 — "
                    "建议使用 Secret Manager 或连接字符串加密"
                )
        except Exception:
            pass
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Secret 安全检测")
    parser.add_argument("--strict", action="store_true", help="严格模式：发现问题时返回非零退出码")
    args = parser.parse_args()

    print("=" * 60)
    print("Secret 安全检测")
    print("=" * 60)

    total_findings = 0

    # 1. 扫描代码文件
    print("\n[1/4] 扫描代码文件中的敏感信息...")
    file_findings = 0
    for root, dirs, files in os.walk(project_root):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        for fname in files:
            if fname in _EXCLUDE_FILES:
                continue
            if not fname.endswith((".py", ".js", ".ts", ".vue", ".json", ".yml", ".yaml", ".sh", ".md")):
                continue
            fpath = Path(root) / fname
            findings = _scan_file(fpath)
            if findings:
                rel = fpath.relative_to(project_root)
                print(f"\n  {rel}")
                for line_no, text, label in findings:
                    print(f"    行 {line_no}: [{label}] {text[:60]}")
                    file_findings += 1
    print(f"  发现 {file_findings} 处潜在敏感信息")
    total_findings += file_findings

    # 2. 检查 .env 文件
    print("\n[2/4] 检查 .env 文件是否被 git 跟踪...")
    env_findings = _check_env_files()
    for msg in env_findings:
        print(f"  [WARN] {msg}")
    total_findings += len(env_findings)

    # 3. 检查 JWT 默认密钥
    print("\n[3/4] 检查 JWT 默认密钥...")
    jwt_findings = _check_jwt_secret()
    for msg in jwt_findings:
        print(f"  [WARN] {msg}")
    total_findings += len(jwt_findings)

    # 4. 检查数据库 URL
    print("\n[4/4] 检查数据库 URL 密码...")
    db_findings = _check_database_url()
    for msg in db_findings:
        print(f"  [WARN] {msg}")
    total_findings += len(db_findings)

    print("\n" + "=" * 60)
    if total_findings == 0:
        print("[OK] 未发现明显敏感信息泄露")
        return 0
    else:
        print(f"[WARN] 共发现 {total_findings} 处潜在问题")
        if args.strict:
            print("   （严格模式：返回退出码 1）")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
