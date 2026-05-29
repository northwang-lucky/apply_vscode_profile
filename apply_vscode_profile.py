#!/usr/bin/env python3
"""
VS Code Profile 配置应用脚本
将导出的 VS Code profile 配置应用到本地 VS Code / VS Code Insiders

用法:
    python apply_vscode_profile.py <profile_json_path> [--editor code|insiders] [--dry-run]
"""

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_vscode_user_dir(editor="code"):
    """获取 VS Code User 配置目录"""
    system = platform.system()
    home = Path.home()

    if system == "Darwin":  # macOS
        if editor == "insiders":
            return home / "Library" / "Application Support" / "Code - Insiders" / "User"
        return home / "Library" / "Application Support" / "Code" / "User"
    elif system == "Linux":
        if editor == "insiders":
            return home / ".config" / "Code - Insiders" / "User"
        return home / ".config" / "Code" / "User"
    elif system == "Windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        if editor == "insiders":
            return appdata / "Code - Insiders" / "User"
        return appdata / "Code" / "User"
    else:
        raise RuntimeError(f"不支持的操作系统: {system}")


def get_code_cli(editor="code"):
    """获取 VS Code CLI 命令"""
    system = platform.system()
    if editor == "insiders":
        cli_name = "code-insiders"
        if system == "Windows":
            cli_name = "code-insiders.cmd"
    else:
        cli_name = "code"
        if system == "Windows":
            cli_name = "code.cmd"

    # 尝试在 PATH 中查找
    code_path = shutil.which(cli_name)
    if code_path:
        return code_path

    # macOS 尝试默认安装路径
    if system == "Darwin":
        app_name = "Code - Insiders.app" if editor == "insiders" else "Visual Studio Code.app"
        default_path = f"/Applications/{app_name}/Contents/Resources/app/bin/{cli_name}"
        if Path(default_path).exists():
            return default_path

    return None


def clean_jsonc(jsonc_str):
    """将 JSONC (带注释/尾逗号的 JSON) 转换为标准 JSON"""
    result = []
    i = 0
    length = len(jsonc_str)

    # 状态: NORMAL, IN_STRING, ESCAPE, LINE_COMMENT, BLOCK_COMMENT
    NORMAL = 0
    IN_STRING = 1
    ESCAPE = 2
    LINE_COMMENT = 3
    BLOCK_COMMENT = 4

    state = NORMAL

    while i < length:
        ch = jsonc_str[i]
        next_ch = jsonc_str[i + 1] if i + 1 < length else ""

        if state == NORMAL:
            if ch == '"':
                state = IN_STRING
                result.append(ch)
            elif ch == "/" and next_ch == "/":
                state = LINE_COMMENT
                i += 1
            elif ch == "/" and next_ch == "*":
                state = BLOCK_COMMENT
                i += 1
            else:
                result.append(ch)

        elif state == IN_STRING:
            if ch == "\\":
                state = ESCAPE
                result.append(ch)
            elif ch == '"':
                state = NORMAL
                result.append(ch)
            else:
                result.append(ch)

        elif state == ESCAPE:
            result.append(ch)
            state = IN_STRING

        elif state == LINE_COMMENT:
            if ch == "\n":
                state = NORMAL
                result.append(ch)

        elif state == BLOCK_COMMENT:
            if ch == "*" and next_ch == "/":
                state = NORMAL
                i += 1

        i += 1

    text = "".join(result)

    # 移除尾逗号 (trailing commas)
    def remove_trailing_commas(s):
        result = []
        in_string = False
        escape = False

        for i, ch in enumerate(s):
            if escape:
                result.append(ch)
                escape = False
                continue

            if ch == "\\" and in_string:
                result.append(ch)
                escape = True
                continue

            if ch == '"' and not in_string:
                in_string = True
                result.append(ch)
            elif ch == '"' and in_string:
                in_string = False
                result.append(ch)
            elif not in_string and ch == ",":
                j = i + 1
                while j < len(s) and s[j] in " \t\n\r":
                    j += 1
                if j < len(s) and s[j] in "}]":
                    continue
                else:
                    result.append(ch)
            else:
                result.append(ch)

        return "".join(result)

    return remove_trailing_commas(text)


def parse_json_nested(data):
    """解析可能嵌套多层转义的 JSON"""
    if isinstance(data, str):
        cleaned = clean_jsonc(data)
        return json.loads(cleaned)
    return data


def backup_file(file_path):
    """备份文件，如果不存在则跳过"""
    if not file_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(str(file_path) + f".backup.{timestamp}")
    shutil.copy2(file_path, backup_path)
    return backup_path


