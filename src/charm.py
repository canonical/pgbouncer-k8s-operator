#!/usr/bin/env -S LD_LIBRARY_PATH=lib python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import enum
import functools
import json
import logging
import math
import os
import socket
from configparser import ConfigParser
from signal import SIGHUP
from typing import Dict, List, Optional, Union, get_args

import lightkube
import psycopg2
from charms.data_platform_libs.v0.data_interfaces import DataPeerData, DataPeerUnitData
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.postgresql_k8s.v0.postgresql_tls import PostgreSQLTLS
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_coordinator_k8s.v0.charm_tracing import trace_charm
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from jinja2 import Template
from ops import (
    ActiveStatus,
    BlockedStatus,
    ConfigChangedEvent,
    JujuVersion,
    MaintenanceStatus,
    PebbleReadyEvent,
    Relation,
    WaitingStatus,
    main,
)
from ops.pebble import ConnectionError as PebbleConnectionError
from ops.pebble import Layer, ServiceStatus

from config import CharmConfig
from constants import (
    APP_SCOPE,
    AUTH_FILE_DATABAG_KEY,
    AUTH_FILE_PATH,
    CFG_FILE_DATABAG_KEY,
    CLIENT_RELATION_NAME,
    CONTAINER_UNAVAILABLE_MESSAGE,
    EXTENSIONS_BLOCKING_MESSAGE,
    K8S_SERVICE_CONNECT_TIMEOUT,
    METRICS_PORT,
    MONITORING_PASSWORD_KEY,
    PEER_RELATION_NAME,
    PG_GROUP,
    PG_USER,
    PGB,
    PGB_DIR,
    PGB_LOG_DIR,
    SECRET_DELETED_LABEL,
    SECRET_INTERNAL_LABEL,
    SECRET_KEY_OVERRIDES,
    TLS_CA_FILE,
    TLS_CERT_FILE,
    TLS_KEY_FILE,
    TRACING_PROTOCOL,
    TRACING_RELATION_NAME,
    UNIT_SCOPE,
    WAITING_FOR_K8S_SERVICE_MESSAGE,
    Scopes,
)
from relations.backend_database import BackendDatabaseRequires
from relations.db import DbProvides
from relations.peers import Peers
from relations.pgbouncer_provider import PgBouncerProvider
from upgrade import PgbouncerUpgrade, get_pgbouncer_k8s_dependencies_model

logger = logging.getLogger(__name__)


class ServiceType(enum.Enum):
    """Supported K8s service types."""

    CLUSTER_IP = "ClusterIP"
    NODE_PORT = "NodePort"
    LOAD_BALANCER = "LoadBalancer"
    FALSE_LOWER = "false"
    NODE_PORT_LOWER = "nodeport"
    LOAD_BALANCER_LOWER = "loadbalancer"

    def __str__(self):
        """The string representation of the enum."""
        if self is ServiceType.FALSE_LOWER:
            return "ClusterIP"
        elif self is ServiceType.NODE_PORT_LOWER:
            return "NodePort"
        elif self is ServiceType.LOAD_BALANCER_LOWER:
            return "LoadBalancer"

        return self.value

    def __eq__(self, other):
        """The equality of the enum."""
        return str(self) == str(other)


CLUSTER_IP_SERVICE_TYPE = ServiceType("ClusterIP")
NODE_PORT_SERVICE_TYPE = ServiceType("NodePort")
LOAD_BALANCER_SERVICE_TYPE = ServiceType("LoadBalancer")


@functools.cache
def get_pod(unit_name: str, model_name: str) -> lightkube.resources.core_v1.Pod:
    """Get the pod for the provided unit name."""
    lightkube_client = lightkube.Client()
    return lightkube_client.get(
        res=lightkube.resources.core_v1.Pod,
        name=unit_name.replace("/", "-"),
        namespace=model_name,
    )


@functools.cache
def get_node(unit_name: str, model_name: str) -> lightkube.resources.core_v1.Node:
    """Return the node for the provided unit name."""
    node_name = get_pod(unit_name, model_name).spec.nodeName
    lightkube_client = lightkube.Client()
    return lightkube_client.get(
        res=lightkube.resources.core_v1.Node,
        name=node_name,
        namespace=model_name,
    )


