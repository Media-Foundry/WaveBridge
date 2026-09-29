enum Positive { zero = 0, implicit_one, last = 1055 };
enum Signed { negative = -4, signed_zero = 0, signed_one };
enum class Wide : unsigned long long { large = 9223372036854775815ULL };
enum Opaque : unsigned;
template<class T> struct Dependent { enum E { value = T::value }; };
