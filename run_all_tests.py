#!/usr/bin/env python3
"""
YouTube Story Maker - Automated QA Test Suite Runner
Runs all unit, integration, and E2E pipeline tests and produces a detailed QA Pass/Fail report.
"""

import os
import sys
import time
import json
from pathlib import Path

# Safe console re-encoding on Windows
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

STORY_STUDIO_DIR = Path(__file__).resolve().parent
TESTS_DIR = STORY_STUDIO_DIR / "tests"
BACKEND_DIR = STORY_STUDIO_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import pytest

class QATestResultCollector:
    """Pytest plugin to collect test execution metrics and results."""
    def __init__(self):
        self.results = []
        self.start_time = 0.0
        self.end_time = 0.0

    def pytest_sessionstart(self, session):
        self.start_time = time.time()

    def pytest_sessionfinish(self, session, exitstatus):
        self.end_time = time.time()

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.failed):
            module_name = report.location[0]
            test_name = report.location[2]
            status = "PASSED" if report.passed else ("FAILED" if report.failed else "SKIPPED")
            duration = report.duration
            error_msg = str(report.longrepr) if report.failed else None

            self.results.append({
                "module": module_name,
                "test": test_name,
                "status": status,
                "duration": round(duration, 3),
                "error": error_msg,
            })

def print_separator(char="=", width=80):
    print(char * width)

def run_qa_suite():
    print_separator("=")
    print("   YOUTUBE STORY MAKER - COMPREHENSIVE QA TEST SUITE")
    print("   Automated Verification of TTS, Image, FFmpeg Video, REST API & E2E")
    print_separator("=")
    print(f"[*] Workspace Root: {STORY_STUDIO_DIR}")
    print(f"[*] Tests Directory: {TESTS_DIR}")
    print()

    test_files = [
        "test_tts.py",
        "test_image.py",
        "test_video.py",
        "test_api.py",
        "test_comic.py",
        "test_vox_narrative.py",
        "test_adversarial_qa.py",
        "test_e2e_pipeline.py",
        "test_launcher.py",
    ]

    collector = QATestResultCollector()
    pytest_args = [
        "-v",
        "-s",
        "--tb=short",
        "-W", "ignore::DeprecationWarning",
    ] + [str(TESTS_DIR / f) for f in test_files]

    start_wall_clock = time.time()
    exit_code = pytest.main(pytest_args, plugins=[collector])
    total_elapsed = round(time.time() - start_wall_clock, 2)

    # Aggregate statistics
    results = collector.results
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["status"] == "PASSED")
    failed_tests = sum(1 for r in results if r["status"] == "FAILED")
    skipped_tests = sum(1 for r in results if r["status"] == "SKIPPED")
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0

    # Group by module
    modules = {}
    for r in results:
        mod = Path(r["module"]).name
        if mod not in modules:
            modules[mod] = []
        modules[mod].append(r)

    print()
    print_separator("=")
    print("                      DETAILED QA TEST REPORT BY MODULE")
    print_separator("=")
    print(f"{'Test Module':<26} | {'Total':<6} | {'Passed':<7} | {'Failed':<7} | {'Duration':<9} | {'Status'}")
    print_separator("-")

    for mod_name, items in modules.items():
        mod_total = len(items)
        mod_passed = sum(1 for i in items if i["status"] == "PASSED")
        mod_failed = sum(1 for i in items if i["status"] == "FAILED")
        mod_dur = round(sum(i["duration"] for i in items), 2)
        mod_status = "[PASS]" if mod_failed == 0 else "[FAIL]"
        print(f"{mod_name:<26} | {mod_total:<6} | {mod_passed:<7} | {mod_failed:<7} | {mod_dur:>6.2f}s   | {mod_status}")

    print_separator("-")
    print(f"{'OVERALL TOTALS':<26} | {total_tests:<6} | {passed_tests:<7} | {failed_tests:<7} | {total_elapsed:>6.2f}s   | {pass_rate:.1f}%")
    print_separator("=")

    # Breakdown of individual test cases
    print("\n[+] INDIVIDUAL TEST VERIFICATIONS:")
    for r in results:
        status_tag = "[PASS]" if r["status"] == "PASSED" else "[FAIL]"
        mod_name = Path(r["module"]).name
        print(f"  {status_tag} {mod_name} :: {r['test']:<45} ({r['duration']}s)")

    # Save JSON report
    report_data = {
        "project": "YouTube Story Maker",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_elapsed_seconds": total_elapsed,
        "summary": {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "skipped": skipped_tests,
            "pass_rate_percentage": round(pass_rate, 2),
            "verdict": "PASS" if failed_tests == 0 and total_tests > 0 else "FAIL",
        },
        "modules": {
            mod_name: {
                "total": len(items),
                "passed": sum(1 for i in items if i["status"] == "PASSED"),
                "failed": sum(1 for i in items if i["status"] == "FAILED"),
                "duration_seconds": round(sum(i["duration"] for i in items), 2),
                "status": "PASS" if all(i["status"] == "PASSED" for i in items) else "FAIL",
            }
            for mod_name, items in modules.items()
        },
        "tests": results,
    }

    report_json_path = STORY_STUDIO_DIR / "qa_test_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print()
    print(f"[*] QA JSON Report exported to: {report_json_path}")

    # Final verdict
    print()
    print_separator("=")
    if exit_code == 0 and failed_tests == 0 and total_tests > 0:
        print(">>> FINAL QA VERDICT: [100% PASS] ALL TESTS PASSED SUCCESSFULLY! <<<")
        print("    Software is stable, functional, and ready for production.")
        print_separator("=")
        return 0
    else:
        print(f">>> FINAL QA VERDICT: [FAILED] {failed_tests} tests failed. <<<")
        print_separator("=")
        return 1

if __name__ == "__main__":
    sys.exit(run_qa_suite())
