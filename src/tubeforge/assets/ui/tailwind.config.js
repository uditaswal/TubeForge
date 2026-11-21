/*
  Tailwind build config (Tailwind 3.4.17). Used only by scripts/build_design_css.sh, which writes
  tubeforge.css. Nothing loads this file in the browser any more.

  Every color maps to a CSS variable in src/tubeforge/assets/ui/tokens.css. Do not put hex values here.
  Tailwind's built-in palettes are removed on purpose: only tf-* colors exist.
*/
const tfTailwindConfig = {
  content: ["./src/tubeforge/api/**/*.{py,html,js}", "./src/tubeforge/assets/ui/*.js", "./design/*.{html,js}"],
  // Preflight (the Tailwind base reset) is off: the dashboard pages already style their own elements.
  corePlugins: { preflight: false },
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      "tf-bg": "var(--tf-bg)",
      "tf-surface": "var(--tf-surface)",
      "tf-raised": "var(--tf-raised)",
      "tf-input": "var(--tf-input)",
      "tf-line": "var(--tf-line)",
      "tf-line-strong": "var(--tf-line-strong)",
      "tf-text": "var(--tf-text)",
      "tf-muted": "var(--tf-muted)",
      "tf-faint": "var(--tf-faint)",
      "tf-accent": "var(--tf-accent)",
      "tf-accent-ink": "var(--tf-accent-ink)",
      "tf-accent-soft": "var(--tf-accent-soft)",
      "tf-ok": "var(--tf-ok)",
      "tf-ok-soft": "var(--tf-ok-soft)",
      "tf-warn": "var(--tf-warn)",
      "tf-warn-soft": "var(--tf-warn-soft)",
      "tf-bad": "var(--tf-bad)",
      "tf-bad-soft": "var(--tf-bad-soft)",
      "tf-info": "var(--tf-info)",
      "tf-info-soft": "var(--tf-info-soft)",
      "tf-scrim": "var(--tf-scrim)",
      "tf-danger": "var(--tf-danger)",
      "tf-danger-ink": "var(--tf-danger-ink)",
    },
    fontFamily: {
      sans: "var(--tf-font-sans)",
      mono: "var(--tf-font-mono)",
    },
    // Type scale (px): 12 / 13 / 14 / 16 / 20 / 26. Use ONLY these six.
    fontSize: {
      xs: ["12px", { lineHeight: "16px" }],
      sm: ["13px", { lineHeight: "18px" }],
      base: ["14px", { lineHeight: "22px" }],
      md: ["16px", { lineHeight: "24px" }],
      lg: ["20px", { lineHeight: "28px" }],
      xl: ["26px", { lineHeight: "32px" }],
    },
    borderRadius: {
      none: "0",
      sm: "var(--tf-radius-sm)",
      md: "var(--tf-radius-md)",
      lg: "var(--tf-radius-lg)",
      full: "9999px",
    },
    extend: {
      maxWidth: {
        content: "var(--tf-content)",
        form: "var(--tf-form)",
      },
      width: {
        sidebar: "var(--tf-sidebar)",
      },
      spacing: {
        sidebar: "var(--tf-sidebar)",
      },
    },
  },
};

if (typeof module !== "undefined" && module.exports) module.exports = tfTailwindConfig;
