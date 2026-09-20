from dataclasses import replace

from wavebridge.ir.model import Program, reduction_offsets


def retile(source: Program, target_width: int) -> Program:
    offsets = reduction_offsets(target_width)
    block = source.launch.block_threads
    if block < target_width or block % target_width:
        raise ValueError("block_threads must be divisible by target_width")
    rows_per_block = block // target_width
    kernel = replace(
        source.kernel,
        cooperation_width=target_width,
        column_stride=target_width,
        reduction_width=target_width,
        reduction_offsets=offsets,
    )
    launch = replace(source.launch, grid_blocks=(source.domain.rows + rows_per_block - 1) // rows_per_block)
    # Quantization grouping, input domain and numeric contract deliberately persist.
    return replace(source, kernel=kernel, launch=launch)
