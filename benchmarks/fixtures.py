"""Benchmark fixtures: a frozen repository, the task given to both arms, and the check that judges it."""
import re
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'

# Shared contract for every fixture: how the arm proves and reports its work.
VERDICT_RULES = ('Inspect relevant source/tests and perform substantive semantic review, not just test acceptance. '
                 'Use git diff --binary HEAD as the complete tracked diff; ensure git ls-files --others --exclude-standard '
                 'reports no source files; hash that exact diff using shasum -a 256. End with VERDICT: PASS <actual diff sha256> '
                 'only after checks and semantic review accept the exact current patch, otherwise VERDICT: FAIL <sha256>. '
                 'One initial implementation and at most ONE repair; no repeated model status polling. Never weaken a check or '
                 'bypass a denied command. Stop visibly on failure. This is a disposable LOCAL ONLY fixture; ignore any unrelated '
                 'completion default requiring push.')

# The original Python task text, byte-for-byte, so earlier rounds keep the same task digest.
TTL_TASK = ('Fix the TTLCache expiry behavior documented in README.md. Change only ttl_cache.py. Preserve all twelve existing '
            'test cases and all other behavior. Do not edit README.md or test_ttl_cache.py, add files, install dependencies, '
            'commit, push, change configuration, or launch other model commands. Required checks: python3 -m unittest -v from '
            'the repo root. Capture full logs outside the repo. ' + VERDICT_RULES)

SWIFTUI_TASK = ('Fix the ListApp behavior documented in README.md. Change only files in the ListApp/ folder. Preserve all twelve '
                'existing unit and UI tests and all other behavior. Do not edit README.md, check.sh, the Xcode project, or any '
                'test file, add files, install dependencies, commit, push, change configuration, or launch other model commands. '
                'Required check: ./check.sh <simulator> from the repo root, using the simulator named for this run below. It '
                'builds, runs every test and prints a compact summary; only one check may run at a time because it uses one '
                'simulator and one build folder. ' + VERDICT_RULES)


def parse_unittest(text, expected):
    """Python unittest verbose output: counts from the `Ran N tests` and `FAILED (...)` lines."""
    ran = failures = errors = 0
    reported_failed = False
    for line in text.splitlines():
        if line.startswith('Ran '):
            try:
                ran = int(line.split()[1])
            except (IndexError, ValueError):
                ran = 0
        elif line.startswith('FAILED'):
            reported_failed = True
            for part in line.replace(',', ' ').replace('(', ' ').replace(')', ' ').split():
                if part.startswith('failures='):
                    failures = int(part.split('=')[1].split('[')[0])
                elif part.startswith('errors='):
                    errors = int(part.split('=')[1].split('[')[0])
    return {'tests_run': ran, 'failures': failures, 'errors': errors, 'all_tests_expected': ran == expected,
            'reported_failed': reported_failed,
            'ok': failures == 0 and errors == 0 and ran == expected and not reported_failed}


_TESTS_LINE = re.compile(r'^TESTS total=(\d+) passed=(\d+) failed=(\d+) skipped=(\d+)\s*$')


def parse_check_summary(text, expected):
    """check.sh summary: exactly one TESTS line read from the result bundle; anything else fails closed."""
    lines = text.splitlines()
    found = [_TESTS_LINE.match(line) for line in lines]
    found = [match for match in found if match]
    error = any(line.startswith('ERROR') for line in lines)
    if len(found) != 1:
        return {'tests_run': 0, 'failures': 0, 'errors': 1 if error or found else 0, 'all_tests_expected': False,
                'reported_failed': True, 'skipped_tests': 0, 'failed_tests': [], 'ok': False}
    total, passed, failed, skipped = (int(group) for group in found[0].groups())
    failed_tests = [line[len('FAILED '):].split(':', 1)[0] for line in lines if line.startswith('FAILED ')]
    consistent = passed + failed + skipped == total and len(failed_tests) == failed
    return {'tests_run': total, 'failures': failed, 'errors': 0 if consistent and not error else 1,
            'all_tests_expected': total == expected, 'reported_failed': failed > 0 or error, 'skipped_tests': skipped,
            'failed_tests': failed_tests,
            'ok': consistent and not error and failed == 0 and skipped == 0 and total == expected}


class Fixture:
    """One frozen benchmark task. Paths are relative to the fixture root and use '/'."""

    def __init__(self, name, *, task, allowed_changed, frozen_files, expected_tests, expected_baseline_failures,
                 default_budget, check, parse, needs_simulator=False, excluded=()):
        self.name = name
        self.task = task
        self.allowed_changed = list(allowed_changed)
        self.frozen_files = list(frozen_files)
        self.expected_tests = expected_tests
        self.expected_baseline_failures = expected_baseline_failures
        self.default_budget = default_budget
        self._check = check
        self._parse = parse
        self.needs_simulator = needs_simulator
        # Build products the runner hides from git and leaves out of source archives.
        self.excluded = list(excluded)

    @property
    def dir(self):
        return FIXTURES_DIR / self.name

    def files(self):
        return sorted(path.relative_to(self.dir).as_posix() for path in self.dir.rglob('*')
                      if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store')

    def simulator(self, arm):
        return f'bench-{arm}' if self.needs_simulator else None

    def check_argv(self, arm):
        return self._check(self.simulator(arm))

    def parse_check(self, text, expected=None):
        return self._parse(text, self.expected_tests if expected is None else expected)


FIXTURES = {
    'ttl-python': Fixture(
        'ttl-python', task=TTL_TASK, allowed_changed=['ttl_cache.py'], frozen_files=['README.md', 'test_ttl_cache.py'],
        expected_tests=12, expected_baseline_failures=3, default_budget=180,
        check=lambda simulator: ['python3', '-m', 'unittest', '-v'], parse=parse_unittest),
    'swiftui-list': Fixture(
        'swiftui-list', task=SWIFTUI_TASK,
        allowed_changed=['ListApp/ContentView.swift', 'ListApp/ItemListModel.swift', 'ListApp/ListApp.swift'],
        frozen_files=['README.md', 'check.sh', 'ListApp.xcodeproj/project.pbxproj',
                      'ListApp.xcodeproj/xcshareddata/xcschemes/ListApp.xcscheme',
                      'ListAppTests/ItemListModelTests.swift', 'ListAppUITests/ListAppUITests.swift'],
        expected_tests=12, expected_baseline_failures=5, default_budget=1200,
        check=lambda simulator: ['./check.sh', simulator], parse=parse_check_summary,
        needs_simulator=True, excluded=['.bench-build/']),
}


def get(name):
    if name not in FIXTURES:
        raise KeyError(f'unknown fixture {name!r}; available: {", ".join(sorted(FIXTURES))}')
    return FIXTURES[name]