@trace_charm(
    tracing_endpoint="tracing_endpoint",
    extra_types=(
        BackendDatabaseRequires,
        DbProvides,
        GrafanaDashboardProvider,
        LogProxyConsumer,
        MetricsEndpointProvider,
        Peers,
        PgBouncerProvider,
        PgbouncerUpgrade,
    ),
)
class PgBouncerK8sCharm(TypedCharmBase):
    """A class implementing charmed PgBouncer."""

    config_type = CharmConfig

    def __init__(self, *args):
        super().__init__(*args)

        self._namespace = self.model.name
        self.peer_relation_app = DataPeerData(
            self.model,
            relation_name=PEER_RELATION_NAME,
            secret_field_name=SECRET_INTERNAL_LABEL,
            deleted_label=SECRET_DELETED_LABEL,
        )
        self.peer_relation_unit = DataPeerUnitData(
            self.model,
            relation_name=PEER_RELATION_NAME,
            secret_field_name=SECRET_INTERNAL_LABEL,
            deleted_label=SECRET_DELETED_LABEL,
        )

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

        self.peers = Peers(self)
        self.backend = BackendDatabaseRequires(self)
        self.client_relation = PgBouncerProvider(self)
        self.legacy_db_relation = DbProvides(self, admin=False)
        self.legacy_db_admin_relation = DbProvides(self, admin=True)

        self.k8s_service_name = f"{self.app.name}-service"
        unit_name = self.unit.name.replace("/", "-")

        self.tls = PostgreSQLTLS(
            self,
            PEER_RELATION_NAME,
            [
                self.unit_pod_hostname,
                self.k8s_service_name,
                f"{self.k8s_service_name}.{self.model.name}.svc.cluster.local",
                unit_name,
                f"{unit_name}.{self.app.name}-endpoints.{self.model.name}.svc.cluster.local",
                self.app.name,
                f"{self.app.name}.{self.app.name}-endpoints",
                f"{self.app.name}.{self.app.name}-endpoints.{self.model.name}.svc.cluster.local",
                f"{self.app.name}-endpoints",
                f"{self.app.name}-endpoints.{self.model.name}.svc.cluster.local",
                f"{self.app.name}.{self.model.name}.svc.cluster.local",
            ],
        )

        self._cores = max(min(os.cpu_count(), 4), 2)
        self._services = [
            {
                "name": f"{PGB}_{service_id}",
                "id": service_id,
                "dir": f"{PGB_DIR}/instance_{service_id}",
                "ini_path": f"{PGB_DIR}/instance_{service_id}/pgbouncer.ini",
                "log_dir": f"{PGB_LOG_DIR}/instance_{service_id}",
            }
            for service_id in range(self._cores)
        ]
        self._metrics_service = "metrics_server"
        self.grafana_dashboards = GrafanaDashboardProvider(self)
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[{"static_configs": [{"targets": [f"*:{METRICS_PORT}"]}]}],
        )
        self.loki_push = LogProxyConsumer(
            self,
            log_files=[f"{service['log_dir']}/pgbouncer.log" for service in self._services],
            relation_name="logging",
            container_name="pgbouncer",
        )

        self.upgrade = PgbouncerUpgrade(
            self,
            model=get_pgbouncer_k8s_dependencies_model(),
            relation_name="upgrade",
            substrate="k8s",
        )
        self.tracing = TracingEndpointRequirer(
            self, relation_name=TRACING_RELATION_NAME, protocols=[TRACING_PROTOCOL]
        )

        self.lightkube_client = lightkube.Client()
        self.INSUFFICIENT_PERMISSIONS_MESSAGE = (
            f"Insufficient permissions, try: `juju trust {self.app.name} --scope=cluster`"
        )

    @property
    def tracing_endpoint(self) -> Optional[str]:
        """Otlp http endpoint for charm instrumentation."""
        if self.tracing.is_ready():
            return self.tracing.get_endpoint(TRACING_PROTOCOL)

    def get_service(self) -> Optional[lightkube.resources.core_v1.Service]:
        """Get the managed k8s service."""
        try:
            service = self.lightkube_client.get(
                res=lightkube.resources.core_v1.Service,
                name=self.k8s_service_name,
                namespace=self.model.name,
            )
        except lightkube.core.exceptions.ApiError as e:
            if e.status.code == 404:
                return None
            raise

        return service

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def reconcile_k8s_service(self, port_changed: bool = False) -> bool:
        """Create or delete a nodeport service for external node connectivity."""
        expose_external = self.config.expose_external
        try:
            desired_service_type = ServiceType(expose_external)
        except ValueError:
            logger.warning(f"Invalid config value {expose_external=}")
            self.unit.status = BlockedStatus("Invalid expose-external config value")
            return False

        service = self.get_service()
        service_exists = service is not None
        service_type = service_exists and ServiceType(service.spec.type)
        if not port_changed and service_exists and service_type == desired_service_type:
            return True

        pod0 = get_pod(self.unit.name, self.model.name)

        annotations = (
            json.loads(self.config.loadbalancer_extra_annotations)
            if desired_service_type == LOAD_BALANCER_SERVICE_TYPE
            else {}
        )

        desired_service = lightkube.resources.core_v1.Service(
            metadata=lightkube.models.meta_v1.ObjectMeta(
                name=self.k8s_service_name,
                namespace=self.model.name,
                ownerReferences=pod0.metadata.ownerReferences,  # the stateful set
                labels={"app.kubernetes.io/name": self.app.name},
                annotations=annotations,
            ),
            spec=lightkube.models.core_v1.ServiceSpec(
                ports=[
                    lightkube.models.core_v1.ServicePort(
                        name="pgbouncer",
                        port=self.config.listen_port,
                        targetPort=self.config.listen_port,
                    ),
                ],
                type=str(desired_service_type),
                selector={"app.kubernetes.io/name": self.app.name},
            ),
        )

        logger.info(f"Creating desired service {desired_service_type=}")
        try:
            self.lightkube_client.apply(desired_service, field_manager=self.app.name)
        except lightkube.ApiError as e:
            if e.status.code == 403:
                self.on_deployed_without_trust()
                return False
            logger.exception("Failed to create K8s service")
            raise

        logger.info(f"Request to create desired service {desired_service_type=} dispatched")

        if self.backend.postgres:
            self.unit.status = MaintenanceStatus(WAITING_FOR_K8S_SERVICE_MESSAGE)

        return True

    @property
    def version(self) -> str:
        """Returns the version Pgbouncer."""
        container = self.unit.get_container(PGB)
        if container.can_connect():
            try:
                output, _ = container.exec(
                    ["pgbouncer", "--version"], user=PG_USER, group=PG_USER
                ).wait_output()
                if output:
                    return output.split("\n")[0].split(" ")[1]
            except Exception:
                logger.exception("Unable to get Pgbouncer version")
                return ""
        return ""

    def _init_config(self, container) -> bool:
        """Helper method to initialise the configuration file and directories."""
        # Initialise filesystem - _push_file()'s make_dirs option sets the permissions for those
        # dirs to root, so we build them ourselves to control permissions.
        for service in self._services:
            if not container.exists(service["dir"]):
                container.make_dir(
                    service["dir"],
                    user=PG_USER,
                    group=PG_USER,
                    permissions=0o700,
                )
            if not container.exists(service["log_dir"]):
                container.make_dir(
                    service["log_dir"],
                    user=PG_USER,
                    group=PG_USER,
                    permissions=0o700,
                )

        self.render_pgb_config()
        # Render the logrotate config
        with open("templates/logrotate.j2") as file:
            template = Template(file.read())
        container.push(
            "/etc/logrotate.d/pgbouncer",
            template.render(service_ids=range(self._cores)),
        )
        return True

    def _on_pgbouncer_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Define and start pgbouncer workload.

        Deferrals:
            - If checking pgb running raises an error, implying that the pgbouncer services are not
              yet accessible in the container.
            - If the unit is waiting for certificates to be issued
        """
        container = event.workload

        if not self._init_config(container):
            event.defer()
            return

        if auth_file := self.get_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY):
            self.render_auth_file(auth_file)

        # in case of pod restart
        if all(self.tls.get_tls_files()):
            self.push_tls_files_to_workload(False)

        pebble_layer = self._pgbouncer_layer()
        container.add_layer(PGB, pebble_layer, combine=True)
        container.replan()

        self.update_status()

        self.unit.set_workload_version(self.version)

        self.peers.unit_databag["container_initialised"] = "True"

    @property
    def is_container_ready(self) -> bool:
        """Check if we can connect to the container and it was already initialised."""
        return (
            self.unit.get_container(PGB).can_connect()
            and "container_initialised" in self.peers.unit_databag
        )

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration.

        Deferrals:
            - If reloading the pgbouncer pebble service throws a ConnectionError (Implying that
              the pebble service is not yet ready)
        """
        if not self.is_container_ready:
            logger.debug("_on_config_changed deferred: container not ready")
            event.defer()
            return

        if not self.configuration_check():
            return

        old_port = self.peers.app_databag.get("current_port")
        port_changed = old_port != str(self.config.listen_port)
        if self.unit.is_leader() and port_changed:
            # This emits relation-changed events to every client relation, so only do it when
            # necessary
            self.update_client_connection_info()

        if self.unit.is_leader() and not self.reconcile_k8s_service(port_changed=port_changed):
            return

        self.render_pgb_config()
        try:
            if self.check_pgb_running():
                self.reload_pgbouncer(restart=port_changed)
        except PebbleConnectionError:
            event.defer()

        if self.unit.is_leader() and port_changed:
            # Only update the config once the services have been restarted
            self.peers.app_databag["current_port"] = str(self.config.listen_port)

        self.update_status()
        if self.unit.is_leader() and self.backend.postgres and self.check_service_connectivity():
            self.update_client_connection_info()

    def _pgbouncer_layer(self) -> Layer:
        """Returns a default pebble config layer for the pgbouncer container.

        Since PgBouncer is single-threaded, we auto-generate multiple pgbouncer services to make
        use of all the available cpu cores on a unit. This necessitates that we have separate
        directories for each instance, since otherwise pidfiles and logfiles will conflict. Ports
        are reused by setting "so_reuseport=1" in the pgbouncer config. This is enabled by default
        in pgb.DEFAULT_CONFIG.

        When viewing logs (including exporting them to COS), use the pebble service logs, rather
        than viewing individual logfiles.

        Returns:
            A pebble configuration layer for as many charm services as there are available CPU
            cores
        """
        pebble_services = {
            "logrotate": {
                "command": "sh -c 'logrotate -v /etc/logrotate.conf; sleep 5'",
                "startup": "enabled",
                "backoff-delay": "24h",
                "backoff-factor": 1,
                "override": "replace",
                "after": [service["name"] for service in self._services],
            },
            self._metrics_service: self._generate_monitoring_service(self.backend.postgres),
        }
        for service in self._services:
            pebble_services[service["name"]] = {
                "summary": f"pgbouncer service {service['id']}",
                "user": PG_USER,
                "group": PG_GROUP,
                # -R flag reuses sockets on restart
                "command": f"pgbouncer {service['ini_path']}",
                "startup": "enabled",
                "override": "replace",
            }
        return Layer({
            "summary": "pgbouncer layer",
            "description": "pebble config layer for pgbouncer",
            "services": pebble_services,
        })

    def _get_readonly_dbs(self, databases: Dict) -> Dict[str, str]:
        readonly_dbs = {}
        if self.backend.relation and "*" in databases:
            read_only_endpoints = self.backend.get_read_only_endpoints()
            sorted_rhosts = [r_host.split(":")[0] for r_host in read_only_endpoints]
            sorted_rhosts.sort()
            r_hosts = ",".join(sorted_rhosts)
            if r_hosts:
                for r_host in read_only_endpoints:
                    r_port = r_host.split(":")[1]
                    break

                backend_databases = json.loads(self.peers.app_databag.get("readonly_dbs", "[]"))
                for name in backend_databases:
                    readonly_dbs[f"{name}_readonly"] = {
                        "host": r_hosts,
                        "dbname": name,
                        "port": r_port,
                        "auth_dbname": databases["*"]["auth_dbname"],
                        "auth_user": self.backend.auth_user,
                    }
        return readonly_dbs

    def _collect_readonly_dbs(self) -> None:
        if self.unit.is_leader() and self.backend.postgres:
            existing_dbs = [db["name"] for db in self.get_relation_databases().values()]
            existing_dbs += ["postgres", "pgbouncer"]
            try:
                with self.backend.postgres._connect_to_database(
                    PGB
                ) as conn, conn.cursor() as cursor:
                    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
                    results = cursor.fetchall()
                conn.close()
            except psycopg2.Error:
                logger.warning("PostgreSQL connection failed")
                return
            readonly_dbs = [db[0] for db in results if db and db[0] not in existing_dbs]
            readonly_dbs.sort()
            self.peers.app_databag["readonly_dbs"] = json.dumps(readonly_dbs)

    def _on_update_status(self, _) -> None:
        """Update Status hook.

        Sets BlockedStatus if we have no backend database; if we can't connect to a backend, this
        charm serves no purpose.
        """
        self.update_status()

        self.peers.update_leader()
        self._collect_readonly_dbs()

        # Update relation connection information. This is necessary because we don't receive any
        # information when the leader is removed, but we still need to have up-to-date connection
        # information in all the relation databags. Furthermore, endpoints need to be updated
        # after confirming that the K8s service is connectable.
        self.update_client_connection_info()

    def configuration_check(self) -> bool:
        """Check that configuration is valid."""
        try:
            _ = self.config
            return True
        except ValueError:
            self.unit.status = BlockedStatus("Configuration Error. Please check the logs")
            logger.exception("Invalid configuration")
            return False

    def _get_node_address(self, node) -> str:
        # OpenStack will return an internal hostname, not externally accessible
        # Preference: ExternalIP > InternalIP > Hostname
        for typ in ["ExternalIP", "InternalIP", "Hostname"]:
            for address in node.status.addresses:
                if address.type == typ:
                    return address.address

    def get_node_hosts(self) -> set[str]:
        """Return the node ports of nodes where units of this app are scheduled."""
        peer_relation = self.model.get_relation(PEER_RELATION_NAME)
        if not peer_relation:
            return set()

        hosts = set()
        for unit in peer_relation.units | {self.model.unit}:
            node = get_node(unit.name, self.model.name)
            hosts.add(self._get_node_address(node))
        return hosts

    def get_hosts_ports(self, port_type: str) -> str:  # noqa: C901
        """Gets the host and port for the endpoint depending of type of service."""
        if port_type not in ["rw", "ro"]:
            raise ValueError("Invalid port type")

        service = self.get_service()
        if not service:
            return ""

        port = self.config.listen_port

        service_type = ServiceType(service.spec.type)

        if service_type == CLUSTER_IP_SERVICE_TYPE:
            return f"{self.k8s_service_name}.{self.model.name}.svc.cluster.local:{self.config.listen_port}"
        elif service_type == NODE_PORT_SERVICE_TYPE:
            hosts = self.get_node_hosts()

            for p in service.spec.ports:
                if p.name == "pgbouncer":
                    node_port = p.nodePort

            return ",".join(sorted({f"{host}:{node_port}" for host in hosts}))
        elif service_type == LOAD_BALANCER_SERVICE_TYPE and service.status.loadBalancer.ingress:
            if len(service.status.loadBalancer.ingress) != 0:
                ip = service.status.loadBalancer.ingress[0].ip
                hostname = service.status.loadBalancer.ingress[0].hostname

            if ip:
                return f"{ip}:{port}"

            if hostname:
                return f"{hostname}:{port}"

        return ""

    @property
    def read_write_endpoints(self) -> str:
        """The read write endpoints."""
        return self.get_hosts_ports("rw")

    @property
    def read_only_endpoints(self) -> str:
        """The read only endpoints."""
        return self.get_hosts_ports("ro")

    def check_service_connectivity(self) -> bool:
        """Check if the service is available (connectable with a socket)."""
        service = self.get_service()
        if not service:
            return False

        service_type = ServiceType(service.spec.type)

        endpoints_to_connect = [self.read_write_endpoints]
        if self.read_only_endpoints or service_type != CLUSTER_IP_SERVICE_TYPE:
            endpoints_to_connect.append(self.read_only_endpoints)

        for endpoints in endpoints_to_connect:
            if endpoints == "":
                logger.debug(
                    f"Empty endpoints {self.read_write_endpoints=} {self.read_only_endpoints=}"
                )
                return False

            for endpoint in endpoints.split(","):
                with socket.socket() as s:
                    s.settimeout(K8S_SERVICE_CONNECT_TIMEOUT)

                    host, port = endpoint.split(":")

                    try:
                        socket_connect_code = s.connect_ex((host, int(port)))
                    except socket.gaierror:
                        # Sometimes, it may take LB hostname record to propagate
                        logger.info(f"Unable to resolve {endpoint=}")
                        return False

                    if socket_connect_code != 0:
                        logger.info(f"Unable to connect to {endpoint=}")
                        return False

        return True

    def update_status(self):
        """Health check to update pgbouncer status based on charm state."""
        if self.unit.status.message == EXTENSIONS_BLOCKING_MESSAGE:
            return

        if not self.configuration_check():
            return

        if self.backend.postgres is None:
            self.unit.status = BlockedStatus("waiting for backend database relation to initialise")
            return

        if not self.backend.ready:
            self.unit.status = BlockedStatus("backend database relation not ready")
            return

        if self.unit.is_leader() and not self.check_service_connectivity():
            if self.unit.status.message != WAITING_FOR_K8S_SERVICE_MESSAGE:
                self.unit.status = BlockedStatus("K8s service not connectable")

            return

        try:
            if self.check_pgb_running():
                self.unit.status = ActiveStatus()
        except PebbleConnectionError:
            not_running = "pgbouncer not running"
            logger.error(not_running)
            self.unit.status = WaitingStatus(not_running)

    def _on_upgrade_charm(self, _) -> None:
        """Re-render the auth file, which is lost in a pod reschedule."""
        if auth_file := self.get_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY):
            self.render_auth_file(auth_file)

    def reload_pgbouncer(self, restart: bool = False) -> None:
        """Reloads pgbouncer application.

        Pgbouncer will not apply configuration changes without reloading, so this must be called
        after each time config files are changed.

        Raises:
            ops.pebble.ConnectionError if pgb service isn't accessible
        """
        logger.info("reloading pgbouncer application")

        pgb_container = self.unit.get_container(PGB)
        pebble_services = pgb_container.get_services()
        for service in self._services:
            if service["name"] not in pebble_services:
                # pebble_ready event hasn't fired so pgbouncer has not been added to pebble config
                raise PebbleConnectionError
            if restart or pebble_services[service["name"]].current != ServiceStatus.ACTIVE:
                pgb_container.restart(service["name"])
            else:
                pgb_container.send_signal(SIGHUP, service["name"])

        self.check_pgb_running()

    def _generate_monitoring_service(self, enabled: bool = True) -> Dict[str, str]:
        if enabled and (stats_password := self.get_secret(APP_SCOPE, MONITORING_PASSWORD_KEY)):
            command = (
                f'pgbouncer_exporter --web.listen-address=:{METRICS_PORT} --pgBouncer.connectionString="'
                f'postgres://{self.backend.stats_user}:{stats_password}@localhost:{self.config.listen_port}/pgbouncer?sslmode=disable"'
            )
            startup = "enabled"
        else:
            command = "true"
            startup = "disabled"
        return {
            "override": "replace",
            "summary": "postgresql metrics exporter",
            "after": [service["name"] for service in self._services],
            "user": PG_USER,
            "group": PG_GROUP,
            "command": command,
            "startup": startup,
        }

    def toggle_monitoring_layer(self, enabled: bool) -> None:
        """Starts or stops the monitoring service."""
        pebble_layer = Layer({
            "services": {self._metrics_service: self._generate_monitoring_service(enabled)}
        })
        pgb_container = self.unit.get_container(PGB)
        pgb_container.add_layer(PGB, pebble_layer, combine=True)
        if enabled:
            pgb_container.replan()
        else:
            pgb_container.stop(self._metrics_service)
        self.check_pgb_running()

    def check_pgb_running(self):
        """Checks that pgbouncer pebble service is running, and updates status accordingly."""
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            if self.unit.status.message != EXTENSIONS_BLOCKING_MESSAGE:
                self.unit.status = WaitingStatus(CONTAINER_UNAVAILABLE_MESSAGE)
            logger.warning(CONTAINER_UNAVAILABLE_MESSAGE)
            return False

        pebble_services = pgb_container.get_services()

        services = [service["name"] for service in self._services]
        if self.backend.ready:
            services.append(self._metrics_service)

        for service in services:
            if service not in pebble_services:
                # pebble_ready event hasn't fired so pgbouncer layer has not been added to pebble
                raise PebbleConnectionError
            pgb_service_status = pgb_container.get_services().get(service).current
            if pgb_service_status != ServiceStatus.ACTIVE:
                pgb_not_running = f"PgBouncer service {service} not running: service status = {pgb_service_status}"
                if self.unit.status.message != EXTENSIONS_BLOCKING_MESSAGE:
                    self.unit.status = BlockedStatus(pgb_not_running)
                logger.warning(pgb_not_running)
                return False

        return True

    def get_hostname_by_unit(self, unit_name: str) -> str:
        """Create a DNS name for a PgBouncer unit.

        Args:
            unit_name: the juju unit name, e.g. "pgbouncer-k8s/1".

        Returns:
            A string representing the hostname of the PgBouncer unit.
        """
        unit_id = unit_name.split("/")[1]
        return f"{self.app.name}-{unit_id}.{self.app.name}-endpoints"

    def _scope_obj(self, scope: Scopes):
        if scope == APP_SCOPE:
            return self.app
        if scope == UNIT_SCOPE:
            return self.unit

    def peer_relation_data(self, scope: Scopes) -> DataPeerData:
        """Returns the peer relation data per scope."""
        if scope == APP_SCOPE:
            return self.peer_relation_app
        elif scope == UNIT_SCOPE:
            return self.peer_relation_unit

    def _translate_field_to_secret_key(self, key: str) -> str:
        """Change 'key' to secrets-compatible key field."""
        if not JujuVersion.from_environ().has_secrets:
            return key
        key = SECRET_KEY_OVERRIDES.get(key, key)
        new_key = key.replace("_", "-")
        return new_key.strip("-")

    def get_secret(self, scope: Scopes, key: str) -> Optional[str]:
        """Get secret from the secret storage."""
        if scope not in get_args(Scopes):
            raise RuntimeError("Unknown secret scope.")

        peers = self.model.get_relation(PEER_RELATION_NAME)
        if not peers:
            return None

        secret_key = self._translate_field_to_secret_key(key)
        # Old translation in databag is to be taken
        if result := self.peer_relation_data(scope).fetch_my_relation_field(peers.id, key):
            return result

        return self.peer_relation_data(scope).get_secret(peers.id, secret_key)

    def set_secret(self, scope: Scopes, key: str, value: Optional[str]) -> Optional[str]:
        """Set secret from the secret storage."""
        if scope not in get_args(Scopes):
            raise RuntimeError("Unknown secret scope.")

        if not value:
            return self.remove_secret(scope, key)

        peers = self.model.get_relation(PEER_RELATION_NAME)
        secret_key = self._translate_field_to_secret_key(key)
        # Old translation in databag is to be deleted
        self.peers.scoped_peer_data(scope).pop(key, None)
        self.peer_relation_data(scope).set_secret(peers.id, secret_key, value)

    def remove_secret(self, scope: Scopes, key: str) -> None:
        """Removing a secret."""
        if scope not in get_args(Scopes):
            raise RuntimeError("Unknown secret scope.")

        peers = self.model.get_relation(PEER_RELATION_NAME)
        secret_key = self._translate_field_to_secret_key(key)
        self.peer_relation_data(scope).delete_relation_data(peers.id, [secret_key])

    def push_tls_files_to_workload(self, update_config: bool = True) -> bool:
        """Uploads TLS files to the workload container."""
        key, ca, cert = self.tls.get_tls_files()
        if key is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_KEY_FILE}",
                key,
                0o400,
            )
        if ca is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_CA_FILE}",
                ca,
                0o400,
            )
        if cert is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_CERT_FILE}",
                cert,
                0o400,
            )
        if update_config:
            return self.update_config()
        return True

    def update_config(self) -> bool:
        """Updates PgBouncer config file based on the existence of the TLS files."""
        self.render_pgb_config(True)

        return True

    # =============================
    #  File Management
    #  TODO: extract into new file
    # =============================

    def push_file(self, path, file_contents, perms):
        """Pushes file_contents to path, with the given permissions."""
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            logger.warning("unable to connect to container")
            self.unit.status = WaitingStatus(
                "Unable to push config to container - container unavailable."
            )
            return

        pgb_container.push(
            path,
            file_contents,
            user=PG_USER,
            group=PG_USER,
            permissions=perms,
            make_dirs=True,
        )

    def delete_file(self, path):
        """Deletes the file at `path`."""
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            logger.warning("unable to connect to container")
            self.unit.status = WaitingStatus(
                "Unable to delete file from container - container unavailable."
            )
            return

        pgb_container.remove_path(path)

    def set_relation_databases(self, databases: Dict[int, Dict[str, Union[str, bool]]]) -> None:
        """Updates the relation databases."""
        self.peers.app_databag["pgb_dbs_config"] = json.dumps(databases)

    def get_relation_databases(self) -> Dict[str, Dict[str, Union[str, bool]]]:
        """Get relation databases."""
        if "pgb_dbs_config" in self.peers.app_databag:
            return json.loads(self.peers.app_databag["pgb_dbs_config"])
        # Nothing set in the config peer data trying to regenerate based on old data in case of update.
        elif not self.unit.is_leader() and (
            cfg := self.get_secret(APP_SCOPE, CFG_FILE_DATABAG_KEY)
        ):
            try:
                parser = ConfigParser()
                parser.optionxform = str
                parser.read_string(cfg)
                old_cfg = dict(parser)
                if databases := old_cfg.get("databases"):
                    databases.pop("DEFAULT", None)
                    result = {}
                    i = 1
                    for database in dict(databases):
                        if database.endswith("_standby") or database.endswith("_readonly"):
                            continue
                        result[str(i)] = {"name": database, "legacy": False}
                        i += 1
                    return result
            except Exception:
                logger.exception("Unable to parse legacy config format")
        return {}

    def generate_relation_databases(self) -> Dict[str, Dict[str, Union[str, bool]]]:
        """Generates a mapping between relation and database and sets it in the app databag."""
        if not self.unit.is_leader():
            return {}

        databases = {}
        add_wildcard = False
        for relation in self.model.relations.get("db", []):
            database = self.legacy_db_relation.get_databags(relation)[0].get("database")
            if database:
                databases[str(relation.id)] = {
                    "name": database,
                    "legacy": True,
                }

        for relation in self.model.relations.get("db-admin", []):
            database = self.legacy_db_admin_relation.get_databags(relation)[0].get("database")
            if database:
                databases[str(relation.id)] = {
                    "name": database,
                    "legacy": True,
                }
                add_wildcard = True

        for rel_id, data in self.client_relation.database_provides.fetch_relation_data(
            fields=["database", "extra-user-roles"]
        ).items():
            database = data.get("database")
            roles = data.get("extra-user-roles", "").lower().split(",")
            if database:
                databases[str(rel_id)] = {
                    "name": database,
                    "legacy": False,
                }
            if "admin" in roles or "superuser" in roles or "createdb" in roles:
                add_wildcard = True
        if add_wildcard:
            databases["*"] = {"name": "*", "auth_dbname": database, "legacy": False}
        self.set_relation_databases(databases)
        return databases

    def _get_relation_config(self) -> [Dict[str, Dict[str, Union[str, bool]]]]:
        """Generate pgb config for databases and admin users."""
        if not self.backend.relation or not (databases := self.get_relation_databases()):
            return {}

        # In postgres, "endpoints" will only ever have one value. Other databases using the library
        # can have more, but that's not planned for the postgres charm.
        if not (postgres_endpoint := self.backend.postgres_databag.get("endpoints")):
            return {}
        host, port = postgres_endpoint.split(":")

        read_only_endpoints = self.backend.get_read_only_endpoints()
        sorted_rhosts = [r_host.split(":")[0] for r_host in read_only_endpoints]
        sorted_rhosts.sort()
        r_hosts = ",".join(sorted_rhosts)
        if r_hosts:
            for r_host in read_only_endpoints:
                r_port = r_host.split(":")[1]
                break

        pgb_dbs = {}

        for database in databases.values():
            name = database["name"]
            if name == "*":
                continue
            pgb_dbs[name] = {
                "host": host,
                "dbname": name,
                "port": port,
                "auth_user": self.backend.auth_user,
            }
            if r_hosts:
                pgb_dbs[f"{name}_readonly"] = {
                    "host": r_hosts,
                    "dbname": name,
                    "port": r_port,
                    "auth_user": self.backend.auth_user,
                }
                if database["legacy"]:
                    pgb_dbs[f"{name}_standby"] = pgb_dbs[f"{name}_readonly"]
        if "*" in databases:
            pgb_dbs["*"] = {
                "host": host,
                "port": port,
                "auth_user": self.backend.auth_user,
                "auth_dbname": databases["*"]["auth_dbname"],
            }
        return pgb_dbs

    def render_pgb_config(self, reload_pgbouncer=False, restart=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Every time the config is rendered, `peers.update_cfg` is called. This updates the config in
        the peer databag if this unit is the leader, propagating the config file to all units,
        which will then update their local config, so each unit isn't figuring out its own config
        constantly. This is valuable because the leader unit is the only unit that can read app
        databags, so this information would have to be propagated to peers anyway. Therefore, it's
        most convenient to have a single source of truth for the whole config.

        Args:
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
            restart: Whether to restart the service when reloading.
        """
        perm = 0o400

        if not self.configuration_check():
            return

        max_db_connections = self.config.max_db_connections
        if max_db_connections == 0:
            default_pool_size = 20
            min_pool_size = 10
            reserve_pool_size = 10
        else:
            effective_db_connections = max_db_connections / self._cores
            default_pool_size = math.ceil(effective_db_connections / 2)
            min_pool_size = math.ceil(effective_db_connections / 4)
            reserve_pool_size = math.ceil(effective_db_connections / 4)
        service_ids = [service["id"] for service in self._services]
        with open("templates/pgb_config.j2") as file:
            template = Template(file.read())
            databases = self._get_relation_config()
            readonly_dbs = self._get_readonly_dbs(databases)
            enable_tls = all(self.tls.get_tls_files())
            for service in self._services:
                self.push_file(
                    service["ini_path"],
                    template.render(
                        databases=databases,
                        readonly_databases=readonly_dbs,
                        peer_id=service["id"],
                        socket_dir=service["dir"],
                        peers=service_ids,
                        log_file=f"{service['log_dir']}/pgbouncer.log",
                        pid_file=f"{service['dir']}/pgbouncer.pid",
                        listen_port=self.config.listen_port,
                        pool_mode=self.config.pool_mode,
                        max_db_connections=max_db_connections,
                        default_pool_size=default_pool_size,
                        min_pool_size=min_pool_size,
                        reserve_pool_size=reserve_pool_size,
                        stats_user=self.backend.stats_user,
                        auth_query=self.backend.auth_query,
                        auth_file=AUTH_FILE_PATH,
                        enable_tls=enable_tls,
                        key_file=f"{PGB_DIR}/{TLS_KEY_FILE}",
                        ca_file=f"{PGB_DIR}/{TLS_CA_FILE}",
                        cert_file=f"{PGB_DIR}/{TLS_CERT_FILE}",
                    ),
                    perm,
                )
        logger.info("pushed new pgbouncer.ini config files to pgbouncer container")

        if reload_pgbouncer:
            self.reload_pgbouncer(restart)

    def render_auth_file(self, auth_file: str, reload_pgbouncer=False):
        """Renders the given auth_file to the correct location."""
        self.push_file(AUTH_FILE_PATH, auth_file, 0o400)
        logger.info("pushed new auth file to pgbouncer container")

        if reload_pgbouncer:
            self.reload_pgbouncer()

    # =====================
    #  Relation Utilities
    # =====================

    def update_client_connection_info(self):
        """Update connection info in client relations.

        TODO rename
        """
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres or not self.unit.is_leader():
            return

        port = self.config.listen_port

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.update_connection_info(relation, port)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.update_connection_info(relation, port)

        for relation in self.model.relations.get(CLIENT_RELATION_NAME, []):
            self.client_relation.update_connection_info(relation)

    @property
    def unit_pod_hostname(self, name="") -> str:
        """Creates the pod hostname from its name."""
        return socket.getfqdn(name)

    @property
    def _has_blocked_status(self) -> bool:
        """Returns whether the unit is in a blocked state."""
        return isinstance(self.unit.status, BlockedStatus)

    @property
    def client_relations(self) -> List[Relation]:
        """Return the list of established client relations."""
        relations = []
        for relation_name in ["database", "db", "db-admin"]:
            for relation in self.model.relations.get(relation_name, []):
                relations.append(relation)
        return relations

    def on_deployed_without_trust(self) -> None:
        """Blocks the application and returns a specific error message for deployments made without --trust."""
        logger.warning(self.INSUFFICIENT_PERMISSIONS_MESSAGE)
        self.unit.status = BlockedStatus(self.INSUFFICIENT_PERMISSIONS_MESSAGE)


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
