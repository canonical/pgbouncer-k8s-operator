# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import math
import socket
import unittest
from signal import SIGHUP
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

import lightkube
import psycopg2
import pytest
from jinja2 import Template
from ops import BlockedStatus, JujuVersion
from ops.model import RelationDataTypeError
from ops.testing import Harness
from parameterized import parameterized

from charm import PgBouncerK8sCharm
from constants import (
    BACKEND_RELATION_NAME,
    PEER_RELATION_NAME,
    PGB,
    SECRET_INTERNAL_LABEL,
)


class TestCharm(unittest.TestCase):
    def setUp(self):
        backend_ready_patch = patch(
            "relations.backend_database.BackendDatabaseRequires.ready",
            new_callable=PropertyMock,
            return_value=True,
        )
        backend_ready_patch.start()

        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        root = self.harness.get_filesystem_root(PGB)
        (root / "etc" / "logrotate.d").mkdir(parents=True, exist_ok=True)
        (root / "var" / "lib" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        (root / "var" / "log" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        self.harness.handle_exec(
            PGB, ["pgbouncer", "--version"], result="PGB 1.16.1\nOther things"
        )
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm

        self.rel_id = self.harness.model.relations[PEER_RELATION_NAME][0].id

    @pytest.fixture
    def use_caplog(self, caplog):
        self._caplog = caplog

    @patch("charm.PgBouncerK8sCharm.reconcile_k8s_service")
    @patch("charm.PgBouncerK8sCharm.update_client_connection_info")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_config_changed(
        self,
        _render,
        _update_connection_info,
        _,
    ):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        _render.reset_mock()

        mock_cores = 1
        self.charm._cores = mock_cores
        max_db_connections = 535

        self.harness.update_config({
            "pool_mode": "transaction",
            "max_db_connections": max_db_connections,
            "listen_port": 6464,
        })
        _render.assert_called_once_with(restart=True)
        _update_connection_info.assert_called_with()

    @patch(
        "charm.PgBouncerK8sCharm.is_container_ready", new_callable=PropertyMock, return_value=False
    )
    @patch("ops.charm.ConfigChangedEvent.defer")
    def test_on_config_changed_container_cant_connect(self, can_connect, defer):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        self.harness.update_config()
        defer.assert_called()

    def test_pgbouncer_layer(self):
        layer = self.charm._pgbouncer_layer()
        assert len(layer.services) == self.charm._cores + 2

    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_pgbouncer_pebble_ready(self, _render, _update_status):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        for service in self.charm._services:
            container_service = self.harness.model.unit.get_container(PGB).get_service(
                service["name"]
            )
            self.assertTrue(container_service.is_running())
        _update_status.assert_called_once_with()
        _render.assert_called_once_with()

    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("charm.PgBouncerK8sCharm.push_tls_files_to_workload")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_on_pgbouncer_pebble_ready_ensure_tls_files(
        self, get_tls_files, _render, push_tls_files_to_workload, _update_status
    ):
        get_tls_files.return_value = ("key", "ca", "cert")

        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation("certificates", "tls_op")
        self.harness.set_leader(True)
        # emit on start to ensure config file render
        self.charm.on.start.emit()

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        get_tls_files.assert_called_once_with()
        push_tls_files_to_workload.assert_called_once_with(False)
        _update_status.assert_called_once_with()
        _render.assert_called_once_with()

    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    @patch("ops.model.Container.send_signal")
    @patch(
        "charm.PgBouncerK8sCharm.auth_file",
        new_callable=PropertyMock,
        return_value="/dev/shm/pgbouncer-k8s_test",
    )
    @patch(
        "relations.backend_database.DatabaseRequires.fetch_relation_field",
        return_value="BACKNEND_USER",
    )
    @patch(
        "charm.BackendDatabaseRequires.relation", new_callable=PropertyMock, return_value=Mock()
    )
    @patch(
        "charm.BackendDatabaseRequires.postgres_databag",
        new_callable=PropertyMock,
        return_value={"endpoints": "HOST:PORT", "read-only-endpoints": "HOST2:PORT"},
    )
    @patch("charm.PgBouncerK8sCharm.get_relation_databases")
    @patch("charm.PgBouncerK8sCharm.push_file")
    def test_render_pgb_config(
        self,
        _push_file,
        _get_dbs,
        _postgres_databag,
        _backend_rel,
        _,
        __,
        _send_signal,
        _check_pgb_running,
    ):
        _get_dbs.return_value = {
            "1": {"name": "first_test", "legacy": True},
            "2": {"name": "second_test", "legacy": False},
        }

        # Assert we exit early if _can_connect returns false
        self.harness.set_can_connect(PGB, False)
        self.charm.render_pgb_config()
        assert not _send_signal.called

        del self.charm.backend.stats_user
        del self.charm.backend.admin_user
        del self.charm.backend.auth_query

        with open("templates/pgb_config.j2") as file:
            template = Template(file.read())
        self.harness.set_can_connect(PGB, True)
        self.charm.render_pgb_config()
        effective_db_connections = 100 / self.charm._cores
        default_pool_size = math.ceil(effective_db_connections / 2)
        min_pool_size = math.ceil(effective_db_connections / 4)
        reserve_pool_size = math.ceil(effective_db_connections / 4)
        expected_databases = {
            "first_test": {
                "host": "HOST",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "first_test_readonly": {
                "host": "HOST2",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "first_test_standby": {
                "host": "HOST2",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "second_test": {
                "host": "HOST",
                "dbname": "second_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "second_test_readonly": {
                "host": "HOST2",
                "dbname": "second_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
        }
        for i in range(self.charm._cores):
            expected_content = template.render(
                databases=expected_databases,
                readonly_databases={},
                peer_id=i,
                peers=range(self.charm._cores),
                socket_dir=f"/var/lib/pgbouncer/instance_{i}",
                log_file=f"/var/log/pgbouncer/instance_{i}/pgbouncer.log",
                pid_file=f"/var/lib/pgbouncer/instance_{i}/pgbouncer.pid",
                listen_port=6432,
                pool_mode="session",
                max_db_connections=100,
                default_pool_size=default_pool_size,
                min_pool_size=min_pool_size,
                reserve_pool_size=reserve_pool_size,
                admin_user="pgbouncer_admin_pgbouncer_k8s",
                stats_user="pgbouncer_stats_pgbouncer_k8s",
                auth_type="scram-sha-256",
                auth_query="SELECT username, password FROM pgbouncer_auth_BACKNEND_USER.get_auth($1)",
                auth_file="/dev/shm/pgbouncer-k8s_test",
                enable_tls=False,
            )
            _push_file.assert_any_call(
                f"/var/lib/pgbouncer/instance_{i}/pgbouncer.ini", expected_content, 0o400
            )
        _check_pgb_running.assert_called_once_with()
        _send_signal.assert_has_calls([
            call(SIGHUP, service["name"]) for service in self.charm._services
        ])
        _push_file.reset_mock()

        # test constant pool sizes with unlimited connections and no ro endpoints
        with self.harness.hooks_disabled():
            self.harness.update_config({
                "max_db_connections": 0,
            })
        expected_databases["first_test_readonly"]["host"] = "HOST"
        expected_databases["first_test_standby"]["host"] = "HOST"
        expected_databases["second_test_readonly"]["host"] = "HOST"
        expected_databases["*"] = {
            "host": "HOST",
            "port": "PORT",
            "auth_dbname": "first_test",
            "auth_user": "pgbouncer_auth_BACKNEND_USER",
        }
        _get_dbs.return_value["*"] = {"name": "*", "auth_dbname": "first_test"}

        del _postgres_databag.return_value["read-only-endpoints"]

        self.charm.render_pgb_config()

        for i in range(self.charm._cores):
            expected_content = template.render(
                databases=expected_databases,
                readonly_databases={},
                peer_id=i,
                peers=range(self.charm._cores),
                socket_dir=f"/var/lib/pgbouncer/instance_{i}",
                log_file=f"/var/log/pgbouncer/instance_{i}/pgbouncer.log",
                pid_file=f"/var/lib/pgbouncer/instance_{i}/pgbouncer.pid",
                listen_port=6432,
                pool_mode="session",
                max_db_connections=0,
                default_pool_size=20,
                min_pool_size=10,
                reserve_pool_size=10,
                admin_user="pgbouncer_admin_pgbouncer_k8s",
                stats_user="pgbouncer_stats_pgbouncer_k8s",
                auth_type="scram-sha-256",
                auth_query="SELECT username, password FROM pgbouncer_auth_BACKNEND_USER.get_auth($1)",
                auth_file="/dev/shm/pgbouncer-k8s_test",
                enable_tls=False,
            )
            _push_file.assert_any_call(
                f"/var/lib/pgbouncer/instance_{i}/pgbouncer.ini", expected_content, 0o400
            )

    @patch("charm.PgBouncerK8sCharm.get_secret", return_value="test")
    @patch("charm.PgBouncerK8sCharm.push_file")
    def test_render_auth_file(self, _push_file, get_secret):
        self.charm.render_auth_file()

        _push_file.assert_called_once_with(self.charm.auth_file, "test", 0o400)

    @patch("charm.Peers.app_databag", new_callable=PropertyMock, return_value={})
    @patch("charm.PgBouncerK8sCharm.get_secret")
    def test_get_relation_databases_legacy_data(self, _get_secret, _):
        """Test that legacy data will be parsed if new one is not set."""
        self.harness.set_leader(False)
        _get_secret.return_value = """
        [databases]
        test_db = host_cfg
        test_db_standby = host_cfg
        other_db = other_cfg
        """
        result = self.charm.get_relation_databases()
        assert result == {
            "1": {"legacy": False, "name": "test_db"},
            "2": {"legacy": False, "name": "other_db"},
        }
        _get_secret.assert_called_once_with("app", "cfg_file")

        # Get empty dict if no config is set
        _get_secret.return_value = None
        assert self.charm.get_relation_databases() == {}

        # Get empty dict if exception
        _get_secret.return_value = 1
        assert self.charm.get_relation_databases() == {}

        # Get empty dict if no databases
        _get_secret.return_value = """
        [other]
        test_db = host_cfg
        test_db_standby = host_cfg
        other_db = other_cfg
        """
        assert self.charm.get_relation_databases() == {}

    @patch("charm.PgBouncerK8sCharm.get_relation_databases", return_value={"some": "values"})
    def test_generate_relation_databases_not_leader(self, _):
        self.harness.set_leader(False)

        assert self.charm.generate_relation_databases() == {}

    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.update_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_push_tls_files_to_workload_enabled_tls(self, get_tls_files, update_config, push_file):
        get_tls_files.return_value = ("key", "ca", "cert")

        self.charm.push_tls_files_to_workload()

        get_tls_files.assert_called_once_with()
        update_config.assert_called_once_with()
        assert push_file.call_count == 3
        push_file.assert_any_call("/var/lib/pgbouncer/key.pem", "key", 0o400)
        push_file.assert_any_call("/var/lib/pgbouncer/ca.pem", "ca", 0o400)
        push_file.assert_any_call("/var/lib/pgbouncer/cert.pem", "cert", 0o400)

    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.update_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_push_tls_files_to_workload_disabled_tls(
        self, get_tls_files, update_config, push_file
    ):
        get_tls_files.return_value = (None, None, None)

        self.charm.push_tls_files_to_workload(False)

        get_tls_files.assert_called_once_with()
        update_config.assert_not_called()
        push_file.assert_not_called()

    @patch(
        "charm.BackendDatabaseRequires.auth_user",
        new_callable=PropertyMock,
        return_value="auth_user",
    )
    @patch(
        "charm.BackendDatabaseRequires.postgres_databag",
        new_callable=PropertyMock,
        return_value={},
    )
    @patch(
        "charm.BackendDatabaseRequires.relation", new_callable=PropertyMock, return_value=Mock()
    )
    def test_get_readonly_dbs(self, _backend_rel, _postgres_databag, _):
        with self.harness.hooks_disabled():
            self.harness.update_relation_data(
                self.rel_id, self.charm.app.name, {"readonly_dbs": '["includedb"]'}
            )

        # Returns empty if no wildcard
        assert self.charm._get_readonly_dbs({}) == {}

        # Returns empty if no readonly backends
        assert self.charm._get_readonly_dbs({"*": {"name": "*", "auth_dbname": "authdb"}}) == {}

        _postgres_databag.return_value = {
            "endpoints": "HOST:PORT",
            "read-only-endpoints": "HOST2:PORT,HOST3:PORT",
        }
        assert self.charm._get_readonly_dbs({"*": {"name": "*", "auth_dbname": "authdb"}}) == {
            "includedb_readonly": {
                "auth_dbname": "authdb",
                "auth_user": "auth_user",
                "dbname": "includedb",
                "host": "HOST2,HOST3",
                "port": "PORT",
            }
        }

    @patch("charm.BackendDatabaseRequires.postgres")
    @patch(
        "charm.PgBouncerK8sCharm.get_relation_databases",
        return_value={"1": {"name": "excludeddb"}},
    )
    def test_collect_readonly_dbs(self, _get_relation_databases, _postgres):
        _postgres._connect_to_database().__enter__().cursor().__enter__().fetchall.return_value = (
            ("includeddb",),
            ("excludeddb",),
        )

        # don't collect if not leader
        self.charm._collect_readonly_dbs()
        assert "readonly_dbs" not in self.charm.peers.app_databag

        with self.harness.hooks_disabled():
            self.harness.set_leader()

        self.charm._collect_readonly_dbs()

        assert self.charm.peers.app_databag["readonly_dbs"] == '["includeddb"]'

        # don't fail if no connection
        _postgres._connect_to_database().__enter__().cursor().__enter__().fetchall.return_value = ()
        _postgres._connect_to_database().__enter__.side_effect = psycopg2.Error

        self.charm._collect_readonly_dbs()

        assert self.charm.peers.app_databag["readonly_dbs"] == '["includeddb"]'

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch("charm.get_pod")
    def test_reconcile_k8s_service_already_exists(self, _get_pod, _get_service):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="ClusterIP")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        assert self.charm.reconcile_k8s_service(port_changed=False)
        _get_pod.assert_not_called()

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch("charm.get_pod")
    def test_reconcile_k8s_service_port_changed(self, _get_pod, _get_service):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="NodePort")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _lightkube_client = MagicMock()
        self.charm.lightkube_client = _lightkube_client

        _get_pod_mock, metadata_mock = MagicMock(), MagicMock()
        type(metadata_mock).ownerReferences = PropertyMock(return_value="owner")
        type(_get_pod_mock).metadata = metadata_mock
        _get_pod.return_value = _get_pod_mock

        expected_service = lightkube.resources.core_v1.Service(
            metadata=lightkube.models.meta_v1.ObjectMeta(
                name=self.charm.k8s_service_name,
                namespace=self.charm.model.name,
                ownerReferences="owner",  # the stateful set
                labels={"app.kubernetes.io/name": self.charm.app.name},
                annotations={},
            ),
            spec=lightkube.models.core_v1.ServiceSpec(
                ports=[
                    lightkube.models.core_v1.ServicePort(
                        name="pgbouncer",
                        port=self.charm.config.listen_port,
                        targetPort=self.charm.config.listen_port,
                    ),
                ],
                type="ClusterIP",
                selector={"app.kubernetes.io/name": self.charm.app.name},
            ),
        )

        assert self.charm.reconcile_k8s_service(port_changed=True)
        _get_pod.assert_called()
        _lightkube_client.apply.assert_called_with(
            expected_service, field_manager=self.charm.app.name
        )

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch("charm.get_pod")
    def test_reconcile_k8s_service(self, _get_pod, _get_service):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="NodePort")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _lightkube_client = MagicMock()
        self.charm.lightkube_client = _lightkube_client

        _get_pod_mock, metadata_mock = MagicMock(), MagicMock()
        type(metadata_mock).ownerReferences = PropertyMock(return_value="owner")
        type(_get_pod_mock).metadata = metadata_mock
        _get_pod.return_value = _get_pod_mock

        expected_service = lightkube.resources.core_v1.Service(
            metadata=lightkube.models.meta_v1.ObjectMeta(
                name=self.charm.k8s_service_name,
                namespace=self.charm.model.name,
                ownerReferences="owner",  # the stateful set
                labels={"app.kubernetes.io/name": self.charm.app.name},
                annotations={},
            ),
            spec=lightkube.models.core_v1.ServiceSpec(
                ports=[
                    lightkube.models.core_v1.ServicePort(
                        name="pgbouncer",
                        port=self.charm.config.listen_port,
                        targetPort=self.charm.config.listen_port,
                    ),
                ],
                type="ClusterIP",
                selector={"app.kubernetes.io/name": self.charm.app.name},
            ),
        )

        assert self.charm.reconcile_k8s_service(port_changed=True)
        _get_pod.assert_called()
        _lightkube_client.apply.assert_called_with(
            expected_service, field_manager=self.charm.app.name
        )

    @patch("charm.PgBouncerK8sCharm.get_service")
    def test_get_hosts_ports_cluster_ip(self, _get_service):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="ClusterIP")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        expected_k8s_service = f"{self.charm.k8s_service_name}.{self.charm.model.name}.svc.cluster.local:{self.charm.config.listen_port}"

        assert self.charm.get_hosts_ports("rw") == expected_k8s_service
        assert self.charm.get_hosts_ports("rw") == expected_k8s_service

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch("charm.get_node")
    def test_get_hosts_ports_node_port(self, _get_node, _get_service):
        get_service_mock, spec_mock, node_ports_mock = MagicMock(), MagicMock(), MagicMock()
        type(node_ports_mock).name = PropertyMock(return_value="pgbouncer")
        type(node_ports_mock).nodePort = "5678"
        type(spec_mock).type = PropertyMock(return_value="NodePort")
        type(spec_mock).ports = [node_ports_mock]
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _get_node_mock, status_mock, address_mock = MagicMock(), MagicMock(), MagicMock()
        type(address_mock).type = PropertyMock(return_value="ExternalIP")
        type(address_mock).address = PropertyMock(return_value="1.2.3.4")
        type(status_mock).addresses = [address_mock]
        type(_get_node_mock).status = status_mock
        _get_node.return_value = _get_node_mock

        assert self.charm.get_hosts_ports("rw") == "1.2.3.4:5678"
        assert self.charm.get_hosts_ports("ro") == "1.2.3.4:5678"

    @patch("charm.PgBouncerK8sCharm.get_service")
    def test_get_hosts_ports_load_balancer(self, _get_service):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="LoadBalancer")
        type(get_service_mock).spec = spec_mock

        status_mock, load_balancer_mock, ingress_mock = MagicMock(), MagicMock(), MagicMock()
        type(ingress_mock).ip = "1.2.3.4"
        type(load_balancer_mock).ingress = [ingress_mock]
        type(status_mock).loadBalancer = load_balancer_mock
        type(get_service_mock).status = status_mock

        _get_service.return_value = get_service_mock

        assert self.charm.get_hosts_ports("rw") == f"1.2.3.4:{self.charm.config.listen_port}"
        assert self.charm.get_hosts_ports("ro") == f"1.2.3.4:{self.charm.config.listen_port}"

        type(ingress_mock).ip = None
        type(ingress_mock).hostname = "test-host"

        assert self.charm.get_hosts_ports("rw") == f"test-host:{self.charm.config.listen_port}"
        assert self.charm.get_hosts_ports("ro") == f"test-host:{self.charm.config.listen_port}"

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch(
        "charm.PgBouncerK8sCharm.read_write_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:1234",
    )
    @patch(
        "charm.PgBouncerK8sCharm.read_only_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:5678",
    )
    @patch("socket.socket")
    def test_check_service_connectivity(
        self, _socket, _read_only_endpoints, _read_write_endpoints, _get_service
    ):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="ClusterIP")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _socket.return_value.__enter__.return_value.connect_ex.return_value = 0

        assert self.charm.check_service_connectivity()

        assert sorted(
            _socket.return_value.__enter__.return_value.connect_ex.call_args_list
        ) == sorted([call(("1.2.3.4", 1234)), call(("1.2.3.4", 5678))])

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch(
        "charm.PgBouncerK8sCharm.read_write_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:1234",
    )
    @patch(
        "charm.PgBouncerK8sCharm.read_only_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:5678",
    )
    @patch("socket.socket")
    def test_check_service_connectivity_false(
        self, _socket, _read_only_endpoints, _read_write_endpoints, _get_service
    ):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="ClusterIP")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _socket.return_value.__enter__.return_value.connect_ex.return_value = 1

        assert not self.charm.check_service_connectivity()

        assert sorted(
            _socket.return_value.__enter__.return_value.connect_ex.call_args_list
        ) == sorted([call(("1.2.3.4", 1234))])

    @patch("charm.PgBouncerK8sCharm.get_service")
    @patch(
        "charm.PgBouncerK8sCharm.read_write_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:1234",
    )
    @patch(
        "charm.PgBouncerK8sCharm.read_only_endpoints",
        new_callable=PropertyMock,
        return_value="1.2.3.4:5678",
    )
    @patch("socket.socket")
    def test_check_service_connectivity_error(
        self, _socket, _read_only_endpoints, _read_write_endpoints, _get_service
    ):
        get_service_mock, spec_mock = MagicMock(), MagicMock()
        type(spec_mock).type = PropertyMock(return_value="ClusterIP")
        type(get_service_mock).spec = spec_mock
        _get_service.return_value = get_service_mock

        _socket.return_value.__enter__.return_value.connect_ex.side_effect = socket.gaierror

        assert not self.charm.check_service_connectivity()

    @patch("charm.PgBouncerK8sCharm.config", new_callable=PropertyMock, return_value={})
    def test_configuration_check(self, _config):
        assert self.charm.configuration_check()

        _config.side_effect = ValueError
        assert not self.charm.configuration_check()
        assert isinstance(self.charm.unit.status, BlockedStatus)
        assert self.charm.unit.status.message == "Configuration Error. Please check the logs"

    #
    # Secrets
    #

    def test_scope_obj(self):
        assert self.charm._scope_obj("app") == self.charm.framework.model.app
        assert self.charm._scope_obj("unit") == self.charm.framework.model.unit
        assert self.charm._scope_obj("test") is None

    def test_get_secret(self):
        # App level changes require leader privileges
        with self.harness.hooks_disabled():
            self.harness.set_leader()
        # Test application scope.
        assert self.charm.get_secret("app", "password") is None
        self.harness.update_relation_data(
            self.rel_id, self.charm.app.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("app", "password") == "test-password"

        # Unit level changes don't require leader privileges
        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        # Test unit scope.
        assert self.charm.get_secret("unit", "password") is None
        self.harness.update_relation_data(
            self.rel_id, self.charm.unit.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("unit", "password") == "test-password"

    @parameterized.expand([("app", "monitoring-password"), ("unit", "csr")])
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_get_secret_secrets(self, scope, field, _):
        with self.harness.hooks_disabled():
            self.harness.set_leader()

        assert self.charm.get_secret(scope, field) is None
        self.charm.set_secret(scope, field, "test")
        assert self.charm.get_secret(scope, field) == "test"

    def test_set_secret(self):
        with self.harness.hooks_disabled():
            self.harness.set_leader()

        # Test application scope.
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.app.name)
        self.charm.set_secret("app", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.rel_id, self.charm.app.name)["password"]
            == "test-password"
        )
        self.charm.set_secret("app", "password", None)
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.app.name)

        # Test unit scope.
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.unit.name)
        self.charm.set_secret("unit", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.rel_id, self.charm.unit.name)["password"]
            == "test-password"
        )
        self.charm.set_secret("unit", "password", None)
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.unit.name)

        with self.assertRaises(RuntimeError):
            self.charm.set_secret("test", "password", "test")

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_set_reset_new_secret(self, scope, is_leader, _):
        """NOTE: currently ops.testing seems to allow for non-leader to set secrets too!"""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        # Getting current password
        self.harness.charm.set_secret(scope, "new-secret", "bla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "new-secret", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "blablabla"

        # Set another new secret
        self.harness.charm.set_secret(scope, "new-secret2", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret2") == "blablabla"

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_invalid_secret(self, scope, is_leader, _):
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        with self.assertRaises((RelationDataTypeError, TypeError)):
            self.harness.charm.set_secret(scope, "somekey", 1)

        self.harness.charm.set_secret(scope, "somekey", "")
        assert self.harness.charm.get_secret(scope, "somekey") is None

    @pytest.mark.usefixtures("use_caplog")
    def test_delete_password(self):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.update_relation_data(
            self.rel_id, self.charm.app.name, {"replication": "somepw"}
        )
        self.harness.charm.remove_secret("app", "replication")
        assert self.harness.charm.get_secret("app", "replication") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        self.harness.update_relation_data(
            self.rel_id, self.charm.unit.name, {"somekey": "somevalue"}
        )
        self.harness.charm.remove_secret("unit", "somekey")
        assert self.harness.charm.get_secret("unit", "somekey") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        with self._caplog.at_level(logging.DEBUG):
            self.harness.charm.remove_secret("app", "replication")
            assert (
                "Non-existing field 'replication' was attempted to be removed" in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "somekey")
            assert "Non-existing field 'somekey' was attempted to be removed" in self._caplog.text

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    @pytest.mark.usefixtures("use_caplog")
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_delete_existing_password_secrets(self, _):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret("app", "monitoring-password", "somepw")
        self.harness.charm.remove_secret("app", "monitoring-password")
        assert self.harness.charm.get_secret("app", "monitoring-password") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        self.harness.charm.set_secret("unit", "csr", "somesecret")
        self.harness.charm.remove_secret("unit", "csr")
        assert self.harness.charm.get_secret("unit", "csr") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        with self._caplog.at_level(logging.DEBUG):
            self.harness.charm.remove_secret("app", "monitoring-password")
            assert (
                "Non-existing secret monitoring-password was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "csr")
            assert "Non-existing secret csr was attempted to be removed." in self._caplog.text

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_migration_from_databag(self, scope, is_leader, _):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(self.rel_id, entity.name, {"monitoring_password": "bla"})
        assert self.harness.charm.get_secret(scope, "monitoring_password") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "monitoring-password", "blablabla")
        assert self.harness.charm.model.get_secret(
            label=f"{PEER_RELATION_NAME}.pgbouncer-k8s.{scope}"
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "blablabla"
        assert "monitoring-password" not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("ops.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_migration_from_single_secret(self, scope, is_leader, _):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        secret = self.harness.charm.app.add_secret({"monitoring-password": "bla"})

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(
            self.rel_id, entity.name, {SECRET_INTERNAL_LABEL: secret.id}
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "bla"

        # Reset new secret
        # Only the leader can set app secret content.
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret(scope, "monitoring-password", "blablabla")
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)
        assert self.harness.charm.model.get_secret(
            label=f"{PEER_RELATION_NAME}.pgbouncer-k8s.{scope}"
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "blablabla"
        assert SECRET_INTERNAL_LABEL not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )

    def test_on_secret_remove(self):
        with (
            patch("ops.model.Model.juju_version", new_callable=PropertyMock) as _juju_version,
        ):
            event = Mock()

            # New juju
            _juju_version.return_value = JujuVersion("3.6.11")
            self.harness.charm._on_secret_remove(event)
            event.remove_revision.assert_called_once_with()
            event.reset_mock()

            # Old juju
            _juju_version.return_value = JujuVersion("3.6.9")
            self.harness.charm._on_secret_remove(event)
            assert not event.remove_revision.called
            event.reset_mock()

            # No secret
            event.secret.label = None
            self.harness.charm._on_secret_remove(event)
            assert not event.remove_revision.called
            event = Mock()