def parse_profile(profile_path):
    """解析导出的 profile JSON 文件"""
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    result = {}

    # 解析 settings
    if "settings" in profile and profile["settings"]:
        settings_raw = json.loads(profile["settings"])
        if isinstance(settings_raw, dict) and "settings" in settings_raw:
            result["settings"] = parse_json_nested(settings_raw["settings"])
        elif isinstance(settings_raw, str):
            result["settings"] = parse_json_nested(settings_raw)
        else:
            result["settings"] = settings_raw

    # 解析 keybindings
    if "keybindings" in profile and profile["keybindings"]:
        kb_raw = json.loads(profile["keybindings"])
        if isinstance(kb_raw, dict) and "keybindings" in kb_raw:
            result["keybindings"] = parse_json_nested(kb_raw["keybindings"])
        elif isinstance(kb_raw, str):
            result["keybindings"] = parse_json_nested(kb_raw)
        else:
            result["keybindings"] = kb_raw

    # 解析 extensions
    if "extensions" in profile and profile["extensions"]:
        ext_raw = profile["extensions"]
        if isinstance(ext_raw, str):
            result["extensions"] = json.loads(ext_raw)
        else:
            result["extensions"] = ext_raw

    # 解析 globalState
    if "globalState" in profile and profile["globalState"]:
        gs_raw = json.loads(profile["globalState"])
        if isinstance(gs_raw, dict) and "storage" in gs_raw:
            result["globalState"] = gs_raw["storage"]
        elif isinstance(gs_raw, dict):
            result["globalState"] = gs_raw
        elif isinstance(gs_raw, str):
            parsed = json.loads(gs_raw)
            if isinstance(parsed, dict) and "storage" in parsed:
                result["globalState"] = parsed["storage"]
            else:
                result["globalState"] = parsed

    return result


def apply_settings(settings_data, user_dir, dry_run=False):
    """应用 settings 到 settings.json"""
    settings_file = user_dir / "settings.json"

    print(f"\n{'[模拟] ' if dry_run else ''}应用 settings...")
    print(f"  目标文件: {settings_file}")

    if dry_run:
        settings_json = json.dumps(settings_data, indent=2, ensure_ascii=False)
        print(f"  将写入 {len(settings_json)} 字符，{len(settings_data)} 个配置项")
        return True

    backup = backup_file(settings_file)
    if backup:
        print(f"  已备份: {backup.name}")

    user_dir.mkdir(parents=True, exist_ok=True)
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings_data, f, indent=2, ensure_ascii=False)

    print("  ✓ settings.json 已更新")
    return True


