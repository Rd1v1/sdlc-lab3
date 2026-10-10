// Application orchestration kernels using the vendored MIT Argon2 primitives.
__kernel void argon_init(__global const pw_t *pws, __global const salt_t *salt,
                         __global const argon2_options_t *parameters, __global argon2_block_t *memory,
                         uint count)
{
    uint gid = get_global_id(0);
    if (gid >= count) return;
    argon2_options_t opts = parameters[0];
    argon2_init_gg(&pws[gid], salt, &opts, memory + gid * opts.memory_block_count);
}

__kernel void argon_segment(__global const argon2_options_t *parameters,
                            __global argon2_block_t *memory, uint count, uint pass, uint slice)
{
    uint candidate = get_group_id(0);
    if (candidate >= count) return;
    uint thread = get_local_id(0);
    uint lane = get_local_id(1);
    __local ulong shuffle[8][32];
    argon2_options_t opts = parameters[0];
    argon2_pos_t pos;
    pos.pass = pass; pos.slice = slice; pos.lane = lane;
    barrier(CLK_LOCAL_MEM_FENCE | CLK_GLOBAL_MEM_FENCE);
    argon2_fill_segment(memory + candidate * opts.memory_block_count, &opts, &pos,
                       shuffle[lane], thread, 32);
    barrier(CLK_LOCAL_MEM_FENCE | CLK_GLOBAL_MEM_FENCE);
}

__kernel void argon_final(__global const argon2_options_t *parameters,
                          __global argon2_block_t *memory, __global uint *output, uint count)
{
    uint gid = get_global_id(0);
    if (gid >= count) return;
    argon2_options_t opts = parameters[0];
    uint digest[8];
    argon2_final(memory + gid * opts.memory_block_count, &opts, digest);
    for (uint i = 0; i < 8; ++i) output[gid * 8 + i] = digest[i];
}
