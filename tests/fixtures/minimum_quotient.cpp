void observe_quotient(int);

void nested_constant_quotient(int target, const int candidate, bool outer) {
    if (outer) {
        observe_quotient(target);
    } else {
        target = candidate < target ? candidate : target;
        constexpr int threads = 64 + 64;
        int quotient = threads / target;
        observe_quotient(quotient);
    }
}

void multiplied_instead(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads * target;
    observe_quotient(quotient);
}

void reversed_division(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = target / threads;
    observe_quotient(quotient);
}

void wrong_denominator(int target, const int candidate, int other) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / other;
    observe_quotient(quotient);
}

void rewritten_between(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    target = 32;
    const int threads = 128;
    int quotient = threads / target;
    observe_quotient(quotient);
}

void aliased_denominator(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    using Ref = int&;
    Ref alias = target;
    const int threads = 128;
    int quotient = threads / alias;
    observe_quotient(quotient);
}

void static_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    static int quotient = threads / target;
    observe_quotient(quotient);
}

void narrow_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    short quotient = threads / target;
    observe_quotient(quotient);
}

void negative_numerator(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = -128;
    int quotient = threads / target;
    observe_quotient(quotient);
}

void multiple_declarators(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target, peer = 0;
    observe_quotient(quotient + peer);
}

void aliased_numerator(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    const int& numerator = threads;
    int quotient = numerator / target;
    observe_quotient(quotient);
}

void cast_numerator(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = static_cast<short>(threads) / target;
    observe_quotient(quotient);
}

void boolean_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    bool quotient = threads / target;
    observe_quotient(quotient);
}
