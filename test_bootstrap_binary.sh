#!/bin/bash

# Test the Go bootstrap binary directly with logging

BINARY="/Users/morganescott/resume-builder/dashboard/bin/bootstrap"
LOGFILE="/tmp/bootstrap_test.log"

echo "Testing Go bootstrap binary..."
echo "Binary: $BINARY"
echo "Log file: $LOGFILE"
echo ""

# Redirect all output to log file, keep stderr visible
{
    echo "=== Starting bootstrap binary test ==="
    echo "Time: $(date)"
    echo "Terminal: $TERM"
    echo "TTY: $(tty)"
    echo ""

    # Run the binary with a timeout
    timeout 5 "$BINARY" > bootstrap_stdout.log 2> bootstrap_stderr.log
    EXIT_CODE=$?

    echo "Exit code: $EXIT_CODE"
    echo ""
    echo "=== Stdout (first 500 chars) ==="
    head -c 500 bootstrap_stdout.log
    echo ""
    echo ""
    echo "=== Stderr (first 500 chars) ==="
    head -c 500 bootstrap_stderr.log
    echo ""

    if [ $EXIT_CODE -eq 124 ]; then
        echo "ERROR: Binary timed out (hung for 5+ seconds)"
    elif [ $EXIT_CODE -ne 0 ]; then
        echo "ERROR: Binary exited with code $EXIT_CODE"
    else
        echo "Binary exited normally"
    fi

} | tee "$LOGFILE"

echo ""
echo "Full logs saved to:"
echo "  $LOGFILE"
echo "  bootstrap_stdout.log"
echo "  bootstrap_stderr.log"
