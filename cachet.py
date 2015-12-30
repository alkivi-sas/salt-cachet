# -*- coding: utf-8 -*-
'''
Module for sending value to cachet

.. versionadded:: 2015.5.0

:configuration: This module can be used by either passing an api key and version
    directly or by specifying both in a configuration profile in the salt
    master/minion config.

    For example:

    .. code-block:: yaml

        cachet:
          api_token: peWcBiMOS9HrZG15peWcBiMOS9HrZG15


Component status :
1   Operational         The component is working.
2   Performance Issues  The component is experiencing some slowness.
3   Partial Outage      The component may not be working for everybody.
4   Major Outage        The component is not working for anybody.

Incident status :
0   Scheduled           This status is used for a scheduled status.
1   Investigating       You have reports of a problem and you're currently looking into them.
2   Identified          You've found the issue and you're working on a fix.
3   Watching            You've since deployed a fix and you're currently watching the situation.
4   Fixed               The fix has worked, you're happy to close the incident.
'''

# Import Python libs
from __future__ import absolute_import
import logging

# Import 3rd-party libs
# pylint: disable=import-error,no-name-in-module,redefined-builtin
from salt.ext.six.moves.urllib.parse import urljoin as _urljoin
from salt.ext.six.moves.urllib.parse import urlencode as _urlencode
from salt.ext.six.moves import range
import salt.ext.six.moves.http_client
# pylint: enable=import-error,no-name-in-module

log = logging.getLogger(__name__)

__virtualname__ = 'cachet'

CACHET_PARAMS_DEFINITION = {
    'components': {
        'add': {
            'name': {'mandatory': True },
            'status': {'mandatory': True },
            'description': {'mandatory': False, 'default': None },
            'link': {'mandatory': False, 'default': None },
            'order': {'mandatory': False, 'default': 0 },
            'group_id': {'mandatory': False, 'default': None },
            'enabled': {'mandatory': False, 'default': True },
        },
        'update': {
            'name': {'mandatory': False },
            'status': {'mandatory': False },
            'link': {'mandatory': False, 'default': None },
            'order': {'mandatory': False, 'default': None },
            'group_id': {'mandatory': False, 'default': None },
        },
    },
    'components.groups': {
        'add': {
            'name': {'mandatory': True },
            'order': {'mandatory': False, 'default': 0 },
        },
        'update': {
            'name': {'mandatory': False, 'default': None },
            'order': {'mandatory': False, 'default': None },
        },
    },
    'incidents': {
        'add': {
            'name': {'mandatory': True },
            'message': {'mandatory': True },
            'status': {'mandatory': True },
            'visible': {'mandatory': True, 'default': 1 },
            'component_id': {'mandatory': False, 'default': None },
            'component_status': {'mandatory': False, 'default': None },
            'notify': {'mandatory': False, 'default': False },
        },
        'update': {
            'name': {'mandatory': False },
            'message': {'mandatory': False },
            'status': {'mandatory': False },
            'visible': {'mandatory': False, 'default': 1 },
            'component_id': {'mandatory': False },
            'notify': {'mandatory': False },
        },
    },
    'metrics': {
        'add': {
            'name': {'mandatory': True },
            'suffix': {'mandatory': True },
            'description': {'mandatory': True },
            'default_value': {'mandatory': True, 'default': 0 },
            'display_chart': {'mandatory': False, 'default': 1 },
        },
    },
    'metrics.points': {
        'add': {
            'value': {'mandatory': True },
        },
    },
}


def __virtual__():
    '''
    Return virtual name of the module.

    :return: The virtual name of the module.
    '''
    return __virtualname__

def _build_args(obj, method, **kwargs):
    '''
    Helpers to build parameters
    According to CACHET_PARAMS_DEFINITION return formated args
    '''

    if obj not in CACHET_PARAMS_DEFINITION:
        raise Exception('%s not in CACHET_PARAMS_DEFINITION' % obj)

    if method not in CACHET_PARAMS_DEFINITION[obj]:
        raise Exception('%s not in CACHET_PARAMS_DEFINITION[%s]' % (method, obj))

    args = {}
    for k, config in CACHET_PARAMS_DEFINITION[obj][method].items():
        if config['mandatory']:
            if k not in kwargs:
                if 'default' in config:
                    args[k] = config['default']
                else:
                    return {'res': False, 'message': 'Mandatory params %s is missing' % k }
            else:
                args[k] = kwargs[k]
        elif k in kwargs:
            args[k] = kwargs[k]
        elif 'default' in config and config['default']:
            args[k] = config['default']

    return {'res': True, 'data': args }

def _check_component_status(data):
    '''
    Raise Exception if status between 1 and 4
    '''
    status = int(data)
    if status < 1 or status > 4:
        raise Exception('Wrong component status %s, must be between 1 and 4' % status)

def _check_incident_status(data):
    '''
    Raise Exception if status between 0 and 4
    '''
    status = int(data)
    if status < 0 or status > 4:
        raise Exception('Wrong incident status %s, must be between 0 and 4' % status)


