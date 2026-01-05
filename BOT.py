import uvicorn

from moneybot.api.app import app
from moneybot.observability import configure_logging


def main() -> None:
    configure_logging()
    print("MoneyBot UI disponible en http://127.0.0.1:8000/ui")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
