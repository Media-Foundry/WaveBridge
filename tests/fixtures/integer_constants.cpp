// Frontend regression, not a GPU workload or manually provided relation oracle.
constexpr int original_width = 32;
constexpr int renamed_width = 32;
constexpr int block_threads = original_width * 8;
constexpr int quotient = -7 / 3;
constexpr int remainder = -7 % 3;
constexpr unsigned int unsigned_value = 32u;
int mutable_width = 32;
constexpr int arbitrary_entry() { return block_threads + renamed_width; }
