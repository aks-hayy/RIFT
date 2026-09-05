"""Allow ``python -m rift`` to use the public CLI entrypoint."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
