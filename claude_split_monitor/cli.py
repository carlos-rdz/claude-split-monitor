"""CLI entry point for claude-split-monitor."""
import asyncio
import sys
import webbrowser
from . import server


def main():
    """Start the monitor server."""
    # --no-browser flag to skip auto-open
    args = sys.argv[1:]
    auto_open = "--no-browser" not in args

    if "--version" in args or "-v" in args:
        from . import __version__
        print(f"claude-split-monitor v{__version__}")
        return

    if "--help" in args or "-h" in args:
        print("""
claude-split-monitor — real-time dashboard for claude-split sessions

Usage:
  claude-split-monitor [options]

Options:
  --no-browser    Don't auto-open dashboard in browser
  --version, -v   Show version
  --help, -h      Show this help

Endpoints:
  http://localhost:7433/           — dashboard
  http://localhost:7433/api/state  — JSON state
  http://localhost:7433/api/health — health check
  ws://localhost:7433/ws           — live updates
""")
        return

    # Auto-open browser after short delay
    if auto_open:
        async def _open():
            await asyncio.sleep(1.5)
            webbrowser.open(f"http://localhost:{server.PORT}/")

        async def _run():
            asyncio.create_task(_open())
            await server.main()

        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            print("\n  [*] Shutting down.")
    else:
        try:
            asyncio.run(server.main())
        except KeyboardInterrupt:
            print("\n  [*] Shutting down.")


if __name__ == "__main__":
    main()
