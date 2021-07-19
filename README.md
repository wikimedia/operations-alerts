Prometheus alerts repository
====

In this repository you will find the Prometheus-based alerts deployed to production, split by team.

The alerts will be deployed to all site-local Prometheus instances by default (i.e. ops, k8s, etc)

For more information refer to Alertmanager's wikitech page: https://wikitech.wikimedia.org/wiki/Alertmanager

Testing
----
CI will run `tox` on this repository at code review time. You can also run tests locally by calling `tox` (python 3) and have `promtool` (Prometheus >= 2.10) installed locally.

On Debian systems the `promtool` binary is part of `prometheus` package, which will also start the Prometheus server. To stop the server and stop it from starting at boot issue the following:

    systemctl stop prometheus
    systemctl mask prometheus