from moneybot.observability import configure_logging
from moneybot.ui_app import MoneyBotApp


def main() -> None:
    configure_logging()
    app = MoneyBotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
