#!/bin/sh
# Build and run every unit and UI test on the named simulator; print a compact summary.
set -u
if [ $# -ne 1 ]; then
    echo "usage: ./check.sh <simulator-name>" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 2
bundle=.bench-build/results.xcresult
mkdir -p .bench-build && rm -rf "$bundle"
xcodebuild test -project ListApp.xcodeproj -scheme ListApp \
    -destination "platform=iOS Simulator,name=$1" \
    -derivedDataPath .bench-build/DerivedData -resultBundlePath "$bundle" -quiet \
    > .bench-build/xcodebuild.log 2>&1
status=$?
if [ ! -d "$bundle" ]; then
    echo "TESTS total=0 passed=0 failed=0 skipped=0"
    echo "ERROR no result bundle (xcodebuild exit $status); see .bench-build/xcodebuild.log"
    tail -n 20 .bench-build/xcodebuild.log
    exit 1
fi
xcrun xcresulttool get test-results summary --path "$bundle" --compact | /usr/bin/python3 -c '
import json, sys
summary = json.load(sys.stdin)
print("TESTS total=%d passed=%d failed=%d skipped=%d" % (summary["totalTestCount"], summary["passedTests"],
      summary["failedTests"], summary["skippedTests"]))
for failure in summary.get("testFailures", []):
    print("FAILED %s: %s" % (failure.get("testIdentifierString") or failure.get("testName"),
          " ".join(str(failure.get("failureText", "")).split())[:200]))
sys.exit(0 if summary["failedTests"] == 0 and summary["totalTestCount"] > 0 else 1)
'
summary_status=$?
[ "$status" -eq 0 ] && [ "$summary_status" -eq 0 ]
