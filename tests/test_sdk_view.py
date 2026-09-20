from pathlib import Path
import tempfile
import unittest

from runtime.probes.prepare_sdk_view import prepare


class SdkViewTests(unittest.TestCase):
    def make_sdk(self, root: Path) -> None:
        for relative, contents in {
            "lib/llvm/bin/clang++": "compiler-fixture",
            "lib/llvm/amdgcn/bitcode/ocml.bc": "device-library-fixture",
            "include/hip/hip_version.h": "#define HIP_VERSION_MAJOR 7\n",
            "lib/libamdhip64.so.7": "runtime-fixture",
        }.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

    def test_view_supplies_alias_without_modifying_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = root / "sdk with spaces"
            self.make_sdk(sdk)
            wrapper = prepare(sdk, root / "views", "gfx1100")
            view = wrapper.parent.parent
            self.assertTrue((view / "lib/libamdhip64.so").samefile(sdk / "lib/libamdhip64.so.7"))
            self.assertFalse((sdk / "lib/libamdhip64.so").exists())
            self.assertTrue((view / "manifest.json").is_file())
            self.assertIn("--rocm-device-lib-path", wrapper.read_text())
            self.assertNotEqual(wrapper, prepare(sdk, root / "views", "gfx1100"))

    def test_missing_matched_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / "sdk"
            self.make_sdk(sdk)
            (sdk / "include/hip/hip_version.h").write_text("#define HIP_VERSION_MAJOR 8\n")
            with self.assertRaisesRegex(ValueError, "runtime missing"):
                prepare(sdk, Path(directory) / "views", "gfx1100")

    def test_invalid_arch_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / "sdk"
            self.make_sdk(sdk)
            with self.assertRaises(ValueError):
                prepare(sdk, Path(directory) / "views", "gfx1100; echo unsafe")
            self.assertFalse((Path(directory) / "views").exists())
