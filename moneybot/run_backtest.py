from .strategy import Strategy


def main() -> None:
    strategy = Strategy()
    signals = strategy.generate_signals([])
    print(f"Backtest stub: generated {len(signals)} signals")


if __name__ == "__main__":
    main()
