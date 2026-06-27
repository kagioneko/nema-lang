#!/bin/bash
# Nema v0.6.0 demo script

cd /home/mayutama/nema

echo "=== Nema v0.6.0 Demo ==="
sleep 1

echo ""
echo "# set<T> type — deduplicated collection"
sleep 0.5
cat set_demo.nema
sleep 1

echo ""
echo "# Running set_demo..."
sleep 0.5
echo "call SetTest test_set
exit" | python3 nema.py set_demo.nema 2>&1 | grep -E "^\s+\[print\]|^\[実行OK\]"

sleep 1
echo ""
echo "# stdlib: math + collections"
sleep 0.5
echo "call Main run
exit" | python3 nema.py stdlib_demo.nema 2>&1 | grep -E "^\s+\[print\]|^\[実行OK\].*run"

sleep 1
echo ""
echo "# Type check"
sleep 0.3
python3 nema.py stdlib_demo.nema --check

echo ""
echo "Done! Nema v0.6.0"
