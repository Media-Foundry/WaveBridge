// Synthetic CPU controls: iteration bounds alone are not output coverage.
// These are NOT upstream kernels, source-recovery results, or GPU evidence.
#include <iostream>
#include <string>
#include <vector>

struct Observation {
  int work = 0, writes = 0, missing = 0, duplicate = 0, outside = 0;
};

Observation observe(int n, const std::vector<int>& starts, int shift, int repeats) {
  std::vector<int> touches(n + 32, 0);
  Observation result;
  for (int lane : starts) {
    for (int it = 0; it < 4; ++it) {
      int column = lane + 32 * it;
      if (column < n) {
        ++result.work;
        for (int copy = 0; copy < repeats; ++copy) {
          ++touches.at(column + shift);
          ++result.writes;
        }
      } else {
        break;
      }
    }
  }
  for (int column = 0; column < n; ++column) {
    if (touches[column] == 0) ++result.missing;
    if (touches[column] > 1) result.duplicate += touches[column] - 1;
  }
  for (int column = n; column < static_cast<int>(touches.size()); ++column)
    result.outside += touches[column];
  return result;
}

bool record(const char* name, int n, const std::vector<int>& starts, int shift,
            int repeats, int work, int writes, int missing, int duplicate, int outside) {
  const auto observed = observe(n, starts, shift, repeats);
  const bool matches = observed.work == work && observed.writes == writes &&
      observed.missing == missing && observed.duplicate == duplicate && observed.outside == outside;
  std::cout << "{\"case\":\"" << name << "\",\"n\":" << n
            << ",\"participants\":" << starts.size()
            << ",\"work\":" << observed.work << ",\"writes\":" << observed.writes
            << ",\"missing\":" << observed.missing << ",\"duplicate_writes\":" << observed.duplicate
            << ",\"outside_logical_domain\":" << observed.outside
            << ",\"matches_expected\":" << (matches ? "true" : "false") << "}\n";
  return matches;
}

int main() {
  std::vector<int> starts;
  for (int lane = 0; lane < 32; ++lane) starts.push_back(lane);
  bool ok = record("reference", 128, starts, 0, 1, 128, 128, 0, 0, 0);
  ok = record("shifted_store", 128, starts, 1, 1, 128, 128, 1, 0, 1) && ok;
  ok = record("double_store", 128, starts, 0, 2, 128, 256, 0, 128, 0) && ok;
  ok = record("header_truncates_129", 129, starts, 0, 1, 128, 128, 1, 0, 0) && ok;
  starts.back() = 0;
  ok = record("duplicate_start", 128, starts, 0, 1, 128, 128, 4, 4, 0) && ok;
  starts.pop_back();
  ok = record("missing_start", 128, starts, 0, 1, 124, 124, 4, 0, 0) && ok;
  return ok ? 0 : 1;
}
