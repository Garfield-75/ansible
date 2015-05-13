#!/usr/bin/python
#
# (c) 2015, Steve Gargan <steve.gargan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = """
module: consul_session
short_description: "manipulate consul sessions"
description:
 - allows the addition, modification and deletion of sessions in a consul
   cluster. These sessions can then be used in conjunction with key value pairs
   to implement distributed locks. In depth documentation for working with
   sessions can be found here http://www.consul.io/docs/internals/sessions.html
requirements:
  - "python >= 2.6"
  - python-consul
  - requests
version_added: "1.9"
author: "Steve Gargan (@sgargan)" <steve.gargan@gmail.com>
options:
    state:
        description:
          - whether the session should be present i.e. created if it doesn't
            exist, or absent, removed if present. If created, the ID for the
            session is returned in the output. If absent, the name or ID is
            required to remove the session. Info for a single session, all the
            sessions for a node or all available sessions can be retrieved by
            specifying info, node or list for the state; for node or info, the
            node name or session id is required as parameter.
        required: false
        choices: ['present', 'absent', 'info', 'node', 'list']
        default: present
    name:
        description:
          - the name that should be associated with the session. This is opaque
            to Consul and not required.
        required: false
        default: None
    delay:
        description:
          - the optional lock delay that can be attached to the session when it
            is created. Locks for invalidated sessions ar blocked from being
            acquired until this delay has expired. Valid units for delays
            include 'ns', 'us', 'ms', 's', 'm', 'h' 
        default: 15s
        required: false
    node:
        description:
          - the name of the node that with which the session will be associated.
            by default this is the name of the agent.
        required: false
        default: None
    datacenter:
        description:
          - name of the datacenter in which the session exists or should be
            created.
        required: false
        default: None
    checks:
        description:
          - a list of checks that will be used to verify the session health. If
            all the checks fail, the session will be invalidated and any locks
            associated with the session will be release and can be acquired once
            the associated lock delay has expired.
        required: false
        default: None
    host:
        description:
          - host of the consul agent defaults to localhost
        required: false
        default: localhost
    port:
        description:
          - the port on which the consul agent is running
        required: false
        default: 8500
"""

EXAMPLES = '''
- name: register basic session with consul
  consul_session:
    name: session1
    
- name: register a session with an existing check
  consul_session:
    name: session_with_check
    checks:
      - existing_check_name

- name: register a session with lock_delay
  consul_session:
    name: session_with_delay
    delay: 20s

- name: retrieve info about session by id
  consul_session: id=session_id state=info

- name: retrieve active sessions
  consul_session: state=list
'''

import sys
import urllib2

try:
    import consul
    from requests.exceptions import ConnectionError
    python_consul_installed = True
except ImportError, e:
    python_consul_installed = False

def execute(module):

    state = module.params.get('state')

    if state in ['info', 'list', 'node']:
        lookup_sessions(module)
    elif state == 'present':
        update_session(module)
    else:
        remove_session(module)

def lookup_sessions(module):

    datacenter = module.params.get('datacenter')

    state = module.params.get('state')
    consul = get_consul_api(module)
    try:
        if state == 'list':
            sessions_list = consul.session.list(dc=datacenter)
            #ditch the index, this can be grabbed from the results
            if sessions_list and sessions_list[1]:
                sessions_list = sessions_list[1]
            module.exit_json(changed=True,
                             sessions=sessions_list)
        elif state == 'node':
            node = module.params.get('node')
            if not node:
                module.fail_json(
                  msg="node name is required to retrieve sessions for node")
            sessions = consul.session.node(node, dc=datacenter)
            module.exit_json(changed=True,
                             node=node,
                             sessions=sessions)
        elif state == 'info':
            session_id = module.params.get('id')
            if not session_id:
                module.fail_json(
                  msg="session_id is required to retrieve indvidual session info")

            session_by_id = consul.session.info(session_id, dc=datacenter)
            module.exit_json(changed=True,
                             session_id=session_id,
                             sessions=session_by_id)

    except Exception, e:
        module.fail_json(msg="Could not retrieve session info %s" % e)


def update_session(module):

    name = module.params.get('name')
    session_id = module.params.get('id')
    delay = module.params.get('delay')
    checks = module.params.get('checks')
    datacenter = module.params.get('datacenter')
    node = module.params.get('node')

    consul = get_consul_api(module)
    changed = True

    try:
        
        session = consul.session.create(
            name=name,
            node=node,
            lock_delay=validate_duration('delay', delay),
            dc=datacenter,
            checks=checks
        )
        module.exit_json(changed=True,
                         session_id=session,
                         name=name,
                         delay=delay,
                         checks=checks,
                         node=node)
    except Exception, e:
        module.fail_json(msg="Could not create/update session %s" % e)


def remove_session(module):
    session_id = module.params.get('id')

    if not session_id:
        module.fail_json(msg="""A session id must be supplied in order to
        remove a session.""")

    consul = get_consul_api(module)
    changed = False

    try:
        session = consul.session.destroy(session_id)

        module.exit_json(changed=True,
                         session_id=session_id)
    except Exception, e:
        module.fail_json(msg="Could not remove session with id '%s' %s" % (
                         session_id, e))

def validate_duration(name, duration):
    if duration:
        duration_units = ['ns', 'us', 'ms', 's', 'm', 'h']
        if not any((duration.endswith(suffix) for suffix in duration_units)):
                raise Exception('Invalid %s %s you must specify units (%s)' %
                    (name, duration, ', '.join(duration_units)))
    return duration

def get_consul_api(module):
    return consul.Consul(host=module.params.get('host'),
                         port=module.params.get('port'))
                         
def test_dependencies(module):
    if not python_consul_installed:
        module.fail_json(msg="python-consul required for this module. "\
              "see http://python-consul.readthedocs.org/en/latest/#installation")

def main():
    argument_spec = dict(
        checks=dict(default=None, required=False, type='list'),
        delay=dict(required=False,type='str', default='15s'),
        host=dict(default='localhost'),
        port=dict(default=8500, type='int'),
        id=dict(required=False),
        name=dict(required=False),
        node=dict(required=False),
        state=dict(default='present',
                   choices=['present', 'absent', 'info', 'node', 'list'])
    )

    module = AnsibleModule(argument_spec, supports_check_mode=False)
    
    test_dependencies(module)
    
    try:
        execute(module)
    except ConnectionError, e:
        module.fail_json(msg='Could not connect to consul agent at %s:%s, error was %s' % (
                            module.params.get('host'), module.params.get('port'), str(e)))
    except Exception, e:
        module.fail_json(msg=str(e))

# import module snippets
from ansible.module_utils.basic import *
main()