def apply_keybindings(kb_data, user_dir, dry_run=False):
    """应用 keybindings 到 keybindings.json"""
    kb_file = user_dir / "keybindings.json"

    print(f"\n{'[模拟] ' if dry_run else ''}应用 keybindings...")
    print(f"  目标文件: {kb_file}")

    if dry_run:
        print(f"  将写入 {len(kb_data)} 条快捷键")
        return True

    backup = backup_file(kb_file)
    if backup:
        print(f"  已备份: {backup.name}")

    # 保留 VS Code keybindings 格式（带注释头）
    lines = []
    lines.append("// 将键绑定放在此文件中以覆盖默认值")
    lines.append("[")
    for i, item in enumerate(kb_data):
        json_str = json.dumps(item, indent=2, ensure_ascii=False)
        indented = "\n".join("  " + line for line in json_str.split("\n"))
        if i < len(kb_data) - 1:
            # 检查最后是否已经有逗号
            if not indented.rstrip().endswith(","):
                indented = indented.rstrip() + ","
        lines.append(indented)
    lines.append("]")

    user_dir.mkdir(parents=True, exist_ok=True)
    with open(kb_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  ✓ keybindings.json 已更新 ({len(kb_data)} 条快捷键)")
    return True


def apply_global_state(gs_data, user_dir, dry_run=False):
    """
    应用 globalState 到 state.vscdb (SQLite)
    VS Code 的 globalState 存储在 User/globalStorage/state.vscdb
    """
    gs_dir = user_dir / "globalStorage"
    state_file = gs_dir / "state.vscdb"

    print(f"\n{'[模拟] ' if dry_run else ''}应用 globalState...")
    print(f"  目标文件: {state_file}")

    if dry_run:
        print(f"  将写入 {len(gs_data)} 个状态项")
        return True

    gs_dir.mkdir(parents=True, exist_ok=True)

    backup = backup_file(state_file)
    if backup:
        print(f"  已备份: {backup.name}")

    # 连接/创建 SQLite 数据库
    conn = sqlite3.connect(str(state_file))
    cursor = conn.cursor()

    # 创建表（如果不存在）
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ItemTable (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """
    )

    # 插入/更新数据
    inserted = 0
    updated = 0
    for key, value in gs_data.items():
        value_str = (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )

        cursor.execute("SELECT 1 FROM ItemTable WHERE key = ?", (key,))
        exists = cursor.fetchone() is not None

        if exists:
            cursor.execute(
                "UPDATE ItemTable SET value = ? WHERE key = ?", (value_str, key)
            )
            updated += 1
        else:
            cursor.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)", (key, value_str)
            )
            inserted += 1

    conn.commit()
    conn.close()

    print(f"  ✓ globalState 已更新 (新增 {inserted} 项, 更新 {updated} 项)")
    return True


def apply_extensions(ext_data, editor="code", dry_run=False):
    """安装 extensions（包括禁用的），并按 profile 标记禁用状态"""
    print(f"\n{'[模拟] ' if dry_run else ''}应用 extensions...")

    code_cli = get_code_cli(editor)
    if not code_cli:
        print(f"  ⚠ 未找到 {editor} CLI 命令，跳过扩展安装")
        print(f"  提示: 请确保 VS Code 已安装并在 PATH 中")
        return False

    print(f"  使用 CLI: {code_cli}")

    # 获取已安装的扩展列表
    try:
        result = subprocess.run(
            [code_cli, "--list-extensions"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        installed = set(
            line.strip().lower()
            for line in result.stdout.strip().split("\n")
            if line.strip()
        )
    except Exception as e:
        print(f"  ⚠ 获取已安装扩展列表失败: {e}")
        installed = set()

    # 分类：需要安装的、需要禁用的
    to_install = []       # (ext_id, display_name, disabled)
    to_disable = []       # (ext_id, display_name)
    already_ok = []       # (ext_id, display_name)

    for ext in ext_data:
        ext_id = ext.get("identifier", {}).get("id", "")
        display_name = ext.get("displayName", ext_id)
        disabled = ext.get("disabled", False)

        if not ext_id:
            continue

        # 跳过 GitHub Copilot Chat
        if ext_id.lower() == "github.copilot-chat":
            print(f"  - [{display_name}] 已跳过（默认排除）")
            continue

        is_installed = ext_id.lower() in installed

        if is_installed:
            if disabled:
                # 已安装但需要禁用（可能当前是启用的）
                to_disable.append((ext_id, display_name))
                print(f"  - [{display_name}] 已安装，将禁用")
            else:
                already_ok.append((ext_id, display_name))
                print(f"  - [{display_name}] 已安装且启用")
        else:
            # 未安装，需要安装（包括禁用的）
            to_install.append((ext_id, display_name, disabled))
            action = "安装并禁用" if disabled else "安装"
            print(f"  - [{display_name}] 未安装，将{action}")

    if dry_run:
        print(f"\n  摘要: {len(to_install)} 个待安装, {len(to_disable)} 个待禁用, {len(already_ok)} 个已就绪")
        return True

    # ---- 安装阶段 ----
    install_success = 0
    install_failed = 0

    if to_install:
        print(f"\n  开始安装 {len(to_install)} 个扩展...")
        for ext_id, display_name, disabled in to_install:
            action = "安装" if not disabled else "安装(将禁用)"
            print(f"  {action}: {display_name} ...", end=" ", flush=True)
            try:
                result = subprocess.run(
                    [code_cli, "--install-extension", ext_id, "--force"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    print("✓")
                    install_success += 1
                    if disabled:
                        to_disable.append((ext_id, display_name))
                else:
                    print(f"✗ (exit {result.returncode})")
                    if result.stderr:
                        print(f"    错误: {result.stderr.strip()[:200]}")
                    install_failed += 1
            except subprocess.TimeoutExpired:
                print("✗ (超时)")
                install_failed += 1
            except Exception as e:
                print(f"✗ ({e})")
                install_failed += 1

    # ---- 禁用阶段 ----
    disable_success = 0
    disable_failed = 0

    if to_disable:
        print(f"\n  开始禁用 {len(to_disable)} 个扩展...")
        for ext_id, display_name in to_disable:
            print(f"  禁用: {display_name} ...", end=" ", flush=True)
            try:
                result = subprocess.run(
                    [code_cli, "--disable-extension", ext_id],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    print("✓")
                    disable_success += 1
                else:
                    # 可能已经禁用了，非致命错误
                    err = result.stderr.strip() if result.stderr else ""
                    if "already disabled" in err.lower() or "not installed" in err.lower():
                        print("✓ (已是禁用状态)")
                        disable_success += 1
                    else:
                        print(f"⚠ ({err[:100]})")
                        disable_failed += 1
            except Exception as e:
                print(f"⚠ ({e})")
                disable_failed += 1

    print(
        f"\n  ✓ 扩展处理完成 "
        f"(安装成功 {install_success}, 安装失败 {install_failed}, "
        f"禁用成功 {disable_success}, 禁用失败 {disable_failed}, "
        f"已就绪 {len(already_ok)})"
    )
    return install_failed == 0 and disable_failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="将 VS Code 导出的 profile 配置应用到本地 VS Code/Insiders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python apply_vscode_profile.py ./my-profile.code-profile
  python apply_vscode_profile.py ./my-profile.code-profile --editor insiders
  python apply_vscode_profile.py ./my-profile.code-profile --dry-run
  python apply_vscode_profile.py ./my-profile.code-profile --apply settings,keybindings
  python apply_vscode_profile.py ./my-profile.code-profile --apply extensions
        """,
    )
    parser.add_argument("profile", help="导出的 VS Code profile JSON 文件路径")
    parser.add_argument(
        "--editor",
        choices=["code", "insiders"],
        default="code",
        help="目标编辑器 (默认: code)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，显示将要执行的操作但不实际写入",
    )
    parser.add_argument(
        "--apply",
        default="settings,keybindings,extensions,globalState",
        help="指定要应用的配置项，逗号分隔 (默认: settings,keybindings,extensions,globalState)",
    )

    args = parser.parse_args()

    # 解析 --apply 参数
    allowed_items = {
        item.strip().lower()
        for item in args.apply.split(",")
        if item.strip()
    }

    def should_apply(name):
        return name.lower() in allowed_items

    profile_path = Path(args.profile).expanduser().resolve()
    if not profile_path.exists():
        print(f"错误: 配置文件不存在: {profile_path}")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"VS Code Profile 配置应用工具")
    print(f"{'='*60}")
    print(f"配置文件: {profile_path}")
    print(f"目标编辑器: {args.editor}")
    print(f"模拟模式: {'是' if args.dry_run else '否'}")

    # 解析配置文件
    print(f"\n解析配置文件...")
    try:
        parsed = parse_profile(profile_path)
    except Exception as e:
        print(f"解析配置文件失败: {e}")
        sys.exit(1)

    has_settings = "settings" in parsed
    has_keybindings = "keybindings" in parsed
    has_extensions = "extensions" in parsed
    has_global_state = "globalState" in parsed

    settings_size = len(json.dumps(parsed.get("settings", {})))
    kb_count = len(parsed.get("keybindings", []))
    ext_count = len(parsed.get("extensions", []))
    gs_count = len(parsed.get("globalState", {}))

    print(f"  settings:     {'✓' if has_settings else '✗'} ({settings_size} 字符) {'→ 将应用' if should_apply('settings') else ''}")
    print(f"  keybindings:  {'✓' if has_keybindings else '✗'} ({kb_count} 条) {'→ 将应用' if should_apply('keybindings') else ''}")
    print(f"  extensions:   {'✓' if has_extensions else '✗'} ({ext_count} 个) {'→ 将应用' if should_apply('extensions') else ''}")
    print(f"  globalState:  {'✓' if has_global_state else '✗'} ({gs_count} 项) {'→ 将应用' if should_apply('globalState') else ''}")

    if not any([has_settings, has_keybindings, has_extensions, has_global_state]):
        print("\n配置文件为空，无需操作。")
        sys.exit(0)

    # 获取目标目录
    user_dir = get_vscode_user_dir(args.editor)
    print(f"\n目标配置目录: {user_dir}")

    if not args.dry_run:
        confirm = input("\n确认应用以上配置? 原配置将被备份 [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消操作")
            sys.exit(0)

    # 应用各项配置
    all_ok = True

    if has_settings and should_apply("settings"):
        all_ok &= apply_settings(parsed["settings"], user_dir, args.dry_run)

    if has_keybindings and should_apply("keybindings"):
        all_ok &= apply_keybindings(parsed["keybindings"], user_dir, args.dry_run)

    if has_global_state and should_apply("globalState"):
        all_ok &= apply_global_state(parsed["globalState"], user_dir, args.dry_run)

    if has_extensions and should_apply("extensions"):
        all_ok &= apply_extensions(parsed["extensions"], args.editor, args.dry_run)

    print(f"\n{'='*60}")
    if args.dry_run:
        print("模拟运行完成。要实际应用，请去掉 --dry-run 参数")
    elif all_ok:
        print("✓ 配置应用完成！请重启 VS Code 使所有更改生效。")
    else:
        print("⚠ 配置应用完成，但部分操作未成功。请检查上方日志。")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
