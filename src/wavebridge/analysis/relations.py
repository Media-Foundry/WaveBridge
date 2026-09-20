"""Describe declared ownership without claiming to recover source intent."""

from wavebridge.ir.model import Program


def describe(program: Program) -> dict:
    k = program.kernel
    return {
        "origin": "user_supplied_structured_model",
        "source_recovery": "not_implemented",
        "model_sha256": program.fingerprint(),
        "data_format": {"quantization_group": k.quantization_group},
        "ownership": {
            "row": "block * (block_threads // cooperation_width) + thread // cooperation_width",
            "lane": "thread % cooperation_width",
            "column": "lane + iteration * column_stride, while column < columns",
            "writer_lane": k.writer_lane,
        },
        "collective": {
            "operation": "guarded_synchronous_shuffle_down_add",
            "width": k.reduction_width,
            "offsets": list(k.reduction_offsets),
        },
        "physical_wave_width": "not_modeled",
        "program": program.to_dict(),
    }
