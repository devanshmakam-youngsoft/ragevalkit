"""The order passages are taken in, so any few of them sample the whole document."""


def spread_order(n: int) -> list[int]:
    """0..n-1 ordered so that any prefix is spread across the whole range (van der Corput order):
    n=8 gives 0, 4, 2, 6, 1, 5, 3, 7. Taking passages in this order samples a document evenly."""
    def reverse_bits(i: int) -> float:
        value, base = 0.0, 0.5
        while i:
            value += (i & 1) * base
            i >>= 1
            base /= 2
        return value

    return sorted(range(n), key=lambda i: (reverse_bits(i), i))
