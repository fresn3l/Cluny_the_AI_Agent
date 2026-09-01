"""Entry point for py2app Cluny.app bundle."""

from __future__ import annotations

from cluny.widget.app import run_widget_app


def main() -> None:
    run_widget_app()


if __name__ == "__main__":
    main()
