#!/usr/bin/python3

# Use pytest to validate/test alerting rules files and their tests.
# For each directory of ALERTSDIR the following tests are ran:
# - each *_test.yaml file is a alerts unit test file, validate it with promtool
# - each non-test *.yaml file is an alerting rule file, validate it with promtool
# - additionally, each alerting rule file is checked for missing labels and annotations

import os
import pathlib
import subprocess
import warnings

import pytest
import yaml

SUBDIRS = [
    x
    for x in os.listdir(os.environ.get("ALERTSDIR", "."))
    if os.path.isdir(x) and not x.startswith(".")
]


def all_testfiles(paths):
    """Return all files with alerting rules tests."""
    files = []

    for path in paths:
        p = pathlib.Path(path)
        files.extend(p.glob("**/*_test.yaml"))

    return files


def all_rulefiles(paths):
    """Return all alerting rule files."""
    files = []

    for path in paths:
        p = pathlib.Path(path)
        non_test_files = set(p.glob("**/*.yaml")) - set(p.glob("**/*_test.yaml"))
        files.extend(non_test_files)

    return files


@pytest.mark.parametrize("testfile", all_testfiles(SUBDIRS))
def test_alerts(testfile):
    """Run alert unit tests for testfile."""
    path = testfile.as_posix()
    p = subprocess.run(
        ["/usr/bin/promtool", "test", "rules", os.path.basename(path)],
        cwd=os.path.dirname(path),
        capture_output=True,
        encoding="utf8",
    )
    assert p.returncode == 0, "promtool test rules failed: %s\n%s" % (
        p.stdout,
        p.stderr,
    )


@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS))
def test_valid_rule(rulefile):
    """Validate rulefile with promtool"""

    path = rulefile.as_posix()
    p = subprocess.run(
        ["/usr/bin/promtool", "check", "rules", os.path.basename(path)],
        cwd=os.path.dirname(path),
        capture_output=True,
        encoding="utf8",
    )
    assert p.returncode == 0, "promtool check rules failed: %s\n%s" % (
        p.stdout,
        p.stderr,
    )


@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS))
def test_rule_metadata(rulefile):
    """Ensure rulefile has all the expected labels/annotations"""

    with open(rulefile) as f:
        alerts = yaml.load(f, Loader=yaml.FullLoader)

    for group in alerts["groups"]:
        for rule in group["rules"]:
            _validate_rule(rule)


def _validate_rule(rule):
    required_labels = ("severity", "team")
    required_annotations = ("summary", "description")
    wanted_annotations = ("dashboard", "runbook")

    labels = rule["labels"]
    annotations = rule["annotations"]
    alertname = rule["alert"]

    for l in required_labels:
        assert l in labels

    for a in required_annotations:
        assert a in annotations

    for a in wanted_annotations:
        if a not in annotations:
            warnings.warn(
                UserWarning("Annotation %r not found for alert %s" % (a, alertname))
            )
