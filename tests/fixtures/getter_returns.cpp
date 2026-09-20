extern unsigned long external_index(unsigned int);

static unsigned int getter_bridge() {
  return external_index(0);
}

unsigned int getter_entry() {
  return getter_bridge();
}