def _query(function,
           api_url=None,
           api_token=None,
           auth=False,
           args=None,
           method='GET',
           header_dict=None,
           data=None):
    '''
    Cachet object method function to construct and execute on the API URL.

    :param api_url:     The Cachet base URL.
    :param api_token:   The Cachet api key.
    :param function:    The Cachet api function to perform.
    :param method:      The HTTP method, e.g. GET or POST.
    :param data:        The data to be sent for POST method.
    :return:            The json response from the API call or False.
    '''
    query_params = {}

    ret = {'message': '',
           'res': True}

    if not api_url:
        api_url = __salt__['config.get']('cachet.api_url') or \
            __salt__['config.get']('cachet:api_url')

        if not api_url:
            log.error('No Cachet api key found.')
            ret['message'] = 'No Cachet api key found.'
            ret['res'] = False
            return ret

    if auth:
        if not api_token:
            api_token = __salt__['config.get']('cachet.api_token') or \
                __salt__['config.get']('cachet:api_token')

            if not api_token:
                log.error('No Cachet api key found.')
                ret['message'] = 'No Cachet api key found.'
                ret['res'] = False
                return ret

    base_url = _urljoin(api_url, '/api/v1/')
    url = _urljoin(base_url, function, False)

    if isinstance(args, dict):
        query_params = args

    if header_dict is None:
        header_dict = {}

    if auth:
        if 'X-Cachet-Token' not in header_dict:
            header_dict['X-Cachet-Token'] = api_token

    result = salt.utils.http.query(
        url,
        method,
        params=query_params,
        data=data,
        decode=True,
        status=True,
        header_dict=header_dict,
        opts=__opts__,
    )

    if result.get('status', None) == salt.ext.six.moves.http_client.OK:
        _result = result['dict']
        if 'error' in _result:
            ret['message'] = _result['error']
            ret['res'] = False
            return ret
        ret['message'] = _result.get('data')
        return ret
    elif result.get('status', None) == salt.ext.six.moves.http_client.NO_CONTENT:
        return True
    else:
        log.debug(url)
        log.debug(query_params)
        log.debug(data)
        log.debug(result)
        if 'error' in result:
            ret['message'] = result['error']
            ret['res'] = False
            return ret
        ret['message'] = _result.get(response)
        return ret


def ping(api_url=None):
    '''
    API test endpoint

    :param api_url: The Cachet URL.
    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.ping

        salt '*' cachet.ping api_url=https://status.test.com/
    '''
    return _query(function='ping', api_url=api_url)

def get_components(id=None,api_url=None, api_token=None):
    '''
    Return all components that have been created.
    If id is specified return wanted component

    :param id: The component id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.get_components

        salt '*' cachet.get_components 2
    '''

    if id:
        function = 'components/%d' % id
    else:
        function = 'components'

    return _query(function, api_url=api_url, api_token=api_token)

def add_component(api_url=None, api_token=None, **kwargs):
    '''
    Create a new component.

    :param name: The component name. MANDATORY
    :param status: The component status:  MANDATORY

    :param description: Description
    :param link: hypertext link
    :param order:
    :param group_id:
    :param enabled:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.add_component name=test status=1
    '''

    # Build args
    test = _build_args('components', 'add', **kwargs)
    if not test['res']:
        return test
    args= test['data']

    # Check stuff
    status = args['status']
    _check_component_status(status)

    function = 'components'

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='POST')

def update_component(id, api_url=None, api_token=None, **kwargs):
    '''
    Update a component.

    :param id: The component id.
    :param name: The component name.
    :param status: The component status: 
    :param link: hypertext link
    :param order:
    :param group_id:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.update_component 1 name=toto
    '''

    # Build args
    test = _build_args('components', 'update', **kwargs)
    if not test['res']:
        return test
    args = test['data']

    if args['status']:
        _check_component_status(args['status'])

    function = 'components/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='PUT')

def delete_component(id, api_url=None, api_token=None):
    '''
    Delete a component.

    :param id: The component id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.delete_component 1
    '''

    function = 'components/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, method='DELETE')

def get_components_groups(id=None,api_url=None, api_token=None):
    '''
    Return all components groups that have been created.
    If id is specified return wanted components group

    :param id: The component group id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.get_components_groups

        salt '*' cachet.get_components_groups 2
    '''

    if id:
        function = 'components/groups/%d' % id
    else:
        function = 'components/groups'

    return _query(function, api_url=api_url, api_token=api_token)

def add_component_group(api_url=None, api_token=None, **kwargs):
    '''
    Create a new component group.

    :param name: The component name. MANDATORY
    :param order:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.add_component_group name=test order=1
    '''

    # Build args
    test = _build_args('components.groups', 'add', **kwargs)
    if not test['res']:
        return test
    args= test['data']

    function = 'components/groups'

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='POST')

