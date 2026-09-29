extern void opaque();
int helper(int);
void guarded(int input) {
    do { if (!(input >= 0 && input <= 1024)) opaque(); } while (0);
    if (input == 0) return;
    else { int target = helper(input); }
}
void changed(int input) {
    ++input;
    int target = helper(input);
}
void aliased(int input) {
    using Ref = int&;
    Ref alias = input;
    alias += 1;
    int target = helper(input);
}
void called(int input) {
    opaque();
    int target = helper(input);
}
void repeat(int input) {
    do {} while (input > 0);
    int target = helper(input);
}
void branch_write(int input) {
    if (input > 100) ++input;
    int target = helper(input);
}
