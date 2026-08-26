"""Command-line entry point: run the Gungnir web server (M5)."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("gungnir.web:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
