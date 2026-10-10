// Application kernels: hash uploaded candidates on GPU and return full digests.
__kernel void md5_batch(__global const pw_t *pws, __global uint *output, uint count)
{
    uint gid = get_global_id(0);
    if (gid >= count) return;
    md5_ctx_t ctx;
    md5_init(&ctx);
    md5_update_global(&ctx, pws[gid].i, pws[gid].pw_len);
    md5_final(&ctx);
    for (uint i = 0; i < 4; ++i) output[gid * 8 + i] = ctx.h[i];
}

__kernel void sha1_batch(__global const pw_t *pws, __global uint *output, uint count)
{
    uint gid = get_global_id(0);
    if (gid >= count) return;
    sha1_ctx_t ctx;
    sha1_init(&ctx);
    sha1_update_global_swap(&ctx, pws[gid].i, pws[gid].pw_len);
    sha1_final(&ctx);
    for (uint i = 0; i < 5; ++i) output[gid * 8 + i] = ctx.h[i];
}
