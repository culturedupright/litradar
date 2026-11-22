"""LitRadar 一键安装器：双击后装引擎，并把插件挂进本机 DSH。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

APP_NAME = "LitRadar"
VERSION = "0.10.1"
PLUGIN_NAME = "litradar-dsh-plugin"
PROFILE_NAMES = ("desktop", "web")


def asset_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        bundled = Path(sys._MEIPASS) / "assets"
        return bundled if bundled.is_dir() else Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent / "dist"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_profiles(dsh_root: Path) -> list[tuple[str, Path]]:
    """只装 DSH 的 desktop/web 用户 profile，跳过 tauri/safe 内部 profile。"""
    found: list[tuple[str, Path]] = []
    profiles_root = dsh_root / "profiles"
    if not profiles_root.is_dir():
        return found
    for name in PROFILE_NAMES:
        folder = profiles_root / name
        pkg = folder / "package.json"
        if not pkg.is_file():
            continue
        try:
            data = _read_json(pkg)
        except Exception:
            continue
        bundles = (((data.get("dsh") or {}).get("profile") or {}).get("bundles") or [])
        if isinstance(bundles, list):
            found.append((name, folder))
    return found


def find_python() -> str:
    for name in ("python", "python3", "py"):
        path = shutil.which(name)
        if path:
            return path
    return ""


def install_engine(install_root: Path, engine_zip: Path) -> tuple[Path, Path]:
    engine_dir = install_root / f"engine-{VERSION}"
    engine_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(engine_zip) as zf:
        zf.extractall(engine_dir)
    if not (engine_dir / "src" / "litradar" / "__init__.py").is_file():
        raise RuntimeError("引擎压缩包里没有 src/litradar/__init__.py")

    exe_src = asset_root() / "litradar-engine.exe"
    if not exe_src.is_file():
        raise RuntimeError("安装器里缺少 litradar-engine.exe")
    exe_dst = install_root / f"litradar-engine-{VERSION}.exe"
    shutil.copy2(exe_src, exe_dst)
    return engine_dir, exe_dst


def install_profile(name: str, folder: Path, tgz: Path) -> str:
    node_modules = folder / "node_modules"
    node_modules.mkdir(parents=True, exist_ok=True)
    dest = node_modules / PLUGIN_NAME

    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tgz, "r:gz") as tar:
            tar.extractall(tmp)
        src = Path(tmp) / "package"
        if not src.is_dir():
            raise RuntimeError(f"{tgz.name} 不是有效的插件包")

        backup = dest.with_name(PLUGIN_NAME + ".litradar-old")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if dest.exists():
            try:
                dest.rename(backup)
            except OSError:
                shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)

    pkg_path = folder / "package.json"
    data = _read_json(pkg_path)
    backup_json = folder / "package.json.litradar-backup"
    if not backup_json.exists():
        shutil.copy2(pkg_path, backup_json)

    deps = data.setdefault("dependencies", {})
    deps[PLUGIN_NAME] = f"file:{tgz.as_posix()}"
    dsh = data.setdefault("dsh", {})
    profile = dsh.setdefault("profile", {})
    bundles = profile.setdefault("bundles", [])
    if PLUGIN_NAME not in bundles:
        bundles.append(PLUGIN_NAME)
    _write_json(pkg_path, data)
    return name


def write_config(
    install_root: Path,
    engine_dir: Path,
    engine_exe: Path,
    config_dir: Path | None = None,
) -> Path:
    config_dir = config_dir or (Path.home() / ".litradar-suite")
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    old = {}
    if config_path.is_file():
        try:
            old = _read_json(config_path)
        except Exception:
            old = {}
    data_dir = Path(old.get("data") or (Path.home() / ".litradar"))
    data_dir.mkdir(parents=True, exist_ok=True)
    old.update(
        {
            "engine": str(engine_dir),
            "engine_exe": str(engine_exe),
            "python": find_python(),
            "data": str(data_dir),
        }
    )
    _write_json(config_path, old)
    return config_path


def _powershell() -> str:
    candidates = [
        shutil.which("pwsh"),
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        shutil.which("powershell"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


def make_shortcut(install_root: Path, engine_exe: Path) -> str:
    """在开始菜单放一个 LitRadar 快捷方式；失败不影响插件安装。"""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return "跳过：没有 APPDATA"
    ps = _powershell()
    if not ps:
        return "跳过快捷方式：找不到 PowerShell"
    shortcut = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "LitRadar.lnk"
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$sc = $ws.CreateShortcut('{shortcut.as_posix()}');\n"
        f"$sc.TargetPath = '{engine_exe.as_posix()}';\n"
        f"$sc.WorkingDirectory = '{install_root.as_posix()}';\n"
        "$sc.Description = '题眼 LitRadar';\n"
        "$sc.Save();\n"
    )
    try:
        subprocess.run(
            [ps, "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return str(shortcut)
    except Exception as exc:
        return f"跳过快捷方式：{exc}"


def install_all(
    dsh_root: Path,
    install_root: Path,
    profile_filter: tuple[str, ...] = PROFILE_NAMES,
    dry_run: bool = False,
    report=None,
    config_dir: Path | None = None,
) -> list[str]:
    base = asset_root()
    engine_zip = base / "litradar-engine.zip"
    tgz = base / f"{PLUGIN_NAME}-{VERSION}.tgz"
    for path in (engine_zip, tgz):
        if not path.is_file():
            raise RuntimeError(f"安装器缺少资源：{path.name}")

    profiles = [p for p in detect_profiles(dsh_root) if p[0] in profile_filter]
    if not profiles:
        raise RuntimeError(
            "没有找到 DSH profile（%USERPROFILE%\\.dsh\\profiles\\desktop 或 web）。"
            "请先安装并启动一次 DeepSeek Harness。"
        )

    lines = [f"安装到：{install_root}", f"DSH profile：{', '.join(n for n, _ in profiles)}"]
    if dry_run:
        lines.append("dry-run：未写文件")
        return lines

    install_root.mkdir(parents=True, exist_ok=True)
    (report or (lambda _: None))("正在解压引擎…")
    engine_dir, engine_exe = install_engine(install_root, engine_zip)
    lines.append(f"引擎：{engine_dir}")

    packages = install_root / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    packaged_tgz = packages / tgz.name
    shutil.copy2(tgz, packaged_tgz)

    (report or (lambda _: None))("正在写入 DSH profile…")
    for name, folder in profiles:
        install_profile(name, folder, packaged_tgz)
        lines.append(f"插件：{name} -> {folder}")
    config_path = write_config(install_root, engine_dir, engine_exe, config_dir)
    lines.append(f"配置：{config_path}")

    (report or (lambda _: None))("正在创建开始菜单快捷方式…")
    lines.append(f"快捷方式：{make_shortcut(install_root, engine_exe)}")
    lines.append("完成：请完全退出并重新打开 DeepSeek Harness。")
    return lines


def run_gui() -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title(f"题眼 LitRadar {VERSION} 安装器")
    root.geometry("560x330")
    root.resizable(False, False)

    tk.Label(root, text="题眼 LitRadar", font=("Microsoft YaHei", 16, "bold")).pack(pady=(18, 2))
    tk.Label(
        root,
        text="把本地引擎和 DSH 插件装到当前用户，不需要管理员权限。",
        fg="#555",
    ).pack()
    status = tk.StringVar(value="准备安装…")
    tk.Label(root, textvariable=status, anchor="w", wraplength=510, justify="left").pack(
        fill="x", padx=28, pady=(14, 8)
    )
    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.pack(fill="x", padx=28, pady=4)
    log_box = tk.Text(root, height=7, width=62, state="disabled", relief="flat", bg="#f7f7f7")
    log_box.pack(fill="both", expand=True, padx=28, pady=8)

    def append(text: str) -> None:
        status.set(text)
        log_box.configure(state="normal")
        log_box.insert("end", text + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")
        root.update_idletasks()

    def start() -> None:
        button.configure(state="disabled")
        progress.start(12)
        root.update_idletasks()
        try:
            lines = install_all(Path.home() / ".dsh", Path(os.environ["LOCALAPPDATA"]) / "LitRadar", report=append)
            for line in lines:
                append(line)
            progress.stop()
            status.set("安装完成")
            messagebox.showinfo("题眼 LitRadar", "安装完成。\n请完全退出并重新打开 DeepSeek Harness。")
        except Exception as exc:
            progress.stop()
            status.set("安装失败")
            append(f"失败：{exc}")
            messagebox.showerror("题眼 LitRadar", f"安装失败：\n{exc}")
        finally:
            button.configure(state="normal")

    button = tk.Button(root, text="安装到 DSH", command=start, height=2, bg="#111", fg="white")
    button.pack(fill="x", padx=28, pady=(0, 16))
    root.after(150, start)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsh-root", type=Path, default=Path.home() / ".dsh")
    parser.add_argument("--install-root", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LitRadar")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".litradar-suite")
    parser.add_argument("--profiles", default="desktop,web")
    args = parser.parse_args()
    if args.headless:
        try:
            for line in install_all(
                args.dsh_root,
                args.install_root,
                tuple(x.strip() for x in args.profiles.split(",") if x.strip()),
                dry_run=args.dry_run,
                report=print,
                config_dir=args.config_dir,
            ):
                print(line)
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
