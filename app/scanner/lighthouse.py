"""Optional Google Lighthouse audit through the locally installed command line tool."""
import asyncio
import json
import logging
import os
import shutil

from app.browser import browser_runtime

logger = logging.getLogger(__name__)
LIGHTHOUSE_TIMEOUT_SECONDS = 120
LIGHTHOUSE_CATEGORIES = ("performance", "accessibility", "seo", "best-practices")


def find_lighthouse_executable() -> str | None:
    """Return the Lighthouse executable path when it is installed (npm install -g lighthouse)."""
    return shutil.which("lighthouse") or shutil.which("lighthouse.cmd")


async def run_lighthouse(url: str) -> dict[str, int] | None:
    """Run a mobile Lighthouse audit and return category scores out of 100."""
    lighthouse_executable = find_lighthouse_executable()
    if lighthouse_executable is None:
        return None
    await browser_runtime.get_playwright()
    environment_variables = dict(os.environ)
    chromium_path = browser_runtime.chromium_executable_path()
    if chromium_path:
        environment_variables["CHROME_PATH"] = chromium_path
    process = await asyncio.create_subprocess_exec(
        lighthouse_executable, url, "--output=json", "--output-path=stdout", "--quiet",
        f"--only-categories={','.join(LIGHTHOUSE_CATEGORIES)}", "--chrome-flags=--headless=new --no-sandbox",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment_variables,
    )
    try:
        standard_output, standard_error = await asyncio.wait_for(process.communicate(), timeout=LIGHTHOUSE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        logger.warning("Lighthouse timed out on %s", url)
        return None
    if process.returncode != 0:
        logger.warning("Lighthouse failed on %s : %s", url, standard_error.decode(errors="replace")[-500:])
        return None
    report = json.loads(standard_output)
    return {
        category_key: round((category.get("score") or 0) * 100)
        for category_key, category in report.get("categories", {}).items()
    }
