/**
 * 题眼 LitRadar 的宿主侧半边。
 *
 * 这里只做一件事：确认本地引擎（127.0.0.1:8899 上的 Python 服务）在跑，
 * 没跑就拉起来。浏览器侧面板只是把这个地址嵌进 DSH 界面，因此引擎随 DSH
 * 一起起停，用户不需要另开终端。API Key 由引擎自己从 DSH 的凭据文件读取，
 * 面板里不再要求填写。
 */
import { spawn } from "node:child_process";

const PORT = Number(process.env.LITRADAR_PORT ?? 8899);
const HOME = process.env.LITRADAR_HOME ?? "D:\\Projects\\LitRadar";
const PYTHON =
  process.env.LITRADAR_PYTHON ??
  "C:\\Users\\1\\AppData\\Local\\Programs\\Python\\Python313\\python.exe";

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
        cwd: HOME,
        windowsHide: true,
        stdio: ["ignore", "ignore", "ignore"],
        env: {
          ...process.env,
          PYTHONPATH: `${HOME}\\src`,
          LITRADAR_HOME: `${HOME}\\workspace`,
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
