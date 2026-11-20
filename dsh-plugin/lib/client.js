window.__ModuleLoader__.load({
  id: "litradar-dsh-plugin",
  factory: (require) => {
    const module = { exports: {} };
    const exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

    const react = require("react");
    const h = react.createElement;

    /** 主面板与左侧栏共用的身份，必须等于 main 坑位的 key。 */
    const ID = "litradar";
    const LABEL = "题眼 LitRadar";
    const ORIGIN = "http://127.0.0.1:8899";

    /** 左侧栏图标：一圈扫描弧 + 中心点。 */
    function RadarGlyph({ size = 18, active = false }) {
      const color = active ? "currentColor" : "currentColor";
      return h(
        "svg",
        {
          width: size,
          height: size,
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: color,
          strokeWidth: 1.6,
          opacity: active ? 1 : 0.72,
          "aria-hidden": "true",
        },
        h("circle", { cx: 12, cy: 12, r: 9 }),
        h("path", { d: "M12 3v3M12 18v3M3 12h3M18 12h3" }),
        h("path", { d: "M12 12 18 8.4" }),
        h("circle", { cx: 12, cy: 12, r: 2.2, fill: "currentColor", stroke: "none" }),
      );
    }

    /** 引擎状态点：绿=在跑，灰=未起。 */
    function StatusDot({ up, pending }) {
      const color = pending ? "#c8a24a" : up ? "#2f9e6b" : "#c05545";
      return h("span", {
        title: pending ? "正在检查本地引擎" : up ? "本地引擎在跑" : "本地引擎没起",
        style: {
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
          flex: "0 0 auto",
        },
      });
    }

    function ToolButton({ children, onClick, title }) {
      return h(
        "button",
        {
          type: "button",
          onClick,
          title,
          style: {
            border: "1px solid rgba(0,0,0,0.14)",
            background: "transparent",
            color: "inherit",
            borderRadius: 6,
            padding: "3px 9px",
            fontSize: 12,
            lineHeight: 1.5,
            cursor: "pointer",
            fontFamily: "inherit",
          },
        },
        children,
      );
    }

    /**
     * 主面板正文：一条工具行 + 撑满剩余高度的 iframe。
     * iframe 直接指向本地引擎，因此表单、进度、六页签、下载都在 DSH 内部完成。
     */
    function LitRadarPanel() {
      const [state, setState] = react.useState({ up: false, pending: true, model: "" });
      const [nonce, setNonce] = react.useState(0);

      const probe = react.useCallback(async () => {
        try {
          const response = await fetch(`${ORIGIN}/api/health`, { cache: "no-store" });
          const body = await response.json();
          setState({ up: response.ok, pending: false, model: body.model ?? "" });
        } catch {
          setState({ up: false, pending: false, model: "" });
        }
      }, []);

      react.useEffect(() => {
        let alive = true;
        probe();
        const timer = setInterval(() => {
          if (alive) probe();
        }, 5000);
        return () => {
          alive = false;
          clearInterval(timer);
        };
      }, [probe]);

      const reload = () => setNonce((value) => value + 1);

      return h(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            height: "100%",
            minHeight: 0,
            background: "#f6f7f9",
          },
        },
        h(
          "div",
          {
            style: {
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 14px",
              borderBottom: "1px solid rgba(0,0,0,0.10)",
              background: "#ffffff",
              flex: "0 0 auto",
              fontSize: 13,
            },
          },
          h(StatusDot, { up: state.up, pending: state.pending }),
          h("span", { style: { fontWeight: 600, letterSpacing: "0.4px" } }, LABEL),
          h(
            "span",
            { style: { color: "#6b7683" } },
            state.up ? `本地引擎 · ${state.model || "deepseek"}` : "本地引擎未连接",
          ),
          h("span", { style: { flex: 1 } }),
          h(ToolButton, { onClick: reload, title: "重新载入界面" }, "刷新"),
          h(
            ToolButton,
            {
              onClick: () => window.open(`${ORIGIN}/`, "_blank", "noopener"),
              title: "在系统浏览器中打开",
            },
            "外部打开",
          ),
        ),
        state.up
          ? h("iframe", {
              key: nonce,
              src: `${ORIGIN}/?embed=1`,
              title: LABEL,
              style: {
                flex: "1 1 auto",
                width: "100%",
                border: "none",
                background: "#f6f7f9",
                minHeight: 0,
              },
            })
          : h(
              "div",
              {
                style: {
                  flex: "1 1 auto",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 14,
                  color: "#5b6672",
                  padding: 32,
                  textAlign: "center",
                },
              },
              h(RadarGlyph, { size: 44, active: false }),
              h("div", { style: { fontSize: 14, color: "#14181d" } }, "本地引擎还没起来"),
              h(
                "div",
                { style: { fontSize: 12, maxWidth: 420, lineHeight: 1.8 } },
                `插件会在 DSH 启动时自动拉起 ${ORIGIN}。如果这里一直是灰色，检查端口是否被占用，然后点“刷新”。`,
              ),
              h(ToolButton, { onClick: probe }, "重新检查"),
            ),
      );
    }

    const inject = ["slots", "layout"];

    function apply(ctx) {
      ctx.effect(
        () =>
          ctx.slots.inject("sidebar.panellist", () =>
            ctx.slots.register(
              {
                name: "sidebar.panellist",
                id: ID,
                order: 5,
                label: () => LABEL,
              },
              RadarGlyph,
            ),
          ),
        "litradar: 左侧栏入口",
      );

      ctx.effect(
        () =>
          ctx.slots.inject("main", () =>
            ctx.slots.register(
              {
                name: "main",
                key: ID,
              },
              LitRadarPanel,
            ),
          ),
        "litradar: 主面板",
      );
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
