"""Writes a tiny random Llama-architecture GGUF model, for testing the engine's plumbing only.
The weights are random, so its answers and similarity scores mean nothing. It shows that llama-server starts, serves /health, /v1/embeddings and /v1/chat/completions, and that the app talks to it."""
import numpy as np
import gguf

VOCAB = ["<unk>", "<s>", "</s>"] + ["<0x%02X>" % i for i in range(256)] + list("abcdefghijklmnopqrstuvwxyz ")


def write(path, embd_dim=32, ctx=512, seed=0):
    rng = np.random.default_rng(seed)
    V, E, F = len(VOCAB), embd_dim, embd_dim * 2
    w = gguf.GGUFWriter(path, "llama")
    w.add_context_length(ctx)
    w.add_embedding_length(E)
    w.add_block_count(1)
    w.add_feed_forward_length(F)
    w.add_head_count(4)
    w.add_head_count_kv(4)
    w.add_layer_norm_rms_eps(1e-5)
    w.add_rope_dimension_count(E // 4)
    w.add_tokenizer_model("llama")
    w.add_token_list(VOCAB)
    w.add_token_scores([0.0] * V)
    w.add_token_types([2, 3, 3] + [6] * 256 + [1] * (V - 259))
    w.add_bos_token_id(1)
    w.add_eos_token_id(2)
    w.add_unk_token_id(0)

    def m(*shape):
        return (rng.standard_normal(shape) * 0.1).astype(np.float32)

    ones = lambda n: np.ones(n, dtype=np.float32)
    w.add_tensor("token_embd.weight", m(V, E))
    w.add_tensor("output_norm.weight", ones(E))
    w.add_tensor("output.weight", m(V, E))
    w.add_tensor("blk.0.attn_norm.weight", ones(E))
    for n in ("attn_q", "attn_k", "attn_v", "attn_output"):
        w.add_tensor("blk.0.%s.weight" % n, m(E, E))
    w.add_tensor("blk.0.ffn_norm.weight", ones(E))
    w.add_tensor("blk.0.ffn_gate.weight", m(F, E))
    w.add_tensor("blk.0.ffn_up.weight", m(F, E))
    w.add_tensor("blk.0.ffn_down.weight", m(E, F))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path


if __name__ == "__main__":
    import sys
    print(write(sys.argv[1]))
