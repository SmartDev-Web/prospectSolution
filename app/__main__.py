"""Launch the local server and open the interface in the default browser once it listens."""
import asyncio
import logging
import sys
import webbrowser

import uvicorn

from app.config import SERVER_HOST, SERVER_PORT


class BrowserOpeningServer(uvicorn.Server):
    """Uvicorn server opening the interface as soon as it is ready to accept connections."""

    def __init__(self, config: uvicorn.Config, open_browser: bool) -> None:
        super().__init__(config)
        self._open_browser = open_browser

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if self._open_browser and self.started:
            webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}/")


def main() -> None:
    """Entry point of 'python -m app'."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    open_browser = "--no-browser" not in sys.argv
    server_config = uvicorn.Config("app.main:application", host=SERVER_HOST, port=SERVER_PORT, loop="none", log_level="info")
    # The default event loop on Windows is the Proactor loop, required by Playwright and subprocesses
    asyncio.run(BrowserOpeningServer(server_config, open_browser).serve())


if __name__ == "__main__":
    main()
