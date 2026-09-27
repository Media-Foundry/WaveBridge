namespace declared_api {
int warp_size();
}

namespace unrelated_api {
int warp_size() { return 99; }
}

namespace defined_api {
int warp_size() { return 32; }
}

void declaration_only() {
  int width = declared_api::warp_size();
  (void)width;
}

void definition_visible() {
  int width = defined_api::warp_size();
  (void)width;
}

void not_direct_initializer() {
  int width = 1 + declared_api::warp_size();
  (void)width;
}

