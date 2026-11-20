/**
 * 题眼 LitRadar 的宿主侧半边。
 *
 * 只做一件事：确认本地引擎（默认 127.0.0.1:8899 上的 Python 服务）在跑，
 * 没跑就拉起来。浏览器侧面板只是把这个地址嵌进 DSH 界面，因此引擎随 DSH
 * 一起起停，用户不需要另开终端。模型 Key 由引擎从 DSH 凭据文件读取。
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONFIG_FILE = path.join(os.homedir(), ".litradar-suite", "config.json");
const PORT = Number(process.env.LITRADAR_PORT ?? 8899);

/** 安装器写在 ~/.litradar-suite/config.json 里的引擎位置。 */
function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf8"));
  } catch {
    return {};
  }
}

const config = readConfig();

/** 依次找引擎：环境变量 → 安装器配置 → 包内 engine → 开发仓库。 */
function engineRoot() {
  const candidates = [
    process.env.LITRADAR_ENGINE,
    config.engine,
    path.join(PKG_ROOT, "engine"),
    path.join(os.homedir(), "LitRadar"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "src", "litradar", "__init__.py"))) {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

function pythonPath() {
  const candidates = [
    process.env.LITRADAR_PYTHON,
    config.python,
    "C:\\Users\\1\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (candidate === "python") return candidate;
    if (fs.existsSync(candidate)) return candidate;
  }
  return "python";
}

const ENGINE = engineRoot();
const PYTHON = pythonPath();
const DATA_HOME =
  process.env.LITRADAR_HOME ??
  config.data ??
  (fs.existsSync(path.join(ENGINE, "workspace"))
    ? path.join(ENGINE, "workspace")
    : path.join(os.homedir(), ".litradar"));

const HEALTH = `http://127.0.0.1:${PORT}/api/health`;

/** 引擎是否已经在跑。 */
async function engineUp() {
  try {
    const response = await fetch(HEALTH, { signal: AbortSignal.timeout(1200) });
    return response.ok;
  } catch {
    return false;
  }
}

/** 拉起引擎；失败只记一行，不阻塞 DSH 启动。 */
function startEngine(log) {
  try {
    const child = spawn(
      PYTHON,
      ["-m", "litradar", "serve", "--port", String(PORT)],
      {
        cwd: ENGINE,
        windowsHide: true,
        stdio: ["ignore", "ignore", "ignore"],
        env: {
          ...process.env,
          PYTHONPATH: path.join(ENGINE, "src"),
          LITRADAR_HOME: DATA_HOME,
        },
      },
    );
    child.on("error", (error) => log?.warn?.(`litradar: 引擎启动失败 ${error.message}`));
    child.unref?.();
    return child;
  } catch (error) {
    log?.warn?.(`litradar: 引擎启动异常 ${String(error)}`);
    return null;
  }
}

/** Cordis 宿主插件主体。 */
export function apply(ctx) {
  let child = null;
  const stop = () => {
    if (child && !child.killed) {
      try {
        child.kill();
      } catch {
        /* 已经退出 */
      }
    }
    child = null;
  };

  ctx.effect(() => {
    let cancelled = false;
    engineUp().then((up) => {
      if (cancelled || up) return;
      child = startEngine(ctx.logger?.("litradar"));
    });
    return () => {
      cancelled = true;
      stop();
    };
  }, "litradar: 本地引擎");
}
