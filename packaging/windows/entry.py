"""What PyInstaller freezes: the console script, as `pip` would have made it."""

from tidalamp.cli import main

if __name__ == "__main__":
    main()
