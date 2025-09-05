#!/bin/zsh
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
export HOMEBREW_PREFIX="$(brew --prefix)"
export DYLD_FALLBACK_LIBRARY_PATH="$HOMEBREW_PREFIX/lib:$DYLD_FALLBACK_LIBRARY_PATH"
python3 -m uvicorn app.main:app --reload
