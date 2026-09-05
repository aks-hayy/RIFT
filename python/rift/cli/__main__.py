"""Allow `python -m rift.cli` to run the RIFT command line."""

from . import main


raise SystemExit(main())
