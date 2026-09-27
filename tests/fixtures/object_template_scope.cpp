template <class T>
const T& select_min(const T& left, const T& right) {
    return left < right ? left : right;
}

typedef struct Config {
    unsigned x;
    unsigned y;

    Config(unsigned first, unsigned second = 1) : x(first), y(second) {}
} Config;

void consume(Config value) { (void)value; }

template <class Scalar, int Token>
void literal_init(int) {
    Config source(7);
    consume(source);
}

template <class Scalar, int Token>
void selected_init(int count) {
    Config source(select_min(count, 1024));
    consume(source);
}

template <class Scalar, int Token>
void direct_dynamic_init(int count) {
    Config source(count);
    consume(source);
}

void instantiate_object_templates(int count) {
    literal_init<int, 7>(count);
    selected_init<int, 7>(count);
    direct_dynamic_init<int, 7>(count);
}
