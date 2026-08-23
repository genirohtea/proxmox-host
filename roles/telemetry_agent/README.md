# Telemetry Agent

Ships a Proxmox host's metrics and journald logs to the Toyota cluster using one Grafana Alloy agent that pushes.

Push is intentional for this workload: Alloy performs local discovery, reads journald, buffers Prometheus remote write in a WAL, and needs only outbound connectivity. Stable external metrics endpoints that need
none of those properties should instead be polled from Toyota with a Prometheus Operator `ScrapeConfig`; see `klaus-homelab/toyota-cluster/apps/observability/INTEGRATION.md`.

## What it collects

| Source     | Component                                     | Notes                                                     |
| ---------- | --------------------------------------------- | --------------------------------------------------------- |
| Host OS    | `prometheus.exporter.unix`                    | Embedded node_exporter; no separate package or port       |
| ZFS        | `zfs` collector                               | ARC hit/miss and per-pool I/O                             |
| Scripts    | textfile collector                            | `/var/lib/node_exporter/textfile_collector`               |
| Proxmox VE | `prometheus-pve-exporter` on `127.0.0.1:9221` | Guests, storages, quorum, and replication                 |
| Disk SMART | `smartctl_exporter` on `127.0.0.1:9633`       | Health, temperature, wear, errors, and device metadata    |
| Logs       | `loki.source.journal`                         | Proxmox services, ZED, kernel, vfio-pci, and IOMMU events |

Every signal carries stable `host`, `site`, and `env` labels.

## Toyota prerequisites

The matching Toyota implementation provides:

1. Prometheus `enableRemoteWriteReceiver: true`.
1. Exact-path, `POST`-only HTTPRoutes:
   - `https://prometheus-push.<env>.<internal-domain>/api/v1/write`;
   - `https://loki-push.<env>.<internal-domain>/loki/api/v1/push`.
1. An Envoy Gateway `SecurityPolicy` on those route sections that validates the `Authorization` bearer value against the `telemetry-api-keys` Kubernetes Secret and removes it before proxying.
1. An ExternalSecret that reads a JSON API-key map from BWS.
1. A Toyota OpenTofu telemetry-client catalog that generates one API key per machine, publishes individual host secrets, and publishes the verifier map.

The existing Let's Encrypt wildcard certificate covers both hostnames, so this role uses the system trust store and needs no CA file.

## Enabling a host

Add the short hostname with the active `-a` rotation slot to `local.telemetry_clients` in Toyota's `deployments/secrets/observability.tofu`, apply the correct workspace, and obtain the BWS ID without exposing
its value:

```bash
tofu output telemetry_api_key_secret_refs
```

Then configure the Proxmox inventory:

```yaml
watt.internal.klaus.geniroh.com:
  telemetry_agent_enabled: true
  telemetry_agent_bws_api_key_id: <BWS-secret-ID-for-watt-a>
```

`telemetry_agent_bws_internal_domain_id` must also point to `kvk-klaus-homelab-prod-klaus-toyota-internal-domain`, or `telemetry_agent_internal_domain` may be supplied directly.

Run only this role while onboarding or rotating a client:

```bash
./run_proxmox_host.sh -H watt.internal.klaus.geniroh.com -t telemetry_agent
```

## Credential handling

The role fetches only this host's key from BWS. It writes the source file as `0600 root:root` and uses systemd `LoadCredential` to project it into `/run/credentials/alloy.service/telemetry-api-key`. The token
never appears in inventory, an environment file, or the rendered Alloy configuration.

One key authenticates both Prometheus and Loki. Compromising one host therefore requires revoking only that client's entry, not rotating credentials for every sender.

### Zero-downtime rotation

The verifier and host update independently, so do not replace a live token in place when a gap matters:

1. Add `watt-b` to Toyota's telemetry client catalog while `watt-a` remains and apply it. Envoy accepts both tokens.
1. Change `telemetry_agent_bws_api_key_id` to the new BWS ID and rerun this role.
1. Confirm new data from Toyota.
1. Remove `watt-a` from the catalog and apply it to revoke the old key. Reverse the slots on the next rotation.

The series label remains `host="watt"`; the BWS/Envoy client ID is only an authentication identity.

For a known compromise, remove the client from the Toyota catalog immediately and apply before issuing a replacement.

## PVE exporter credential

The exporter token is separate from telemetry ingress. The role creates a `prometheus@pve` user with the built-in read-only `PVEAuditor` role, mints a token, and writes it to
`/etc/prometheus-pve-exporter/pve.yml` at mode `0640`. PVE displays a token secret only once, so if that file is lost the role revokes the old token and creates a new one.

## Important variables

- `telemetry_agent_enabled`: master switch; default `false`.
- `telemetry_agent_bws_api_key_id`: per-host BWS secret ID.
- `telemetry_agent_alloy_apt_version`: pinned Alloy Debian package version; default `1.18.1-1`.
- `telemetry_agent_pve_exporter_version`: exporter version; default `3.9.0`.
- `telemetry_agent_smartctl_exporter_version`: exporter version; default `0.14.0`.
- `telemetry_agent_scrape_interval`: default `30s`.
- `telemetry_agent_journal_max_age`: default `12h`.
- `telemetry_agent_cluster_env` and `telemetry_agent_internal_domain`: build the push hostnames. Override the complete push URLs if routes move.

## Verifying

```bash
systemctl status alloy prometheus-pve-exporter smartctl_exporter
curl -s localhost:12345/-/ready
curl -s 'localhost:9221/pve?target=localhost' | head
curl -s localhost:9633/metrics | grep -E 'smartctl_device_(smart_status|temperature)'
journalctl -u alloy -f
```

`/-/ready` proves the Alloy configuration loaded, not that the remote endpoints accepted data. Confirm delivery in Toyota:

```promql
up{host="watt"}
```

```logql
{job="journald", host="watt"}
```

## SMART and textfile producers

The role runs prometheus-community's `smartctl_exporter` on loopback and Alloy scrapes it as `job="smartctl-exporter"`. The exporter owns physical-disk discovery and SMART metric parsing; zvol, loop, zram, and
device-mapper nodes are excluded. The `disk_health` role is deliberately limited to email reports and scheduled self-tests.

The `zfs` role publishes vdev health every five minutes, while the embedded ZFS collector supplies pool state and performance metrics. The `ipmi_fan_control` role publishes fan RPM and zone duty through the
node-exporter textfile collector because those BMC readings are outside smartctl_exporter's scope. It writes atomically through a temporary file and rename, so Alloy never scrapes a partial metric file.

## License

BSD-3-Clause
