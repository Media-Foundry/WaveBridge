extern void dispatch(int first, int second);
extern void escape(const int*);
extern bool other();
int good(int input) {
    const int value = input;
    if (other() || (value != 65 && value != 128) || other()) return 3;
    dispatch(value, value);
    return 0;
}
int extra_conjunct(int input) {
    const int value = input;
    if (value != 65 && value != 128 && other()) return 3;
    dispatch(value, value);
    return 0;
}
int escaped(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    escape(&value);
    dispatch(value, value);
    return 0;
}
int aliased(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    const int& alias = value;
    dispatch(value, value);
    return alias;
}
int bypass(int input) {
    const int value = input;
    goto target;
    if (value != 65 && value != 128) return 3;
    target: ;
    dispatch(value, value);
    return 0;
}
int mutable_local(int input) {
    int value = input;
    if (value != 65 && value != 128) return 3;
    value = 10;
    dispatch(value, value);
    return 0;
}
int wrong_argument(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    dispatch(input, value);
    return 0;
}
int power_helper(int input) {
    int exponent = 0;
    while ((1 << exponent) < input) ++exponent;
    return exponent;
}
int power_dispatch(int input) {
    int exponent = power_helper(input);
    const int power = 1 << exponent;
    other();
    int width = 16;
    width = (power < width) ? power : width;
    return power;
}
int guarded_power(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    power_dispatch(value);
    return 0;
}
int unsafe_guarded_power(int input) {
    const int value = input;
    if (value != 0 && value != 128) return 3;
    power_dispatch(value);
    return 0;
}
int escaped_power_dispatch(int input) {
    int exponent = power_helper(input);
    const int power = 1 << exponent;
    escape(&(other() ? power : input));
    return power;
}
int guarded_escaped_power(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    escaped_power_dispatch(value);
    return 0;
}
int mutable_power_dispatch(int input) {
    int exponent = power_helper(input);
    int power = 1 << exponent;
    other();
    return power;
}
int guarded_mutable_power(int input) {
    const int value = input;
    if (value != 65 && value != 128) return 3;
    mutable_power_dispatch(value);
    return 0;
}
