"""Arithmetic and wire format only; no RTL controller/shift-register replica."""
def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits-1)) else value


def expected(codes, inputs):
    if len(codes) != 8 or len(inputs) != 8:
        raise ValueError('ternary8 needs eight weights and inputs')
    if any(c not in range(4) for c in codes) or any(not -128 <= a <= 127 for a in inputs):
        raise ValueError('input out of contract range')
    weights = (0, 1, -1, 0)
    total = sum(weights[c] * a for c, a in zip(codes, inputs))
    illegal = int(3 in codes)
    return ((total & 4095) | (illegal << 12))


def packet(codes, inputs):
    expected(codes, inputs)  # Validate the public input domain.
    packed = sum(c << (2*i) for i, c in enumerate(codes))
    byte_values = [packed & 255, packed >> 8] + [a & 255 for a in inputs]
    return [n for byte in byte_values for n in (byte & 15, byte >> 4)]


def decode(nibbles):
    if len(nibbles) != 4 or any(n not in range(16) for n in nibbles):
        raise ValueError('expected four nibbles')
    return sum(n << (4*i) for i, n in enumerate(nibbles))
