int renamed(int input) {
    int exponent = 0;
    while ((1 << exponent) < input) ++exponent;
    return exponent;
}
int postfix(int x) {
    int i = 0;
    while ((1 << i) < x) { i++; }
    return i;
}
int wrong_equal(int x) {
    int i = 0;
    while ((1 << i) <= x) ++i;
    return i;
}
int wrong_write(int x) {
    int i = 0;
    while ((1 << i) < x) { ++i; --x; }
    return i;
}
int persistent(int x) {
    static int i = 0;
    while ((1 << i) < x) ++i;
    return i;
}
int adjacent(int input) {
    int exponent = renamed(input);
    const int power = 1 << exponent;
    return power;
}
int intervening(int input) {
    int exponent = renamed(input);
    ++exponent;
    const int power = 1 << exponent;
    return power;
}
int changed_base(int input) {
    int exponent = renamed(input);
    const int power = 2 << exponent;
    return power;
}
int shifted_other(int input) {
    int exponent = renamed(input);
    const int power = 1 << input;
    return power;
}
int static_result(int input) {
    static int exponent = renamed(input);
    const int power = 1 << exponent;
    return power;
}
