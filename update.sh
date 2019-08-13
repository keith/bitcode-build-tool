#!/bin/bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 XCODE_PATH" >&2
  exit 1
fi

xcode_path="$1"
usr_path="$xcode_path/Contents/Developer/usr"

rm -rf bin lib
mkdir bin lib
cp -R "$usr_path/bin/bitcode-build-tool" bin
cp -R "$usr_path/lib/bitcode_build_tool" lib
find . -name "*.pyc" -delete
