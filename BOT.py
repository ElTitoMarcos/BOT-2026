import sys
import webbrowser

import uvicorn

from moneybot.api.app import app
from moneybot.observability import configure_logging


def main() -> None:
    configure_logging()
    url = "http://127.0.0.1:8000/ui"
    if sys.platform == "win32":
        opened = False
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            print(f"MoneyBot UI disponible en {url}")
    else:
        print(f"MoneyBot UI disponible en {url}")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
