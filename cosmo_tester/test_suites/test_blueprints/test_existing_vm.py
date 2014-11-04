########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

__author__ = 'dank'

import time

import fabric.api
import fabric.context_managers
from path import path

from cosmo_tester.framework.util import get_actual_keypath
from cosmo_tester.framework.testenv import TestCase
from cosmo_tester.framework.handlers.openstack import openstack_clients


class ExistingVMTest(TestCase):

    def test_existing_vm(self):
        blueprint_path = self.copy_blueprint('existing-vm')
        self.blueprint_yaml = blueprint_path / 'blueprint.yaml'

        # prefixing resources is required here because we manage
        # this resources manually and not using the openstack plugin
        # which does all this work for us.
        # 1. it is needed to work properly
        # 2. it is needed for the cleanup process to work properly
        prefix = self.env.resources_prefix
        server_name = '{}testexistingvm'.format(prefix)
        remote_key_path = '/tmp/{}test-existing-vm.pem'.format(prefix)
        key_name = '{}test_existing_vm_key'.format(prefix)
        agents_security_group = '{}{}'.format(prefix,
                                              self.env.agents_security_group)
        management_network_name = '{}{}'.format(
            prefix, self.env.management_network_name)

        nova_client, _ = openstack_clients(self.env)
        self.create_keypair_and_copy_to_manager(
            nova_client=nova_client,
            remote_key_path=remote_key_path,
            key_name=key_name)
        private_server_ip = self.create_server(
            name=server_name,
            nova_client=nova_client,
            key_name=key_name,
            security_groups=[agents_security_group],
            management_network_name=management_network_name)

        self.upload_deploy_and_execute_install(
            fetch_state=False,
            inputs=dict(
                ip=private_server_ip,
                agent_key=remote_key_path
            ))

        instances = self.client.node_instances.list(deployment_id=self.test_id)
        middle_runtime_properties = [i.runtime_properties for i in instances
                                     if i.node_id == 'middle'][0]
        self.assertDictEqual({'working': True}, middle_runtime_properties)
        self.execute_uninstall()

    def create_keypair_and_copy_to_manager(self,
                                           nova_client,
                                           remote_key_path,
                                           key_name):
        key_file = path(self.workdir) / '{}.pem'.format(key_name)
        keypair = nova_client.keypairs.create(key_name)
        key_file.write_text(keypair.private_key)
        key_file.chmod(0600)

        management_key_path = get_actual_keypath(self.env,
                                                 self.env.management_key_path)
        fabric.api.env.update({
            'timeout': 30,
            'user': self.env.cloudify_agent_user,
            'key_filename': management_key_path,
            'host_string': self.env.management_ip,
        })
        fabric.api.put(local_path=key_file,
                       remote_path=remote_key_path)

    def create_server(self,
                      nova_client,
                      name,
                      key_name,
                      security_groups,
                      management_network_name,
                      timeout=300):
        server = {
            'name': name,
            'image': self.env.ubuntu_image_id,
            'flavor': self.env.small_flavor_id,
            'key_name': key_name,
            'security_groups': security_groups
        }
        srv = nova_client.servers.create(**server)
        end = time.time() + timeout
        while srv.status != 'ACTIVE' and time.time() < end:
            sleep_time = 1
            time.sleep(sleep_time)
            srv = nova_client.servers.get(srv)
        if srv.status != 'ACTIVE':
            raise RuntimeError('Failed starting server')
        for network, network_ips in srv.networks.items():
            if network == management_network_name:
                return str(network_ips[0])
        raise RuntimeError(
            'Failed finding new server ip [expected management network '
            'name={}, vm networks={}]'.format(management_network_name,
                                              srv.networks))
