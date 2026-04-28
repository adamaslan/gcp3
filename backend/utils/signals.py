"""Shared momentum signal logic for screener and watchlist."""


def ai_signal(quote: dict) -> str:
    """Rule-based momentum signal derived from intraday data.

    Args:
        quote: Dict with keys change_pct, price, low, high.

    Returns:
        One of: "strong_buy", "buy", "hold", "sell", "strong_sell".
    """
    pct = quote.get("change_pct", 0)
    price = quote.get("price", 0)
    low = quote.get("low", price)
    high = quote.get("high", price)
    intraday_range = high - low
    position_in_range = (price - low) / intraday_range if intraday_range > 0 else 0.5

    if pct > 3 and position_in_range > 0.75:
        return "strong_buy"
    if pct > 1.5 or (pct > 0.5 and position_in_range > 0.7):
        return "buy"
    if pct < -3 and position_in_range < 0.25:
        return "strong_sell"
    if pct < -1.5 or (pct < -0.5 and position_in_range < 0.3):
        return "sell"
    return "hold"
