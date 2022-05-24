#!/usr/bin/python3

# Use pytest to validate/test alerting rules files and their tests.
# For each directory of ALERTSDIR the following tests are ran:
# - each *_test.yaml file is a alerts unit test file, validate it with promtool
# - each non-test *.yaml file is an alerting rule file, validate it with promtool
# - additionally, each alerting rule file is checked for missing labels and annotations

import os
import pathlib
import re
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


def test_yml_extension():
    for path in SUBDIRS:
        p = pathlib.Path(path)
        yml_files = set(p.glob("**/*.yml"))
        assert yml_files == set(), "use yaml extension not yml"


@pytest.mark.parametrize("testfile", all_testfiles(SUBDIRS), ids=str)
def test_alerts(testfile):
    """Run alert unit tests for testfile."""
    path = testfile.as_posix()
    p = _run_promtool(["test", "rules", os.path.basename(path)], path)
    assert p.returncode == 0, "promtool test rules failed: %s\n%s" % (
        p.stdout,
        p.stderr,
    )


@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS), ids=str)
def test_valid_rule(rulefile):
    """Validate rulefile with promtool"""

    path = rulefile.as_posix()
    p = _run_promtool(["check", "rules", os.path.basename(path)], path)
    assert p.returncode == 0, "promtool check rules failed: %s\n%s" % (
        p.stdout,
        p.stderr,
    )


@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS), ids=str)
def test_rule_metadata(rulefile):
    """Ensure rulefile has all the expected labels/annotations"""

    with open(rulefile) as f:
        alerts = yaml.load(f, Loader=yaml.FullLoader)

    for group in alerts["groups"]:
        for rule in group["rules"]:
            _validate_rule_metadata(rule)


@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS), ids=str)
def test_deploy_metadata(rulefile):
    """Ensure the file 'deploy-tag' metadata is valid"""

    with open(rulefile) as f:
        tag = _get_tag(f, "deploy-tag")
        if tag is None:
            return

    tags = re.split(r",\s*", tag)

    if len(tags) > 1:
        for value in ("global", "local"):
            assert value not in tags, "%r not allowed with multiple tags" % value


def _get_tag(fobj, name):
    """Read tag 'name' from fobj "header". The header ends when a non-comment or non-empty line, the
    rest is ignored. Return None on tag not found."""

    # FIXME Use format strings
    tag_re = re.compile("^# *{name}: *(.+)$".format(name=name))

    for line in fobj:
        m = tag_re.match(line)
        if m:
            return m.group(1)
        # stop looking after comments and empty lines
        if not line.startswith("#") and not line.startswith(" "):
            return None
    return None


def _validate_rule_metadata(rule):
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

    if rule['labels']['severity'] == 'page':
        assert '#page' in rule['annotations']['summary']

    for a in wanted_annotations:
        if a not in annotations:
            warnings.warn(
                UserWarning("Annotation %r not found for alert %s" % (a, alertname))
            )


def _run_promtool(args, workdir):
    args.insert(0, "promtool")
    return subprocess.run(
        args,
        cwd=os.path.dirname(workdir),
        capture_output=True,
        encoding="utf8",
        env={"PATH": os.environ.get("PATH", "")},
    )


