# Apply VSCode Profile

将 VSCode 导出的 profile 配置一键应用到本地 VSCode / VSCode Insiders。

支持 **settings**、**keybindings**、**extensions**、**globalState** 四类配置的完整迁移，操作前自动备份原配置。

---

## 快速开始

### 前提

- macOS / Linux 系统（已预装 Python 3）
- VSCode CLI（`code` 或 `code-insiders`）在 PATH 中可用

> 如果提示 `command not found: code`，在 VSCode 中按 `Cmd+Shift+P` 并执行 `Shell Command: Install 'code' command in PATH`。

### 第一步：下载脚本

```bash
curl -fsSL -o ~/apply_vscode_profile.py https://raw.githubusercontent.com/northwang-lucky/apply_vscode_profile/main/apply_vscode_profile.py
```

### 第二步：准备 Profile

**方式 A — 使用本地 profile 文件**

直接在 VSCode 中导出 profile（`Profiles` → `Export Profile...`），保存到本地，例如 `~/Downloads/custom.code-profile`。

**方式 B — 使用在线 profile 链接**

将 profile 文件上传至任意可公开访问的地址（如 GitHub、Gist），然后下载到本地：

```bash
# 替换为实际的 profile URL
curl -fsSL -o ~/my-profile.code-profile <YOUR_PROFILE_URL>
```

### 第三步：执行应用

```bash
# 基础用法 — 应用到 VSCode 稳定版
python3 ~/apply_vscode_profile.py ~/Downloads/custom.code-profile

# 应用到 VSCode Insiders
python3 ~/apply_vscode_profile.py ~/Downloads/custom.code-profile --editor insiders

# 模拟运行 — 只预览，不实际写入
python3 ~/apply_vscode_profile.py ~/Downloads/custom.code-profile --dry-run
```

---

## 功能特性

| 配置项 | 说明 | 目标位置 |
|--------|------|---------|
| `settings` | 编辑器设置（自动处理 JSONC 注释和尾逗号） | `settings.json` |
| `keybindings` | 快捷键绑定 | `keybindings.json` |
| `extensions` | 扩展列表（禁用的扩展也会被安装并禁用） | 通过 CLI 安装 |
| `globalState` | 全局状态（视图布局、隐藏状态等） | `globalStorage/state.vscdb` |

- **自动备份**：修改前自动将原配置备份为 `*.backup.YYYYMMDD_HHMMSS`
- **禁用的扩展**：安装后自动执行 `code --disable-extension` 禁用 profile 中标记为 `disabled` 的扩展
- **跳过已安装**：已安装的扩展不会重复安装
- **JSONC 兼容**：正确解析 VSCode 的 JSONC 格式（含 `//` 注释、`/* */` 注释、尾部逗号）

---

## 参数说明

```
usage: apply_vscode_profile.py [-h] [--editor {code,insiders}] [--dry-run]
                               [--skip-extensions] [--skip-global-state]
                               profile

位置参数:
  profile                 导出的 VSCode profile 文件路径

可选参数:
  -h, --help              显示帮助信息
  --editor {code,insiders}
                          目标编辑器（默认：code）
  --dry-run               模拟运行，只显示操作不实际写入
  --skip-extensions       跳过扩展安装
  --skip-global-state     跳过 globalState 应用
```

---

## 平台支持

自动识别操作系统，无需手动配置路径：

| 平台 | VSCode | VSCode Insiders |
|------|---------|-----------------|
| **macOS** | `~/Library/Application Support/Code/User` | `~/Library/Application Support/Code - Insiders/User` |
| **Linux** | `~/.config/Code/User` | `~/.config/Code - Insiders/User` |

---

## 导出 Profile

在 VSCode 中导出你的配置：

1. 点击左下角头像图标 → **Profiles** → **Export Profile...**
2. 选择要导出的配置项（settings、keybindings、extensions、UI state）
3. 保存为 `*.code-profile` 文件

---

## License

[MIT](LICENSE)
