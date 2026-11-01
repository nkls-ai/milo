"""The frozen desktop and runtime share one dispatch entry point."""
from milo.desktop.main import main

if __name__ == "__main__":
    raise SystemExit(main())
