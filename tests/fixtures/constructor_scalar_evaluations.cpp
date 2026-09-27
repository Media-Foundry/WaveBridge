struct Config {
    Config(unsigned x, unsigned y, unsigned z) {}
};
void good(int x, int y) { Config value(x, y, 1); }
void bad_write(int x, int y) { Config value(x, ++y, 1); }
int opaque();
void bad_call(int x, int y) { Config value(opaque(), y, 1); }
struct Defaults { Defaults(unsigned x, unsigned y = 1) {} };
void default_argument(int x) { Defaults value(x); }