def update_component_group(id, api_url=None, api_token=None, **kwargs):
    '''
    Update a component group.

    :param id: The component group id.
    :param name: The component name.
    :param order:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.update_component_group 1 name=toto
    '''

    # Build args
    test = _build_args('components.groups', 'update', **kwargs)
    if not test['res']:
        return test
    args = test['data']

    function = 'components/groups/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='PUT')

def delete_component_group(id, api_url=None, api_token=None):
    '''
    Delete a component group.

    :param id: The component group id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.delete_component_group 1
    '''

    function = 'components/groups/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, method='DELETE')

def get_incidents(id=None,api_url=None, api_token=None):
    '''
    Return all incidents that have been created.
    If id is specified return wanted incident

    :param id: The incident id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.get_incidents

        salt '*' cachet.get_incidents 2
    '''

    if id:
        function = 'incidents/%d' % id
    else:
        function = 'incidents'

    return _query(function, api_url=api_url, api_token=api_token)

def add_incident(api_url=None, api_token=None, **kwargs):
    '''
    Create a new incident.

    :param name: MANDATORY
    :param message: MANDATORY
    :param status: MANDATORY
    :param visible: MANDATORY
    :param component_id:
    :param component_status:
    :param notify:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.add_incident name=test status=1
    '''

    # Build args
    test = _build_args('incidents', 'add', **kwargs)
    if not test['res']:
        return test
    args= test['data']

    # Check stuff
    status = args['status']
    _check_incident_status(status)

    if 'component_status' in args and args['component_status']:
        _check_component_status(args['component_status'])

    function = 'incidents'

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='POST')

def update_incident(id, api_url=None, api_token=None, **kwargs):
    '''
    Update a incident.

    :param id: The incident id.
    :param name: 
    :param message: 
    :param status: 
    :param visible: 
    :param component_id:
    :param notify:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.update_incident 1 name=toto
    '''

    # Build args
    test = _build_args('incidents', 'update', **kwargs)
    if not test['res']:
        return test
    args = test['data']

    if args['status']:
        _check_incident_status(args['status'])

    function = 'incidents/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='PUT')

def delete_incident(id, api_url=None, api_token=None):
    '''
    Delete a incident.

    :param id: The incident id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.delete_incident 1
    '''

    function = 'incidents/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, method='DELETE')

def get_metrics(id=None,api_url=None, api_token=None):
    '''
    Return all metrics that have been created.
    If id is specified return wanted metric

    :param id: The metric id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.get_metrics

        salt '*' cachet.get_metrics 2
    '''

    if id:
        function = 'metrics/%d' % id
    else:
        function = 'metrics'

    return _query(function, api_url=api_url, api_token=api_token)

def add_metric(api_url=None, api_token=None, **kwargs):
    '''
    Create a new metric.

    :param name: MANDATORY
    :param suffix: MANDATORY
    :param description: MANDATORY
    :param default_value: MANDATORY 
    :param display_chart:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.add_metric name=test suffix='Metric test' description='toto' default_value=0
    '''

    # Build args
    test = _build_args('metrics', 'add', **kwargs)
    if not test['res']:
        return test
    args= test['data']

    function = 'metrics'

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='POST')

def delete_metric(id, api_url=None, api_token=None):
    '''
    Delete a metric.

    :param id: The metric id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.delete_metric 1
    '''

    function = 'metrics/%d' % id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, method='DELETE')


def get_metrics_points(metric_id, id=None,api_url=None, api_token=None):
    '''
    Return all metrics points that have been created.
    If id is specified return wanted metrics point

    :param metric_id: The metric id.
    :param id: The metric point id.
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.get_metrics_points 2

        salt '*' cachet.get_metrics_points 2 3
    '''

    if id:
        function = 'metrics/%d/points/%d' % (metric_ic, id)
    else:
        function = 'metrics/%d/points' % metric_id

    return _query(function, api_url=api_url, api_token=api_token)

def add_metric_point(metric_id, api_url=None, api_token=None, **kwargs):
    '''
    Create a new metric point

    :param metric_id: MANDATORY
    :param value: MANDATORY
    :param timestamp:
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.add_metric_point 1 value=12
    '''

    # Build args
    test = _build_args('metrics.points', 'add', **kwargs)
    if not test['res']:
        return test
    args= test['data']

    function = 'metrics/%d/points' % metric_id

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='POST')

def delete_metric_point(metric_id, id, api_url=None, api_token=None):
    '''
    Delete a metric point.

    :param metric_id: MANDATORY
    :param id: MANDATORY
    :param api_url: The Cachet URL.
    :param api_token: The Cachet Token.

    :return: data.

    CLI Example:

    .. code-block:: bash

        salt '*' cachet.delete_metric_point 1 2
    '''

    function = 'metrics/%d/points/%d' % (metric_id, id)

    return _query(function, api_url=api_url, api_token=api_token,
                  auth=True, args=args, method='DELETE')
