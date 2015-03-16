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

# a test for data persistence. We start a new cloudify manager, then kill the
# main container and restart it using the data container and see that we can
# still deploy the nodecellar app on it.

import urllib
import json
from time import sleep, time

import fabric.api

from cosmo_tester.framework.util import YamlPatcher
from cosmo_tester.test_suites.test_blueprints import nodecellar_test


class DockerPersistenceTest(nodecellar_test.NodecellarAppTest):

    def test_docker_persistence_nodecellar(self):
        provider_context = json.load(self.get_provider_context())
        self.init_fabric()
        restarted = self.restart_container()
        if not restarted:
            raise AssertionError('Failed restarting container. Test failed.')
        # elasticsearch takes a few more seconds to start
        sleep(20)
        print 'initial provider context is: {}'\
              .format(provider_context)
        print 'after reboot provider context is: {}' \
              .format(json.load(self.get_provider_context()))
        self.assertEqual(provider_context,
                         json.load(self.get_provider_context()),
                         msg='Provider context should be identical to what it '
                             'was prior to reboot.')

        self._test_nodecellar_impl('openstack-blueprint.yaml')

    def get_provider_context(self):
        context_url = 'http://{0}/provider/context' \
            .format(self.env.management_ip)
        return urllib.urlopen(context_url)

    def modify_blueprint(self):
        with YamlPatcher(self.blueprint_yaml) as patch:
            vm_props_path = 'node_types.nodecellar\.nodes\.MonitoredServer' \
                            '.properties'
            vm_type_path = 'node_types.vm_host.properties'
            patch.merge_obj('{0}.server.default'.format(vm_type_path), {
                'image': self.env.ubuntu_trusty_image_name,
                'flavor': self.env.flavor_name
            })
            # Use ubuntu trusty 14.04 as agent machine
            patch.merge_obj('{0}.server.default'.format(vm_props_path), {
                'image': self.env.ubuntu_trusty_image_id
            })

    def init_fabric(self):
        manager_keypath = self.env._config_reader.management_key_path
        fabric_env = fabric.api.env
        fabric_env.update({
            'timeout': 30,
            'user': 'ubuntu',
            'key_filename': manager_keypath,
            'host_string': self.env.management_ip,
        })

    def restart_container(self):
        # self.logger.info('terminating cloudify nginx container')
        # fabric.api.run('sudo docker exec -d frontend /bin/bash -c 'pkill -f '
        #                'nginx' ')
        fabric.api.run('sudo reboot')
        started = self._wait_for_management(self.env.management_ip, 180)
        return started

    def _wait_for_management(self, ip, timeout, port=80):
        """ Wait for url to become available
            :param ip: the manager IP
            :param timeout: in seconds
            :param port: port used by the rest service.
            :return: True of False
        """
        validation_url = 'http://{0}:{1}/blueprints'.format(ip, port)

        end = time() + timeout

        while end - time() >= 0:
            try:
                status = urllib.urlopen(validation_url).getcode()
                if status == 200:
                    return True

            except IOError:
                print 'Manager not accessible. retrying in 5 seconds.'
            sleep(5)

        return False

    def get_inputs(self):

        return {
            'image': self.env.ubuntu_image_id,
            'flavor': self.env.small_flavor_id,
            'agent_user': 'ubuntu'
        }
