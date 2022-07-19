#!/usr/bin/python3

# Use pytest to validate/test alerting rules files and their tests.
# For each directory of ALERTSDIR the following tests are ran:
# - each *_test.yaml file is a alerts unit test file, validate it with promtool
# - each non-test *.yaml file is an alerting rule file, validate it with promtool
# - additionally, each alerting rule file is checked for missing labels and annotations

import os
import pathlib
import re
import string
import subprocess
import urllib
import warnings
from pathlib import Path
from urllib.parse import quote, unquote

import pytest
import requests
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

    # this is to get a reproducible list
    return sorted(files)


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


@pytest.mark.ci()
@pytest.mark.parametrize("rulefile", all_rulefiles(SUBDIRS), ids=str)
def test_runbook_exists(rulefile):
    """Ensure that if the alert has a runbook, it actually exists"""
    with open(rulefile, encoding="utf-8") as rulefile_fd:
        groups = yaml.load(rulefile_fd, Loader=yaml.FullLoader)

    for group in groups["groups"]:
        for rule in group["rules"]:
            runbook = rule.get("annotations", {}).get("runbook", None)
            if runbook is not None:
                response = requests.get(runbook)
                assert response.status_code == 200 and response.text != "", (
                    f"Unable to fetch runbook {runbook}, please make sure that it exists and "
                    "it's reachable."
                )


@pytest.mark.parametrize(
    "rulefile",
    [
        rulefile
        for rulefile in all_rulefiles(SUBDIRS)
        if "team-wmcs" == rulefile.parent.parent.name
    ],
    ids=str,
)
def test_wmcs_runbook_is_defined(rulefile):
    """Make sure that there's at least one runbook define for all WMCS alerts."""
    with open(rulefile, encoding="utf-8") as rulefile_fd:
        groups = yaml.load(rulefile_fd, Loader=yaml.FullLoader)

    for group in groups["groups"]:
        for index, rule in enumerate(group["rules"]):
            runbook = rule.get("annotations", {}).get("runbook", None)
            assert (
                runbook
            ), f"Rule #{index} - alertname:{rule['alert']} has no runbook defined, please add one."


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

    if rule["labels"]["severity"] == "page":
        assert "#page" in rule["annotations"]["summary"]

    assert string.whitespace not in alertname, (
        "Alert names with spaces are hard to address and silence: %r" % alertname
    )

    for a in ("runbook", "dashboard"):
        if a in annotations:
            assert _url_is_quoted(annotations[a]), (
                "URL in %s contains unquoted characters, check warnings for details" % a
            )

    for a in wanted_annotations:
        if a not in annotations:
            warnings.warn(
                UserWarning("Annotation %r not found for alert %s" % (a, alertname))
            )


def _untemplate(string):
    """Return string without golang text/template markers."""

    return re.sub("{{.*}}", "", string)


def _url_is_quoted(url):
    """Check if url has been URL quoted. The check will ignore template markers since no quoting can be checked at this stage."""
    u = urllib.parse.urlparse(url)
    if not u.query or "=" not in u.query:
        return True

    # Basic split/parsing of qs variables, urllib.parse.parse_qs unquotes the result, which we don't want
    qs_vars = u.query.split("&")
    qs_pairs = [x.split("=", 1) for x in qs_vars]
    for el in qs_pairs:
        # qs variable with no value (e.g. 'fullscreen' in Grafana)
        if len(el) == 1:
            raw_name = el[0]
            raw_value = None
        else:
            raw_name, raw_value = el

        name = _untemplate(raw_name)
        if quote(unquote(name)) != name:
            warnings.warn(
                UserWarning(
                    "Unquoted query string variable %r: expected %r"
                    % (name, quote(name))
                )
            )
            return False

        if raw_value is None:
            continue

        value = _untemplate(raw_value)
        if quote(unquote(value)) != value:
            warnings.warn(
                UserWarning(
                    "Unquoted value for query string variable %r. Expected: %r Got: %r"
                    % (name, quote(value), value)
                )
            )
            return False

    return True


def _run_promtool(args, workdir):
    args.insert(0, "promtool")
    return subprocess.run(
        args,
        cwd=os.path.dirname(workdir),
        capture_output=True,
        encoding="utf8",
        env={"PATH": os.environ.get("PATH", "")},
    )
