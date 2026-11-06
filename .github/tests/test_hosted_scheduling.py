# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, INP001
"""Regression model for the workflow's approval gates after a skipped branch.

GitHub's documented dependency-chain skip rule is modelled here, not executed.
Actual scheduler acceptance still requires a hosted run through approval.
"""

import os
import re
import subprocess
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / 'workflows/release-preparation.yml'


def job_block(job: str) -> str:
    return re.split(r'\n  \S', WORKFLOW.read_text().split(f'\n  {job}:\n', 1)[1], maxsplit=1)[0]


def ancestors_succeeded(job: str, results: dict[str, str]) -> bool:
    needs = re.search(r'(?m)^    needs: (.+)$', job_block(job))
    if needs is None:
        return True
    dependencies = needs[1].strip('[]').replace(' ', '').split(',')
    return all(
        results.get(dependency, 'success') == 'success'
        and ancestors_succeeded(dependency, results)
        for dependency in dependencies
    )


def gate_runs(job: str, results: dict[str, str], *, cancelled: bool = False) -> bool:
    """Evaluate the small conjunction grammar used by these job gates.

    The alternative branch is a skipped ancestor on both prepare and resume.
    Without a status function GitHub applies its implicit success condition to
    the dependency chain. Reject unknown expressions rather than guessing.
    """
    block = job_block(job)
    condition = re.search(r'(?m)^    if: (.+)(?:\n      .+)*', block)
    if condition is None:
        return not cancelled and ancestors_succeeded(job, results)
    expression = condition.group().removeprefix('    if: ').replace('>-', '').strip().strip('"')
    terms = [term.strip() for term in expression.split('&&')]
    if not any(term in {'always()', '!cancelled()'} for term in terms) and (
        cancelled or not ancestors_succeeded(job, results)
    ):
        return False
    for term in terms:
        if term == 'always()':
            continue
        if term == '!cancelled()':
            if cancelled:
                return False
            continue
        match = re.fullmatch(r"needs\.([\w-]+)\.result == 'success'", term)
        if match is None:
            message = f'Unsupported gate expression: {term}'
            raise AssertionError(message)
        if results[match[1]] != 'success':
            return False
    return True


class HostedSchedulingChecks(unittest.TestCase):
    def test_approval_and_recheck_run_after_either_alternative_branch_is_skipped(self) -> None:
        for branch in ('prepare', 'resume'):
            results = {
                'retain': 'success' if branch == 'prepare' else 'skipped',
                'resume': 'success' if branch == 'resume' else 'skipped',
                'hosted-checkpoint': 'success',
                'hosted-approval': 'success',
            }
            for job in ('hosted-approval', 'hosted-recheck'):
                with self.subTest(branch=branch, job=job):
                    self.assertTrue(gate_runs(job, results))

    def test_failed_skipped_or_cancelled_prerequisites_cannot_open_the_gates(self) -> None:
        for outcome in ('failure', 'skipped', 'cancelled'):
            for prerequisite in ('hosted-checkpoint', 'hosted-approval'):
                results = {'hosted-checkpoint': 'success', 'hosted-approval': 'success'}
                results[prerequisite] = outcome
                with self.subTest(prerequisite=prerequisite, outcome=outcome):
                    self.assertFalse(gate_runs('hosted-recheck', results))
                    if prerequisite == 'hosted-checkpoint':
                        self.assertFalse(gate_runs('hosted-approval', results))
        for job in ('hosted-approval', 'hosted-recheck'):
            with self.subTest(cancelled=job):
                self.assertFalse(gate_runs(
                    job,
                    {'hosted-checkpoint': 'success', 'hosted-approval': 'success'},
                    cancelled=True,
                ))

    def test_report_fails_when_required_hosted_recheck_did_not_finish(self) -> None:
        report = WORKFLOW.read_text().split('\n  report:\n', 1)[1]
        self.assertIn('HOSTED_PROOF_REQUIRED:', report)
        self.assertIn('HOSTED_RECHECK_RESULT:', report)
        command = report.split('        run: |\n', 1)[1]
        command = '\n'.join(line.removeprefix('          ') for line in command.splitlines())
        # Replace the external coordinator process, preserving the real shell
        # command and its outcome argument and exit status.
        command = 'python() { printf "%s\\n" "$@"; }\n' + command
        for required, result, expected in (
            ('true', 'success', 0),
            ('true', 'skipped', 1),
            ('true', 'failure', 1),
            ('true', 'cancelled', 1),
            ('false', 'skipped', 0),
        ):
            with self.subTest(required=required, result=result):
                completed = subprocess.run(  # noqa: S603
                    ['bash', '-eu', '-c', command],  # noqa: S607
                    env={
                        **os.environ,
                        'HOSTED_PROOF_REQUIRED': required,
                        'HOSTED_RECHECK_RESULT': result,
                        'OUTCOME': 'success',
                        'RECORD_ID': '10',
                        'RECORD_TARGET': 'fixture',
                        'REPOSITORY_ID': '123',
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, expected, completed.stderr)
                self.assertIn(
                    '--outcome\nfailure' if expected else '--outcome\nsuccess', completed.stdout,
                )


if __name__ == '__main__':
    unittest.main()
