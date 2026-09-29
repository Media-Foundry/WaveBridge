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
