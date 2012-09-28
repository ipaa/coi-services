#!/usr/bin/env python
"""
@package ion.services.sa.tcaa.remote_endpoint
@file ion/services/sa/tcaa/remote_endpoint.py
@author Edward Hunter
@brief 2CAA Remote endpoint.
"""

__author__ = 'Edward Hunter'
__license__ = 'Apache 2.0'

# Pyon log and config objects.
from pyon.public import log
from pyon.public import CFG

import uuid
import time
import random

#
import gevent


# Pyon exceptions.
from pyon.core.exception import BadRequest
from pyon.core.exception import Conflict

from pyon.event.event import EventPublisher, EventSubscriber
from interface.objects import TelemetryStatusType, RemoteCommand

from interface.services.sa.iremote_endpoint import BaseRemoteEndpoint
from interface.services.sa.iremote_endpoint import RemoteEndpointProcessClient
from ion.services.sa.tcaa.endpoint_mixin import EndpointMixin


class ServiceCommandQueue(object):
    """
    """
    def __init__(self, id, callback):
        """
        """
        self._id = id
        self._queue = []
        self._client = None
        self._callback = callback
        self._greenlet = None
        
        if id == 'fake_id':
            pass
        
        else:
            # Look for a service with name == id.
            
            # Then look for a resource with resource_id == id.
            
            # If nothing found raise.
            # raise ValueError
            pass

    def start(self):
        
        def command_loop():
            while True:
                try:
                    cmd = self._queue.pop(0)
                    
                except IndexError:
                    # No command available, sleep for a while.
                    gevent.sleep(.1)
                    continue
                
                if self._id == 'fake_id':
                    log.debug('Processing fake command.')
                    worktime = random.uniform(.1,3)
                    gevent.sleep(worktime)
                    result = 'fake_result'
                else:
                    cmdstr = cmd.command
                    args = cmd.args
                    kwargs = cmd.kwargs
                    try:
                        func = getattr(self,_client, cmdstr)
                        result = func(*args, **kwargs)
                    
                    except AttributeError, TypeError:
                        # The command does not exist.
                        pass
                        
                    except Exception as ex:
                        # populate result with error.
                        pass
                
                cmd_result = {
                    'command_id' : cmd.command_id,
                    'result' : result
                }
                self._callback(cmd_result)
                    
        self._greenelet = gevent.spawn(command_loop)

    def stop(self):
        """
        """
        if self._greenlet:
            self._greenlet.kill()
            self._greenlet.join()
            self._greenlet = None

    def insert(self, cmd):
        """
        """
        self._queue.append(cmd)

class RemoteEndpoint(BaseRemoteEndpoint, EndpointMixin):
    """
    """
    def __init__(self, *args, **kwargs):
        """
        For framework level code only.
        """
        super(RemoteEndpoint, self).__init__(*args, **kwargs)
        
    ######################################################################    
    # Framework process lifecycle funcitons.
    ######################################################################    

    def on_init(self):
        """
        Application level initializer.
        Setup default internal values.
        """
        super(RemoteEndpoint, self).on_init()
        self.mixin_on_init()
        self._service_command_queues = {}

    def on_start(self):
        """
        Process about to be started.
        """
        super(RemoteEndpoint, self).on_start()
        self.mixin_on_start()
        
    def on_stop(self):
        """
        Process about to be stopped.
        """
        self.mixin_on_stop()
        self._stop_queues()
        super(RemoteEndpoint, self).on_stop()
    
    def on_quit(self):
        """
        Process terminated following.
        """
        self.mixin_on_quit()
        self._stop_queues()
        super(RemoteEndpoint, self).on_quit()

    ######################################################################    
    # Helpers.
    ######################################################################    

    def _stop_queues(self):
        """
        """
        for (id, queue) in self._service_command_queues.iteritems():
            queue.stop()
        self._service_command_queues = {}

    ######################################################################    
    # Callbacks.
    ######################################################################    

    def _req_callback(self, request):
        """
        """
        try:
            id = request.resource_id
            service_queue = self._service_command_queues[id]
            
        except KeyError:
            service_queue = ServiceCommandQueue(id, self._result_complete)
            service_queue.start()
            self._service_command_queues[id] = service_queue

        service_queue.insert(request)
        log.debug('Remote endpoint got request: %s', str(request))
    
    def _ack_callback(self, result):
        """
        """
        log.debug('Remote endpoint got ack for result: %s', str(result))
    
    def _server_close_callback(self):
        """
        """
        log.debug('Remote endpoint server closed.')
    
    def _client_close_callback(self):
        """
        """
        log.debug('Remote endpoint client closed.')
    
    def _consume_telemetry_event(self, *args, **kwargs):
        """
        """
        log.debug('Telemetry event received by remote endpoint, args: %s, kwargs: %s',
                  str(args), str(kwargs))
        evt = args[0]
        self._link_status = evt.status
        if evt.status == TelemetryStatusType.AVAILABLE:
            log.debug('Remote endpoint telemetry available.')
            self._on_link_up()
            
        elif evt.status == TelemetryStatusType.UNAVAILABLE:
            log.debug('Remote endpoint telemetry not available.')
            self._on_link_down()
    
    def _on_link_up(self):
        """
        Processing on link up event.
        Start client socket.
        ION link availability published when pending commands are transmitted.
        """
        log.debug('%s client connecting to %s:%i',
                    self.__class__.__name__,
                    self._other_host, self._other_port)
        self._client.start(self._other_host, self._other_port)

    def _on_link_down(self):
        """
        Processing on link down event.
        Stop client socket and publish ION link unavailability.
        """
        self._client.stop()
    
    def _result_complete(self, result):
        """
        """
        self._client.enqueue(result)

    ######################################################################    
    # Commands.
    ######################################################################    
    
    def get_port(self):
        """
        """
        return self._this_port
    
class RemoteEndpointClient(RemoteEndpointProcessClient):
    """
    Remote endpoint client.
    """
    pass
