"""TubeForge dashboard design system, server side.

The design system's source of truth is documented in design/DESIGN.md. The shared runtime files live in
src/tubeforge/assets/ui/ and are served at /static/ui/ (see register_design_assets). Pages built from the
recipes in design/guide.html use the helpers here so the app shell looks the same everywhere.
"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi.staticfiles import StaticFiles

UI_DIR = Path(__file__).resolve().parents[1] / "assets" / "ui"
STATIC_PREFIX = "/static/ui"

# Pages that already use the new shell. The SPA at "/" still uses studio_shell's own chrome.
NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("Make", ["studio", "batch", "references", "long-form", "clips"]),
    ("Review", ["generations"]),
    ("Publish", ["publishing", "scheduling", "accounts"]),
    ("System", ["media", "settings"]),
]

# Recipe classes copied from design/guide.html (keep these in sync with the guide).
# `!grid-cols-1` and `no-underline` are needed on the standalone pages: their legacy CSS defines a global
# `.grid` (two columns, 19px gap) and styles every `a` with an underline. See DESIGN.md, 'Known collisions'.
_NAV_LINK = (
    "flex h-9 items-center rounded-md px-3 text-base font-medium text-tf-muted no-underline "
    "hover:bg-tf-surface hover:text-tf-text aria-[current=page]:bg-tf-accent-soft aria-[current=page]:text-tf-accent"
)
_BUTTON_SMALL_SECONDARY = (
    "inline-flex h-8 items-center whitespace-nowrap rounded-md border border-tf-line-strong bg-tf-raised px-3 text-sm "
    "font-medium text-tf-text hover:border-tf-muted"
)
_BUTTON_QUIET = (
    "inline-flex h-8 items-center rounded-md px-3 text-sm font-medium text-tf-muted "
    "hover:bg-tf-raised hover:text-tf-text"
)


def register_design_assets(app) -> None:
    """Serve src/tubeforge/assets/ui (tokens.css, the Tailwind config, tubeforge-ui.js). Public: contains no data."""
    app.mount(STATIC_PREFIX, StaticFiles(directory=str(UI_DIR)), name="design-ui")


def design_head() -> str:
    """Stylesheets and script for a page, in load order. Place in the body: stylesheets there apply in order too.

    Everything is served from /static/ui: the compiled Tailwind stylesheet (built by scripts/build_design_css.sh),
    the tokens, the local IBM Plex fonts and the shared behaviour script. No CDN, no Google Fonts at run time.
    """
    return (
        f'<link rel="stylesheet" href="{STATIC_PREFIX}/fonts.css">'
        f'<link rel="stylesheet" href="{STATIC_PREFIX}/tokens.css">'
        f'<link rel="stylesheet" href="{STATIC_PREFIX}/tubeforge.css">'
        f'<script src="{STATIC_PREFIX}/tubeforge-ui.js" defer></script>'
    )


def _nav_links(active: str, items: dict[str, tuple[str, str]]) -> str:
    groups = []
    for group, keys in NAV_GROUPS:
        links = []
        for key in keys:
            if key not in items:
                continue
            href, label = items[key]
            current = ' aria-current="page"' if key == active else ""
            links.append(f'<a href="{html.escape(href)}" class="{_NAV_LINK}"{current}>{html.escape(label)}</a>')
        if links:
            groups.append(
                '<div class="grid !grid-cols-1 gap-1">'
                f'<p class="px-3 text-xs font-medium text-tf-faint">{group}</p>'
                + "".join(links)
                + "</div>"
            )
    return "".join(groups)


def render_sidebar(active: str, items: list[tuple[str, str, str]]) -> str:
    """The sidebar and its backdrop. ``items`` is (key, href, label)."""
    by_key = {key: (href, label) for key, href, label in items}
    return (
        '<aside id="studioSidebar" data-nav data-open="false" aria-label="Workspace navigation" '
        'class="tf-nav fixed inset-y-0 left-0 z-40 w-sidebar flex-col gap-6 overflow-y-auto border-r border-tf-line bg-tf-bg px-3 py-5">'
        '<a href="/" class="flex items-center gap-3 px-2 no-underline">'
        '<span class="grid !grid-cols-1 h-8 w-8 place-items-center rounded-md bg-tf-accent text-sm font-semibold text-tf-accent-ink">TF</span>'
        '<span class="grid !grid-cols-1 !gap-0 leading-tight"><span class="text-md font-semibold text-tf-text">TubeForge</span>'
        '<span class="text-xs text-tf-muted">Creator Studio</span></span></a>'
        '<div class="rounded-md border border-tf-line px-3 py-2 text-sm text-tf-text">Local workspace</div>'
        f'<nav aria-label="Studio sections" class="grid !grid-cols-1 gap-5">{_nav_links(active, by_key)}</nav>'
        '<p class="mt-auto text-xs text-tf-faint">Account plans stay local until a destination is verified and a separate draft is reviewed.</p>'
        "</aside>"
        '<button type="button" class="tf-nav-backdrop fixed inset-0 z-30 bg-tf-scrim lg:hidden" '
        'data-nav-close aria-label="Close navigation" hidden></button>'
    )


def render_app_shell(active: str, items: list[tuple[str, str, str]], breadcrumb: str, username: str | None) -> str:
    """Sidebar, top bar and the opening of the main column.

    The caller must close the returned markup with ``</div></div>``.
    """
    if username:
        auth = (
            f'<span class="hidden text-sm text-tf-muted sm:inline">Signed in as {html.escape(username)}</span>'
            f'<button type="button" id="signOutButton" class="{_BUTTON_SMALL_SECONDARY}">Sign out</button>'
        )
    else:
        auth = '<span class="hidden text-sm text-tf-muted sm:inline">Local access</span>'
    topbar = (
        '<header class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-tf-line bg-tf-bg px-4 lg:px-8">'
        '<button type="button" class="inline-flex h-8 items-center rounded-md border border-tf-line-strong '
        'bg-tf-raised px-3 text-sm font-medium text-tf-text lg:hidden" data-nav-open aria-expanded="false" '
        'aria-controls="studioSidebar">Menu</button>'
        f'<nav aria-label="Breadcrumb" class="min-w-0 truncate text-sm text-tf-muted">{html.escape(breadcrumb)}</nav>'
        f'<div class="ml-auto flex items-center gap-3">{auth}</div>'
        "</header>"
    )
    # The content wrapper leaves room for the fixed sidebar from 1024 px. Close with '</div></div>'.
    return render_sidebar(active, items) + '<div class="lg:pl-sidebar min-w-0">' + topbar + '<div class="min-w-0 px-4 py-8 lg:px-8">'



def spa_shell_open(items: list[tuple[str, str, str]]) -> str:
    """Opening markup of the single-page dashboard (served at /): tags, sidebar, top bar.

    The page keeps <main class="shell"> inside; spa_shell_close() closes the wrappers after it.
    The top bar keeps the ids the dashboard script uses: studioBreadcrumb, authInfo, connection.
    """
    topbar = (
        '<header id="spaTopbar" class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-tf-line bg-tf-bg px-4 lg:px-8">'
        '<button type="button" class="inline-flex h-8 items-center rounded-md border border-tf-line-strong bg-tf-raised px-3 text-sm font-medium text-tf-text lg:hidden" data-nav-open aria-expanded="false" aria-controls="studioSidebar">Menu</button>'
        '<nav id="studioBreadcrumb" aria-label="Breadcrumb" class="min-w-0 truncate text-sm text-tf-muted">Workspace / <strong class="font-semibold text-tf-text">Studio</strong></nav>'
        '<div class="ml-auto flex items-center gap-3">'
        '<span id="connection" class="hidden text-sm text-tf-muted sm:inline" role="status">Connecting…</span>'
        '<span id="authInfo" class="flex items-center gap-3 whitespace-nowrap text-sm text-tf-muted" data-username=""></span>'
        "</div></header>"
    )
    return (
        design_head()
        + render_sidebar("studio", items)
        + '<div class="lg:pl-sidebar min-w-0">' + topbar + '<div class="min-w-0 px-4 py-8 lg:px-8">'
    )


def spa_shell_close() -> str:
    return "</div></div>"
