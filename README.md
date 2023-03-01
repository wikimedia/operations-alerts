Prometheus alerts repository
====

In this repository you will find the Prometheus-based alerts deployed to
production, split by team.

The alerts will be deployed to all site-local Prometheus instances by default
(i.e. ops, k8s, etc)

For more information refer to Alertmanager's wikitech page:
https://wikitech.wikimedia.org/wiki/Alertmanager

Testing
----
CI will run `tox` on this repository at code review time. You can also run
tests locally by calling `tox` (python 3). You'll also need to have the
following tools in your `$PATH`:

* `promtool` Available in Linux distributions, or
  https://github.com/prometheus/prometheus/releases (>= 2.10 required)

* `pint` Available as a Debian package from
  https://wikitech.wikimedia.org/wiki/APT_repository or a single binary from
  https://github.com/cloudflare/pint/releases

On Debian systems the `promtool` binary is part of `prometheus` package, which
will also start the Prometheus server. To stop the server and stop it from
starting at boot issue the following:

    systemctl stop prometheus
    systemctl mask prometheus

To also disable the timers for various node exporters, run:

    systemctl list-timers prometheus* | perl -ne 'print "$1\n" if /(prometheus-.+\.timer)/' | \
        xargs sudo systemctl disable

Finally, to also disable `pint` at startup run the following:

    systemctl stop pint
    systemctl mask pint

Deploying
----
The repository is self-service for `wmf` LDAP group users. In other words, a +2
will trigger CI tests and merge (if tests pass). Post-merge the alerts will be
deployed at the next Puppet run (i.e. in 30 min).
