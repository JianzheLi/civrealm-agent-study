#!/usr/bin/env bash
export CIVSTUDY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/home/ubuntu/jianzheli/University/envs/civrealm/bin:$PATH"
export PYTHONPATH="$CIVSTUDY_ROOT/src:$CIVSTUDY_ROOT/third_party/civrealm/src"
export TMPDIR="$CIVSTUDY_ROOT/tmp"
export XDG_CACHE_HOME="$CIVSTUDY_ROOT/cache"
export CIVREALM_HOST_URL=localhost
export CIVREALM_HOST_PORT=18080
export CUDA_VISIBLE_DEVICES=""
export MPLBACKEND=Agg
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
cd "$CIVSTUDY_ROOT"
