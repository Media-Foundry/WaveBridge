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
