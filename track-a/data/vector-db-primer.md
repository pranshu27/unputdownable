# Vector Database Primer
## HNSW Index
HNSW builds a multi-layer graph where upper layers are sparse and lower layers are dense.
Search complexity is O(log N) and ef_search trades recall against latency.
## Quantization
Scalar quantization reduces memory 4x with a small recall loss.
Product quantization compresses further but requires rescoring for accuracy.
## Cost Model
| Component | Memory per 1M vectors |
|---|---|
| fp32 dense | 4096 MB |
| int8 scalar quantized | 1024 MB |
| PQ (m=16) | 256 MB |

Storage cost is dominated by dense vectors, not sparse indices.
